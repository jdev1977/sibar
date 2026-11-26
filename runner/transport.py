"""HTTP for the provider adapters (T0.5): one request, a streamed response.

Standard library only (``http.client`` over ``ssl``). One small HTTP library
would add little here: the runner needs one POST and line-by-line reading of
a streamed body, and it needs to know whether a failure happened *before* the
request left the machine (nothing can have been billed) or after (it may have
been). ``http.client`` exposes the connect step separately, which gives that
distinction directly.

A transport is anything with ``send(request) -> HttpResponse``; tests use a
fake one, so no test makes a network call.
"""

import http.client
import socket
import ssl
import time
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlsplit

MAX_LINE = 16 * 1024 * 1024
USER_AGENT = "sibar-runner/1"


class TransportError(Exception):
    """The request failed without an HTTP response to read."""

    sent = True  # the request may have reached the provider


class NotSentError(TransportError):
    """The connection could not be opened: no request byte was sent."""

    sent = False


class SendError(TransportError):
    """The request failed after it may have reached the provider (a timeout,
    a dropped connection): it may have been billed."""

    sent = True


@dataclass(frozen=True, repr=False)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""

    def __repr__(self):  # never show headers (they hold the key) or the body
        return f"HttpRequest({self.method} {self.url})"


class UrllibTransport:
    """Sends requests over HTTPS with ``http.client``.

    ``connect_timeout`` bounds opening the connection; ``read_timeout`` bounds
    each wait for data (a stream that goes quiet that long has failed);
    ``total_timeout`` bounds the whole response. Plain HTTP is refused except
    to hosts in ``allow_http_hosts`` (for local tests).
    """

    def __init__(self, *, connect_timeout=30.0, read_timeout=600.0,
                 total_timeout=3600.0, allow_http_hosts=()):
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.total_timeout = total_timeout
        self.allow_http_hosts = frozenset(allow_http_hosts)

    def send(self, request):
        parts = urlsplit(request.url)
        host = parts.hostname or ""
        if parts.scheme == "https":
            connection = http.client.HTTPSConnection(
                host, parts.port, timeout=self.connect_timeout,
                context=ssl.create_default_context())
        elif parts.scheme == "http" and host in self.allow_http_hosts:
            connection = http.client.HTTPConnection(
                host, parts.port, timeout=self.connect_timeout)
        else:
            raise ValueError(f"refusing to send to {parts.scheme}://{host}: "
                             "only https is allowed")
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
        try:
            connection.connect()
        except (OSError, http.client.HTTPException) as error:
            connection.close()
            raise NotSentError(f"could not connect to {host}: "
                               f"{type(error).__name__}: {error}") from None
        try:
            connection.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            connection.sock.settimeout(self.read_timeout)
            headers = {"user-agent": USER_AGENT, **request.headers,
                       "content-length": str(len(request.body))}
            connection.putrequest(request.method, target)  # adds Host and
            for name, value in headers.items():         # Accept-Encoding: identity
                connection.putheader(name, value)
        except ValueError:
            # http.client puts the bad header value, possibly a key, in its
            # message: never show it. Headers are only buffered so far.
            connection.close()
            raise NotSentError("a request header is not valid (value hidden)") from None
        except OSError as error:
            connection.close()
            raise NotSentError(f"could not prepare the connection to {host}: "
                               f"{type(error).__name__}") from None
        try:
            connection.endheaders(request.body)
            response = connection.getresponse()
        except (OSError, http.client.HTTPException) as error:
            connection.close()
            raise SendError(f"request to {host} failed after connecting: "
                            f"{type(error).__name__}: {error}") from None
        return _Response(connection, response, time.monotonic() + self.total_timeout)


class _Response:
    def __init__(self, connection, response, deadline):
        self._connection = connection
        self._response = response
        self._deadline = deadline
        self.status = response.status

    def header(self, name):
        """The header's value (case-insensitive), or None."""
        return self._response.getheader(name)

    def _check_deadline(self):
        if time.monotonic() > self._deadline:
            raise SendError("the response took longer than the total time limit")

    def lines(self):
        """Yield the body line by line (bytes, with line breaks)."""
        while True:
            self._check_deadline()
            try:
                line = self._response.readline(MAX_LINE + 1)
            except (OSError, http.client.HTTPException) as error:
                raise SendError(f"reading the response failed: "
                                f"{type(error).__name__}: {error}") from None
            if not line:
                # http.client reports a body cut short as a plain end of file.
                # A Content-Length body then has length left. A chunked body
                # leaves chunk_left at 0 rather than None, which only its
                # final empty chunk sets (a CPython detail; the adapters also
                # notice a stream that ends without its last event).
                response = self._response
                if response.length or (response.chunked and getattr(
                        response, "chunk_left", None) is not None):
                    raise SendError("the connection closed before the end of "
                                    "the response body")
                return
            if len(line) > MAX_LINE:
                raise SendError("a response line is longer than "
                                f"{MAX_LINE} bytes")
            yield line

    def read(self, limit=1024 * 1024):
        """Up to ``limit`` bytes of the body."""
        self._check_deadline()
        try:
            return self._response.read(limit)
        except (OSError, http.client.HTTPException) as error:
            raise SendError(f"reading the response failed: "
                            f"{type(error).__name__}: {error}") from None

    def close(self):
        try:
            self._response.close()
        finally:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
