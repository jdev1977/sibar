"""Optional fixes for some tasks run in the sibar sandbox (T2.7).

Turned on by the sandbox through ``SIBAR_SANDBOX_SHIMS`` (a comma-separated
list). Like ``sitecustomize``, none of this is a boundary.

- ``clock``: the time starts at ``SIBAR_SANDBOX_CLOCK`` (ISO 8601 with a time
  zone) and runs on from there at the real rate: ``time.time``,
  ``time.time_ns``, ``time.localtime``/``gmtime``/``ctime``/``asctime``/
  ``strftime`` without a time, ``datetime.datetime.now``/``utcnow``/
  ``today`` and ``datetime.date.today``. Not changed: ``time.monotonic`` and
  ``perf_counter`` (durations stay real), file times, and clocks of C
  libraries (``pandas.Timestamp.now``, ``numpy.datetime64("now")``).
- ``stub``: HTTP and HTTPS requests to the hosts in the JSON file
  ``SIBAR_SANDBOX_STUB`` are answered from that file, inside the process,
  without a socket (the sandbox has none): for ``http.client`` and so
  ``urllib.request``, and for ``urllib3`` and so ``requests``. Each request
  is logged as a JSON line to the file the spec names. No TLS takes place:
  the client is told the connection is verified. Other clients (raw
  sockets, asyncio-based ones) still find no network.
"""

import io
import json
import os
import sys
import threading


def install():
    """Install the shims named in the environment; return import hooks."""
    wanted = {name.strip() for name in os.environ.get("SIBAR_SANDBOX_SHIMS", "").split(",")}
    hooks = {}
    if "clock" in wanted and os.environ.get("SIBAR_SANDBOX_CLOCK"):
        _clock(os.environ["SIBAR_SANDBOX_CLOCK"])
    if "stub" in wanted and os.environ.get("SIBAR_SANDBOX_STUB"):
        stub = _Stub(os.environ["SIBAR_SANDBOX_STUB"])
        hooks["http.client"] = stub.patch_http_client
        hooks["urllib3.connection"] = stub.patch_urllib3
    return hooks


# --- clock ------------------------------------------------------------------------------


def _clock(start_text):
    import datetime as dt
    import time

    start = dt.datetime.fromisoformat(start_text.replace("Z", "+00:00"))
    if start.tzinfo is None:
        start = start.replace(tzinfo=dt.timezone.utc)
    base, began = start.timestamp(), time.monotonic()

    def now():
        return base + (time.monotonic() - began)

    time.time = now
    time.time_ns = lambda: int(now() * 1_000_000_000)
    for name in ("localtime", "gmtime", "ctime"):
        original = getattr(time, name)

        def wrapper(seconds=None, _original=original):
            return _original(now() if seconds is None else seconds)

        setattr(time, name, wrapper)
    strftime, asctime, localtime = time.strftime, time.asctime, time.localtime
    time.strftime = lambda fmt, t=None: strftime(fmt, localtime() if t is None else t)
    time.asctime = lambda t=None: asctime(localtime() if t is None else t)

    real_datetime, real_date = dt.datetime, dt.date

    class _DateTimeType(type):
        def __instancecheck__(cls, value):
            return isinstance(value, real_datetime)

        def __subclasscheck__(cls, other):
            return issubclass(other, real_datetime)

    class _DateType(type):
        def __instancecheck__(cls, value):
            return isinstance(value, real_date)

        def __subclasscheck__(cls, other):
            return issubclass(other, real_date)

    class datetime(real_datetime, metaclass=_DateTimeType):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(now(), tz)

        @classmethod
        def utcnow(cls):
            return cls.fromtimestamp(now(), dt.timezone.utc).replace(tzinfo=None)

        @classmethod
        def today(cls):
            return cls.fromtimestamp(now())

    class date(real_date, metaclass=_DateType):
        @classmethod
        def today(cls):
            moment = real_datetime.fromtimestamp(now())
            return cls(moment.year, moment.month, moment.day)

    datetime.__module__ = date.__module__ = "datetime"
    datetime.__qualname__, date.__qualname__ = "datetime", "date"
    dt.datetime, dt.date = datetime, date


# --- stub --------------------------------------------------------------------------------


class _Stub:
    def __init__(self, path):
        with open(path, encoding="utf-8") as handle:
            spec = json.load(handle)
        self.hosts = {host.lower(): routes for host, routes in spec["hosts"].items()}
        self.log = spec.get("log")
        self._lock = threading.Lock()

    def handles(self, host):
        return isinstance(host, str) and host.lower() in self.hosts

    def answer(self, host, request):
        from urllib.parse import parse_qsl, urlsplit

        head, _, body = request.partition(b"\r\n\r\n")
        lines = head.decode("iso-8859-1").split("\r\n")
        method, target = (lines[0].split(" ") + ["", ""])[:2]
        headers = {}
        for line in lines[1:]:
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        url = urlsplit(target)
        query = dict(parse_qsl(url.query))
        status, payload = 404, json.dumps({"error": "not found"})
        for route in self.hosts[host.lower()]:
            if route.get("method", "GET") == method and route["path"] == url.path:
                status = route.get("status", 200)
                payload = route["body"]
                for key, value in query.items():
                    payload = payload.replace("{query." + key + "}", value)
                break
        if self.log:
            import time

            with self._lock, open(self.log, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "time": time.time(), "host": host, "method": method,
                    "path": url.path, "query": query,
                    "headers": sorted(headers)}) + "\n")
        data = payload.encode("utf-8")
        reason = {200: "OK", 404: "Not Found"}.get(status, "Status")
        return (f"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n").encode() + data

    def socket(self, host):
        return _StubSocket(self, host)

    def patch_http_client(self, module):
        stub = self
        for cls in (module.HTTPConnection, module.HTTPSConnection):
            original = cls.connect

            def connect(self, _original=original):
                if stub.handles(self.host):
                    self.sock = stub.socket(self.host)
                    return
                return _original(self)

            cls.connect = connect

    def patch_urllib3(self, module):
        stub = self
        for cls in (module.HTTPConnection, module.HTTPSConnection):
            original = cls.connect

            def connect(self, _original=original):
                if stub.handles(self.host):
                    self.sock = stub.socket(self.host)
                    self._has_connected_to_proxy = False
                    self.is_verified = True
                    self.proxy_is_verified = None
                    return
                return _original(self)

            cls.connect = connect
        connected = module.HTTPConnection.is_connected

        def is_connected(self):
            if isinstance(self.sock, _StubSocket):
                return not self.sock.closed
            return connected.fget(self)

        module.HTTPConnection.is_connected = property(is_connected)


class _StubSocket:
    """Enough of a socket for http.client and urllib3: what is sent is a
    request; the answer is read back through makefile()."""

    def __init__(self, stub, host):
        self._stub, self._host = stub, host
        self._sent, self.closed, self._timeout = b"", False, None

    def sendall(self, data):
        self._sent += bytes(data)

    def send(self, data):
        self.sendall(data)
        return len(data)

    def makefile(self, mode="rb", *args, **kwargs):
        request, self._sent = self._sent, b""
        return io.BufferedReader(io.BytesIO(self._stub.answer(self._host, request)))

    def settimeout(self, value):
        self._timeout = value

    def gettimeout(self):
        return self._timeout

    def setsockopt(self, *args):
        pass

    def shutdown(self, how):
        pass

    def close(self):
        self.closed = True

    def fileno(self):
        return -1
