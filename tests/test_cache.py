import pytest

from slapbot.cache import Cache


@pytest.fixture(scope='function')
def cache():
    return Cache()


def test_cache_set_and_get():
    cache = Cache()
    cache.set('key', 'value')
    assert cache.get('key') == 'value'


def test_cache_delete():
    cache = Cache()
    cache.set('key', 'value')
    cache.delete('key')
    assert cache.get('key') is None


def test_cache_has():
    cache = Cache()
    cache.set('key', 'value')
    assert cache.has('key') is True
    assert cache.has('unknown_key') is False


def test_cache_clear():
    cache = Cache()
    cache.set('key1', 'value1')
    cache.set('key2', 'value2')
    cache.clear()
    assert cache.get('key1') is None
    assert cache.get('key2') is None


def test_cache_len():
    cache = Cache()
    assert len(cache) == 0
    cache.set('key1', 'value1')
    assert len(cache) == 1
    cache.set('key2', 'value2')
    assert len(cache) == 2


def test_cache_iter():
    cache = Cache()
    cache.set('key1', 'value1')
    cache.set('key2', 'value2')
    keys = []
    for key in cache:
        keys.append(key)
    assert 'key1' in keys
    assert 'key2' in keys


def test_cache_repr():
    cache = Cache()
    cache.set('key1', 'value1')
    cache.set('key2', 'value2')
    assert repr(cache) == "{'key1': 'value1', 'key2': 'value2'}"


def test_cache_str():
    cache = Cache()
    cache.set('key1', 'value1')
    cache.set('key2', 'value2')
    assert str(cache) == "{'key1': 'value1', 'key2': 'value2'}"


def test_cache(cache):
    cache.set('test', 'value')
    assert cache.get('test') == 'value'

    del cache['test']
    assert 'test' not in cache
