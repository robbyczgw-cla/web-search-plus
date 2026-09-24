"""Offline regression tests for the portable 4.3.1 runtime sync."""

import copy
import json
import multiprocessing
import os
import sys
import time
from unittest import mock

import pytest

from scripts import provider_stats, search


@pytest.fixture
def cli(monkeypatch, tmp_path, capsys):
    config = copy.deepcopy(search.DEFAULT_CONFIG)
    config['auto_routing']['provider_priority'] = ['tavily', 'exa']
    monkeypatch.setattr(search, 'load_config', lambda: config)
    monkeypatch.setenv('WSP_CACHE_DIR', str(tmp_path))
    monkeypatch.delenv('WSP_DISABLE_CACHE', raising=False)
    monkeypatch.setattr(search, 'CACHE_DIR', tmp_path)
    monkeypatch.setattr(search, 'PROVIDER_HEALTH_FILE', tmp_path / 'provider_health.json')
    monkeypatch.setattr(search, 'provider_is_configured', lambda *a: True)
    monkeypatch.setattr(search, 'validate_api_key', lambda *a: 'test-key')
    monkeypatch.setattr(search.time, 'sleep', lambda _: None)

    def run(*args):
        monkeypatch.setattr(sys, 'argv', ['search.py', '-p', 'tavily', *args])
        search.main()
        return json.loads(capsys.readouterr().out)

    return run, config


@pytest.mark.parametrize('argv,query', [
    (['-q', '--', '-foo'], '-foo'),
    (['--query=-foo'], '-foo'),
    (['-q', '-foo'], '-foo'),
    (['--query', '--provider'], '--provider'),
    (['--query=--'], '--'),
    (['-q', '--', '--'], '--'),
])
def test_query_text_reaches_provider(cli, argv, query):
    run, _ = cli
    with mock.patch.object(search, 'search_tavily', return_value={'results': []}) as call:
        run(*argv, '--no-cache')
    assert call.call_args.kwargs['query'] == query


def test_literal_double_dash_action():
    namespace = search.argparse.Namespace()
    action = search._StoreQueryText(['--query'], 'query')
    action(None, namespace, [])
    assert namespace.query == '--'


@pytest.mark.parametrize('highlights,expected', [
    (['matched passage', 'another match'], 'matched passage ... another match'),
    ([None, '', ' ', 'matched passage'], 'matched passage'),
    ([], 'leading text'), (None, 'leading text'),
])
@pytest.mark.parametrize('depth', ['normal', 'deep'])
def test_exa_prefers_highlights(highlights, expected, depth):
    with mock.patch.object(search, 'make_request', return_value={
        'results': [{'text': 'leading text', 'highlights': highlights}]
    }):
        result = search.search_exa('query', 'key', exa_depth=depth)
    assert result['results'][0]['snippet'] == expected


@pytest.mark.parametrize('args,expected', [
    (['--freshness', 'day'], 'day'),
    (['--freshness', 'day', '--time-range', 'week'], 'week'),
    (['--time-range', 'month'], 'month'),
])
def test_tavily_wire_filter_and_receipt(cli, args, expected):
    run, _ = cli
    with mock.patch.object(search, 'make_request', return_value={'results': []}) as wire:
        result = run('-q', 'query', '--no-cache', *args)
    assert wire.call_args.args[2]['time_range'] == expected
    assert result['metadata']['freshness'] == {
        'requested': expected, 'applied': True, 'provider': 'tavily', 'native_value': expected,
    }


def test_tavily_hour_is_not_reported_as_sent(cli):
    run, _ = cli
    with mock.patch.object(search, 'make_request', return_value={'results': []}) as wire:
        result = run('-q', 'query', '--time-range', 'hour', '--no-cache')
    assert 'time_range' not in wire.call_args.args[2]
    assert result['metadata']['freshness']['applied'] is False


@pytest.mark.parametrize('research', [False, True])
def test_exa_dates_resolved_once_and_preserved(cli, research):
    run, _ = cli
    frozen = search.datetime(2026, 9, 20, tzinfo=search.timezone.utc)
    extra = ['--mode', 'research', '--research-providers', 'exa', '--research-extract-count', '0'] if research else []
    with mock.patch.object(search, 'datetime') as clock, mock.patch.object(search, 'make_request', return_value={'results': []}) as wire:
        clock.now.return_value = frozen
        result = run('-p', 'exa', '-q', 'query', '--freshness', 'week', '--time-range', 'hour', '--no-cache', *extra)
    clock.now.assert_called_once()
    body = wire.call_args.args[2]
    assert body['startPublishedDate'] == '2026-09-19T23:00:00Z'
    assert body['endPublishedDate'] == '2026-09-20T00:00:00Z'
    receipt = result['metadata']['freshness']
    if research:
        receipt = receipt['per_provider'][0]
    assert receipt['requested'] == 'hour'
    assert receipt['native_value'] == {k: body[k] for k in ('startPublishedDate', 'endPublishedDate')}


def test_exa_explicit_dates_win():
    with mock.patch.object(search, 'make_request', return_value={'results': []}) as wire:
        result = search.search_exa('q', 'key', freshness='day', start_date='2025-01-01', end_date='2025-02-01')
    assert result['metadata']['applied_published_dates'] == {
        'startPublishedDate': '2025-01-01', 'endPublishedDate': '2025-02-01',
    }
    assert wire.call_args.args[2]['startPublishedDate'] == '2025-01-01'


@pytest.mark.parametrize('query,freshness,ttl,expected', [
    ('live scores', None, 3600, 60), ('latest release', None, 3600, 300),
    ('ordinary query', 'hour', 3600, 60), ('ordinary query', 'day', 3600, 300),
    ('ordinary query', 'week', 3600, 1800), ('ordinary query', None, 30, 30),
    ('ordinary query', None, 0, 3600), ('ordinary query', None, -1, 3600),
])
def test_recency_cache_ttl(query, freshness, ttl, expected):
    assert search.effective_search_cache_ttl(query, freshness=freshness, requested_ttl=ttl) == expected


def test_cache_age_no_samples_and_time_range_precedence(cli):
    run, _ = cli
    args = ['-q', 'ordinary query', '--freshness', 'day', '--time-range', 'week', '--cache-ttl', '2400']
    with mock.patch.object(search, 'search_tavily', return_value={'provider': 'tavily', 'results': []}) as call, mock.patch.object(search.time, 'time', return_value=10000):
        run(*args)
    with mock.patch.object(search.time, 'time', return_value=10400), mock.patch.object(search, 'search_tavily') as call:
        hit = run(*args)
    assert hit['cached'] is True
    assert hit['cache_age_seconds'] == 400
    call.assert_not_called()
    assert len(provider_stats._load_samples()['tavily']) == 1
    with mock.patch.object(search.time, 'time', return_value=12000), mock.patch.object(search, 'search_tavily', return_value={'results': []}) as call:
        assert run(*args)['cached'] is False
    call.assert_called_once()


def test_no_cache_bypasses_lookup(cli):
    run, _ = cli
    with mock.patch.object(search, 'cache_get') as cache, mock.patch.object(search, 'search_tavily', return_value={'results': []}):
        run('-q', 'query', '--no-cache')
    cache.assert_not_called()


@pytest.mark.parametrize('research', [False, True])
def test_every_retry_records_a_sample(cli, research):
    run, _ = cli
    extra = ['--mode', 'research', '--research-providers', 'tavily', 'exa', '--research-extract-count', '0'] if research else []
    with mock.patch.object(search, 'search_tavily', side_effect=[search.ProviderRequestError('retry', transient=True), {'results': []}]), mock.patch.object(search, 'search_exa', return_value={'results': []}):
        run('-q', 'query', '--no-cache', *extra)
    samples = provider_stats._load_samples()
    assert [sample['err'] for sample in samples['tavily']] == [True, False]
    if research:
        assert len(samples['exa']) == 1


def test_configuration_errors_do_not_record(cli):
    run, _ = cli
    with mock.patch.object(search, 'validate_api_key', side_effect=search.ProviderConfigError('missing')):
        with pytest.raises(SystemExit):
            run('-q', 'query', '--no-cache')
    assert provider_stats._load_samples() == {}


@pytest.mark.parametrize('configured,explicit,expected', [(8, None, 8), (8, 3, 3), (50, None, 20), (0, None, 1), (8, 40, 20), (8, -2, 1)])
def test_configured_count_and_clamp(cli, configured, explicit, expected):
    run, config = cli
    config['defaults']['max_results'] = configured
    extra = [] if explicit is None else ['-n', str(explicit)]
    with mock.patch.object(search, 'search_tavily', return_value={'results': []}) as call:
        run('-q', 'query', '--no-cache', *extra)
    assert call.call_args.kwargs['max_results'] == expected


def _record_in_process(directory, gate):
    os.environ['WSP_CACHE_DIR'] = directory
    os.environ.pop('WSP_DISABLE_CACHE', None)
    original = provider_stats._load_samples

    def slow_load():
        samples = original()
        time.sleep(0.03)
        return samples

    provider_stats._load_samples = slow_load
    gate.wait()
    for _ in range(8):
        provider_stats.record_provider_outcome('tavily', 0.1, 1, False)


@pytest.mark.skipif(os.name != 'posix', reason='POSIX file locking')
def test_concurrent_processes_keep_all_samples(monkeypatch, tmp_path):
    monkeypatch.setenv('WSP_CACHE_DIR', str(tmp_path))
    monkeypatch.delenv('WSP_DISABLE_CACHE', raising=False)
    context = multiprocessing.get_context('spawn')
    gate = context.Event()
    workers = [context.Process(target=_record_in_process, args=(str(tmp_path), gate)) for _ in range(2)]
    for worker in workers:
        worker.start()
    gate.set()
    for worker in workers:
        worker.join(timeout=15)
        if worker.is_alive():
            worker.terminate()
            worker.join()
            pytest.fail('stats writer did not finish')
        assert worker.exitcode == 0
    assert len(provider_stats._load_samples()['tavily']) == 16
    assert (tmp_path / 'provider_stats.json.lock').stat().st_mode & 0o777 == 0o600


def test_stats_without_fcntl(monkeypatch, tmp_path):
    monkeypatch.setenv('WSP_CACHE_DIR', str(tmp_path))
    monkeypatch.delenv('WSP_DISABLE_CACHE', raising=False)
    monkeypatch.setattr(provider_stats, 'fcntl', None)
    provider_stats.record_provider_outcome('exa', 0.1, 2, False)
    assert provider_stats._load_samples()['exa'][0]['n'] == 2


def test_stats_lock_failure_does_not_fail_search(monkeypatch, tmp_path):
    monkeypatch.setenv('WSP_CACHE_DIR', str(tmp_path))
    monkeypatch.delenv('WSP_DISABLE_CACHE', raising=False)
    with mock.patch.object(provider_stats.os, 'open', side_effect=OSError('unwritable')):
        provider_stats.record_provider_outcome('exa', 0.1, 2, False)


def test_you_dispatch_uses_time_range(cli):
    run, _ = cli
    with mock.patch.object(search, 'search_you', return_value={'results': []}) as call:
        result = run('-p', 'you', '-q', 'query', '--freshness', 'day', '--time-range', 'week', '--no-cache')
    assert call.call_args.kwargs['freshness'] == 'week'
    assert result['metadata']['freshness']['native_value'] == 'week'


def test_exa_cached_receipt_and_explicit_date_cache_keys(cli):
    run, _ = cli
    args = ['-p', 'exa', '-q', 'query', '--freshness', 'week', '--start-date', '2025-01-01']
    with mock.patch.object(search, 'make_request', return_value={'results': []}):
        first = run(*args)
    with mock.patch.object(search, 'make_request', return_value={'results': []}) as wire:
        cached = run(*args)
        assert cached['cached'] is True
        assert cached['metadata']['freshness'] == first['metadata']['freshness']
        wire.assert_not_called()
        changed = run(*args, '--start-date', '2025-02-01')
    assert changed['cached'] is False
    assert changed['metadata']['freshness']['native_value']['startPublishedDate'] == '2025-02-01'


def test_exhausted_retries_and_fallback_samples(cli):
    run, _ = cli
    with mock.patch.object(search, 'search_tavily', side_effect=search.ProviderRequestError('retry', transient=True)), mock.patch.object(search, 'search_exa', return_value={'results': []}):
        run('-q', 'query', '--no-cache')
    samples = provider_stats._load_samples()
    assert [s['err'] for s in samples['tavily']] == [True, True, True]
    assert [s['err'] for s in samples['exa']] == [False]


def test_disabled_stats_persistence_needs_no_file_lock(monkeypatch, tmp_path):
    monkeypatch.setenv('WSP_CACHE_DIR', str(tmp_path))
    monkeypatch.setenv('WSP_DISABLE_CACHE', '1')
    monkeypatch.setattr(provider_stats, '_memory_samples', {})
    with mock.patch.object(provider_stats.os, 'open', side_effect=AssertionError('disk write')):
        provider_stats.record_provider_outcome('exa', 0.1, 2, False)
    assert provider_stats._load_samples()['exa'][0]['n'] == 2
    assert list(tmp_path.iterdir()) == []


def test_release_metadata():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'package.json').read_text())
    frontmatter = (root / 'SKILL.md').read_text().split('---', 2)[1]
    fields = dict(line.split(': ', 1) for line in frontmatter.strip().splitlines())
    assert manifest['version'] == fields['version'] == '4.3.1'
    assert len(fields['description']) < 300
    assert 'perplexity' not in fields['description'].lower()
    assert 'kilo' not in fields['description'].lower()
    assert json.loads(fields['metadata'])['openclaw']['requires']['bins']
