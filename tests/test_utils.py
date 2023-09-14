import random
from collections.abc import Hashable

import pytest

from slapbot import utils
from slapbot.utils import make_hash

comments = [
    '{Hey|Hi} [test]'
]

tag_collection = {
    'test': [
        'test1'
    ]
}


def test_spintax_generation():
    """Test that the spintax generator works"""
    generated_comment = utils.generate_comment_using_spintax(text=comments[0], tags_to_query=tag_collection, author_name='test', trim=True)
    assert generated_comment is not None
    assert generated_comment in ("Hey test1", "Hi test1")

def test_message_contains_any_links():
    links = {'google.com', 'facebook.com', 'twitter.com'}
    message = 'Check out this link: twitter.com'

    assert utils.message_contains_any_links(message, links) == True

class Foo:
    def __init__(self, x):
        self.x = x

def test_make_hash_with_dict():
    d = {"a": 1, "b": {"c": 2}}
    assert isinstance(make_hash(d), Hashable)

def test_make_hash_with_list():
    lst = [1, 2, [3, 4]]
    assert isinstance(make_hash(lst), Hashable)

def test_make_hash_with_tuple():
    tpl = (1, 2, [3, 4])
    assert isinstance(make_hash(tpl), Hashable)

def test_make_hash_with_set():
    st = {1, 2, 3}
    assert isinstance(make_hash(st), Hashable)

def test_make_hash_with_object_attributes():
    foo = Foo(42)
    assert isinstance(make_hash([foo.__dict__, foo.__class__]), Hashable)

def test_make_hash_with_function_attributes():
    def bar(x):
        return x + 1
    assert isinstance(make_hash([bar.__code__, bar.__name__]), Hashable)

def test_make_hash_with_dictproxy():
    from types import MappingProxyType
    dp = MappingProxyType({"__foo__": "bar"})
    expected_hash = make_hash({"foo": "bar"})
    actual_hash = make_hash(dp)
    for key in dp:
        if key.startswith("__"):
            continue
        assert key in actual_hash, f"Key {key} not found in actual hash"
        assert actual_hash[key] == expected_hash[key], f"Hashes for key {key} do not match"

def test_make_hash_with_nonhashable_objects():
    try:
        make_hash({"a": set(), "b": [1, 2, Foo(42)]})
    except TypeError:
        pytest.fail("make_hash raised TypeError unexpectedly")
