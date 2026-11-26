"""The HTTP transport (T0.5), against a server on this machine only.

These tests open sockets on 127.0.0.1; nothing leaves the machine and no
provider is contacted.
"""

import http.server
import socket
import threading
import time

import pytest

from runner.transport import (HttpRequest, NotSentError, SendError,
                              UrllibTransport)

LOCAL = ("127.0.0.1",)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.server.seen.append((self.path, self.headers, body))
        mode = self.path.strip("/").split("?")[0]
        if mode == "stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Request-Id", "req_1")
            self.end_headers()
            for line in (b"event: a\n", b"data: 1\n", b"\n", b"data: 2\n", b"\n"):
                self.wfile.write(line)
                self.wfile.flush()
        elif mode == "error":
            payload = b'{"error": {"message": "bad"}}'
            self.send_response(429)
            self.send_header("Retry-After", "7")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif mode == "hang":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"data: first\n")
            self.wfile.flush()
            time.sleep(1.5)
        elif mode == "slow":
            time.sleep(1.5)
            self.send_response(200)
            self.end_headers()
        elif mode == "drop":
            self.send_response(200)
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(b"data: partial\n")
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_RDWR)
        elif mode == "chunked":
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(b"e\r\ndata: partial\n\r\n0\r\n\r\n")
            self.wfile.flush()
        elif mode == "drop-chunked":
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(b"e\r\ndata: partial\n\r\n")
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_RDWR)


@pytest.fixture
def server():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.seen = []
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def url(server, path):
    return f"http://127.0.0.1:{server.server_address[1]}/{path}"


def test_a_streamed_body_arrives_line_by_line(server):
    transport = UrllibTransport(allow_http_hosts=LOCAL)
    request = HttpRequest("POST", url(server, "stream?alt=sse"),
                          {"x-test": "1", "content-type": "application/json"},
                          b'{"a": 1}')
    with transport.send(request) as response:
        assert response.status == 200
        assert response.header("request-id") == "req_1"
        assert list(response.lines()) == [b"event: a\n", b"data: 1\n", b"\n",
                                          b"data: 2\n", b"\n"]
    path, headers, body = server.seen[0]
    assert path == "/stream?alt=sse"
    assert body == b'{"a": 1}'
    assert headers["x-test"] == "1"
    assert headers["User-Agent"] == "sibar-runner/1"


def test_an_error_response_can_be_read(server):
    transport = UrllibTransport(allow_http_hosts=LOCAL)
    with transport.send(HttpRequest("POST", url(server, "error"))) as response:
        assert response.status == 429
        assert response.header("Retry-After") == "7"
        assert b"bad" in response.read()


def test_a_refused_connection_was_not_sent():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    transport = UrllibTransport(allow_http_hosts=LOCAL, connect_timeout=2)
    with pytest.raises(NotSentError):
        transport.send(HttpRequest("POST", f"http://127.0.0.1:{port}/x"))


def test_a_stream_that_goes_quiet_times_out_as_maybe_billed(server):
    transport = UrllibTransport(allow_http_hosts=LOCAL, read_timeout=0.3)
    with transport.send(HttpRequest("POST", url(server, "hang"))) as response:
        lines = response.lines()
        assert next(lines) == b"data: first\n"
        with pytest.raises(SendError):
            next(lines)


def test_a_slow_response_head_times_out_as_maybe_billed(server):
    transport = UrllibTransport(allow_http_hosts=LOCAL, read_timeout=0.3)
    with pytest.raises(SendError):
        transport.send(HttpRequest("POST", url(server, "slow")))


def test_a_finished_chunked_body_ends_cleanly(server):
    transport = UrllibTransport(allow_http_hosts=LOCAL, read_timeout=2)
    with transport.send(HttpRequest("POST", url(server, "chunked"))) as response:
        assert list(response.lines()) == [b"data: partial\n"]


@pytest.mark.parametrize("path", ["drop", "drop-chunked"])
def test_a_dropped_connection_mid_body_is_an_error(server, path):
    transport = UrllibTransport(allow_http_hosts=LOCAL, read_timeout=2)
    with transport.send(HttpRequest("POST", url(server, path))) as response:
        lines = response.lines()
        assert next(lines) == b"data: partial\n"
        with pytest.raises(SendError):
            next(lines)


def test_the_total_time_limit_applies_between_lines(server):
    transport = UrllibTransport(allow_http_hosts=LOCAL, total_timeout=0.0)
    with transport.send(HttpRequest("POST", url(server, "stream"))) as response:
        time.sleep(0.01)
        with pytest.raises(SendError, match="total time"):
            list(response.lines())


@pytest.mark.parametrize("address", ["http://example.com/x", "ftp://127.0.0.1/x",
                                     "file:///etc/passwd"])
def test_only_https_is_allowed_outside_local_tests(address):
    with pytest.raises(ValueError, match="only https"):
        UrllibTransport().send(HttpRequest("POST", address))


def test_a_bad_header_value_is_hidden_and_not_sent(server):
    secret = "sk-" + "ant-" + "q" * 30
    transport = UrllibTransport(allow_http_hosts=LOCAL)
    request = HttpRequest("POST", url(server, "stream"),
                          {"authorization": f"Bearer {secret}\n"})
    with pytest.raises(NotSentError) as error:
        transport.send(request)
    assert secret not in str(error.value)
    assert error.value.__cause__ is None
    assert server.seen == []


def test_a_request_never_shows_its_headers_or_body():
    secret = "k" * 40
    request = HttpRequest("POST", "https://api.example.com/v1",
                          {"authorization": secret}, secret.encode())
    assert secret not in repr(request)
    assert secret not in str(request)
