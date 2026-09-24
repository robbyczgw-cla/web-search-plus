"""Shared keep-alive transport for provider requests."""

from __future__ import annotations

from http.client import IncompleteRead
import http.client
import io
import os
import socket
import ssl
import threading
import time
import urllib.request as _urllib_request
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request


# Idle connections are keyed by scheme, host, and port.
_KEEPALIVE_IDLE_SECONDS = 30.0
_KEEPALIVE_MAX_IDLE_PER_HOST = 8
_MAX_REDIRECTS = 10
_REDIRECT_CODES = {301, 302, 303, 307, 308}
# Errors that mean a reused idle socket was already closed by the server.
_STALE_CONNECTION_ERRORS = (
    http.client.RemoteDisconnected,
    http.client.BadStatusLine,
    ConnectionResetError,
    ConnectionAbortedError,
    BrokenPipeError,
)


class _ConnectionPool:
    """Thread-safe pool of idle keep-alive connections, dropped after fork."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._idle: dict[tuple, list] = {}
        self._pid = os.getpid()
        self._ssl_context: ssl.SSLContext | None = None

    def _check_pid(self) -> None:
        # A forked child must never share TLS sockets with its parent.
        if self._pid != os.getpid():
            self._idle = {}
            self._pid = os.getpid()

    def new(self, key: tuple, timeout: float):
        scheme, host, port = key
        if scheme == "https":
            with self._lock:
                if self._ssl_context is None:
                    self._ssl_context = ssl.create_default_context()
                context = self._ssl_context
            return http.client.HTTPSConnection(host, port, timeout=timeout, context=context)
        return http.client.HTTPConnection(host, port, timeout=timeout)

    def acquire(self, key: tuple, timeout: float):
        now = time.monotonic()
        with self._lock:
            self._check_pid()
            idle = self._idle.get(key) or []
            while idle:
                stamp, conn = idle.pop()
                if now - stamp <= _KEEPALIVE_IDLE_SECONDS and conn.sock is not None:
                    conn.timeout = timeout
                    conn.sock.settimeout(timeout)
                    return conn, True
                conn.close()
        return self.new(key, timeout), False

    def release(self, key: tuple, conn) -> None:
        with self._lock:
            if self._pid != os.getpid():
                return
            idle = self._idle.setdefault(key, [])
            if len(idle) < _KEEPALIVE_MAX_IDLE_PER_HOST:
                idle.append((time.monotonic(), conn))
                return
        conn.close()

    def reset(self) -> None:
        with self._lock:
            idle, self._idle = self._idle, {}
            self._pid = os.getpid()
        for conns in idle.values():
            for _, conn in conns:
                conn.close()


_POOL = _ConnectionPool()


def reset_connection_pool() -> None:
    """Close every idle pooled connection (tests, config reloads)."""
    _POOL.reset()


class _PooledResponse:
    """Minimal urllib-compatible response over an already-read body."""

    def __init__(self, url: str, status: int, reason: str, headers, body: bytes):
        self.url = url
        self.status = self.code = status
        self.reason = reason
        self.headers = headers
        self._body = io.BytesIO(body)

    def read(self, amt: int | None = None) -> bytes:
        return self._body.read() if amt is None else self._body.read(amt)

    def getheader(self, name: str, default=None):
        return self.headers.get(name, default)

    def geturl(self) -> str:
        return self.url

    def close(self) -> None:
        self._body.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _keepalive_enabled() -> bool:
    return os.environ.get("WSP_HTTP_KEEPALIVE", "1").strip().lower() not in {"0", "false", "no", "off"}


def _proxy_applies(scheme: str, host: str | None) -> bool:
    proxies = _urllib_request.getproxies()
    if not (proxies.get(scheme) or proxies.get("all")):
        return False
    return not (host and _urllib_request.proxy_bypass(host))


def _send_once(key: tuple, method: str, target: str, data, headers: dict, timeout: float):
    """Send one request, retrying once on a fresh socket if a reused one was stale."""
    conn, reused = _POOL.acquire(key, timeout)
    while True:
        try:
            conn.request(method, target, body=data, headers=headers)
            response = conn.getresponse()
            body = response.read()
        except _STALE_CONNECTION_ERRORS:
            conn.close()
            if not reused:
                raise
            conn, reused = _POOL.new(key, timeout), False
            continue
        except BaseException:
            conn.close()
            raise
        if response.will_close:
            conn.close()
        else:
            _POOL.release(key, conn)
        return response.status, response.reason, response.msg, body


def _pooled_open(req: Request, timeout: float):
    url = req.full_url
    method = req.get_method()
    data = req.data
    headers = dict(req.header_items())
    if data is not None and not any(k.lower() == "content-type" for k in headers):
        headers["Content-type"] = "application/x-www-form-urlencoded"
    status, reason, resp_headers, body = 0, "", {}, b""
    try:
        for _ in range(_MAX_REDIRECTS + 1):
            parts = urlsplit(url)
            scheme = parts.scheme.lower()
            port = parts.port or (443 if scheme == "https" else 80)
            if _proxy_applies(scheme, parts.hostname):
                return _urllib_request.urlopen(Request(url, data=data, headers=headers, method=method), timeout=timeout)
            key = (scheme, parts.hostname, port)
            target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
            status, reason, resp_headers, body = _send_once(key, method, target, data, headers, timeout)
            location = resp_headers.get("Location")
            # Mirror urllib: follow any redirect for GET/HEAD, and 301/302/303
            # for other methods as a body-less GET.
            if status in _REDIRECT_CODES and location and (method in {"GET", "HEAD"} or status in {301, 302, 303}):
                url = urljoin(url, location)
                if method not in {"GET", "HEAD"}:
                    method, data = "GET", None
                    headers = {k: v for k, v in headers.items() if k.lower() not in {"content-type", "content-length"}}
                if urlsplit(url).scheme.lower() not in {"http", "https"}:
                    break
                continue
            if not 200 <= status < 300:
                raise HTTPError(url, status, reason, resp_headers, io.BytesIO(body))
            return _PooledResponse(url, status, reason, resp_headers, body)
        raise HTTPError(url, status, "Too many or unsupported redirects", resp_headers, io.BytesIO(body))
    except (HTTPError, IncompleteRead, TimeoutError, socket.timeout):
        raise
    except (OSError, http.client.HTTPException) as exc:
        # Match urllib: connection-level failures surface as URLError.
        raise URLError(exc) from exc


def urlopen(req, timeout: float = 30):
    """Drop-in for urllib.request.urlopen that reuses keep-alive connections."""
    if not isinstance(req, Request) or not _keepalive_enabled():
        return _urllib_request.urlopen(req, timeout=timeout)
    parts = urlsplit(req.full_url)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or _proxy_applies(scheme, parts.hostname):
        return _urllib_request.urlopen(req, timeout=timeout)
    return _pooled_open(req, timeout)
