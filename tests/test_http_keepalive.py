"""Transport tests use fake connections and never open sockets."""

from email.message import Message
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from scripts import extract, http_client, search


@pytest.fixture
def transport(monkeypatch):
    http_client.reset_connection_pool()
    monkeypatch.setenv('WSP_HTTP_KEEPALIVE', '1')
    monkeypatch.setattr(http_client._urllib_request, 'getproxies', lambda: {})
    factory = mock.Mock(side_effect=lambda *a, **kw: connection())
    monkeypatch.setattr(http_client.http.client, 'HTTPSConnection', factory)
    yield factory
    http_client.reset_connection_pool()


def response(status=200, body=b'{"results": []}', headers=None, close=False):
    result = mock.Mock(status=status, reason='response', will_close=close)
    result.msg = Message()
    for key, value in (headers or {}).items():
        result.msg[key] = value
    result.read.return_value = body
    return result


def connection():
    result = mock.Mock()
    result.getresponse.return_value = response()
    return result


def test_same_host_reuses_connection_and_updates_timeout(transport):
    first = http_client.urlopen(Request('https://example.com/one'), timeout=10)
    second = http_client.urlopen(Request('https://example.com/two'), timeout=15)
    assert first.read() == second.read() == b'{"results": []}'
    assert transport.call_count == 1
    conn = http_client._POOL._idle[('https', 'example.com', 443)][0][1]
    conn.sock.settimeout.assert_called_with(15)
    assert conn.request.call_count == 2


def test_hosts_have_separate_connections(transport):
    http_client.urlopen(Request('https://example.com/'))
    http_client.urlopen(Request('https://example.org/'))
    assert transport.call_count == 2


@pytest.mark.parametrize('error', [
    http_client.http.client.RemoteDisconnected, http_client.http.client.BadStatusLine,
    ConnectionResetError, ConnectionAbortedError, BrokenPipeError,
])
def test_stale_connection_retries_once_on_fresh_socket(transport, error):
    old, fresh = connection(), connection()
    transport.side_effect = [old, fresh]
    http_client.urlopen(Request('https://example.com/'))
    old.request.side_effect = error('stale')
    assert http_client.urlopen(Request('https://example.com/')).read() == b'{"results": []}'
    assert transport.call_count == 2
    old.close.assert_called_once()
    fresh.request.assert_called_once()


def test_fresh_socket_failure_is_not_retried(transport):
    old, fresh = connection(), connection()
    transport.side_effect = [old, fresh]
    http_client.urlopen(Request('https://example.com/'))
    old.request.side_effect = ConnectionResetError('stale')
    fresh.request.side_effect = ConnectionResetError('fresh failure')
    with pytest.raises(URLError):
        http_client.urlopen(Request('https://example.com/'))
    assert transport.call_count == 2
    fresh.close.assert_called_once()


@pytest.mark.parametrize('setting,proxies', [('0', {}), ('1', {'https': 'proxy'})])
def test_disabled_or_proxy_uses_urllib(transport, monkeypatch, setting, proxies):
    monkeypatch.setenv('WSP_HTTP_KEEPALIVE', setting)
    monkeypatch.setattr(http_client._urllib_request, 'getproxies', lambda: proxies)
    monkeypatch.setattr(http_client._urllib_request, 'proxy_bypass', lambda host: False)
    req = Request('https://example.com/')
    with mock.patch.object(http_client._urllib_request, 'urlopen', return_value='fallback') as fallback:
        assert http_client.urlopen(req, timeout=7) == 'fallback'
    fallback.assert_called_once_with(req, timeout=7)
    transport.assert_not_called()


def test_proxy_bypass_can_pool(transport, monkeypatch):
    monkeypatch.setattr(http_client._urllib_request, 'getproxies', lambda: {'https': 'proxy'})
    monkeypatch.setattr(http_client._urllib_request, 'proxy_bypass', lambda host: True)
    http_client.urlopen(Request('https://example.com/'))
    transport.assert_called_once()


def test_closed_and_expired_connections_are_discarded(transport):
    old, fresh, last = connection(), connection(), connection()
    transport.side_effect = [old, fresh, last]
    with mock.patch.object(http_client.time, 'monotonic', return_value=0):
        http_client.urlopen(Request('https://example.com/'))
    with mock.patch.object(http_client.time, 'monotonic', return_value=31):
        fresh.getresponse.return_value.will_close = True
        http_client.urlopen(Request('https://example.com/'))
        http_client.urlopen(Request('https://example.com/'))
    assert transport.call_count == 3
    old.close.assert_called_once()
    fresh.close.assert_called_once()


def test_http_errors_preserve_body_and_retry_after(transport):
    conn = connection()
    conn.getresponse.return_value = response(429, b'quota', {'Retry-After': '2'})
    transport.side_effect = [conn]
    with pytest.raises(HTTPError) as error:
        http_client.urlopen(Request('https://example.com/'))
    assert error.value.read() == b'quota'
    assert error.value.headers['Retry-After'] == '2'


def test_post_redirect_becomes_get(transport):
    conn = connection()
    conn.getresponse.side_effect = [response(302, headers={'Location': '/next'}), response()]
    transport.side_effect = [conn]
    http_client.urlopen(Request('https://example.com/start', data=b'{}'))
    calls = conn.request.call_args_list
    assert calls[0].args == ('POST', '/start')
    assert calls[1].args == ('GET', '/next')
    assert calls[1].kwargs['body'] is None
    assert 'Content-type' not in calls[1].kwargs['headers']


def test_redirect_to_proxy_uses_urllib(transport, monkeypatch):
    conn = connection()
    conn.getresponse.return_value = response(302, headers={'Location': 'https://example.org/next'})
    transport.side_effect = [conn]
    monkeypatch.setattr(http_client, '_proxy_applies', lambda scheme, host: host == 'example.org')
    with mock.patch.object(http_client._urllib_request, 'urlopen', return_value='proxied'):
        assert http_client.urlopen(Request('https://example.com/')) == 'proxied'
    assert transport.call_count == 1


def test_pool_limit_and_reset_close_sockets(transport):
    key = ('https', 'example.com', 443)
    connections = [connection() for _ in range(9)]
    for conn in connections:
        http_client._POOL.release(key, conn)
    assert len(http_client._POOL._idle[key]) == 8
    connections[-1].close.assert_called_once()
    http_client.reset_connection_pool()
    for conn in connections:
        conn.close.assert_called_once()


def test_fork_does_not_reuse_parent_connection(transport, monkeypatch):
    http_client.urlopen(Request('https://example.com/'))
    monkeypatch.setattr(http_client.os, 'getpid', lambda: -1)
    http_client.urlopen(Request('https://example.com/'))
    assert transport.call_count == 2


def test_search_and_extract_share_transport(transport):
    assert search.urlopen is extract.urlopen is http_client.urlopen
    search.make_request('https://example.com/search', {}, {})
    search.make_get_request('https://example.com/search', {})
    assert transport.call_count == 1
