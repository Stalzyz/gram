import pytest
from utils.validators import extract_username, normalize_url


def test_extract_username_from_plain_username():
    assert extract_username("example_store") == "example_store"


def test_extract_username_from_url():
    assert extract_username("https://www.instagram.com/example_store/") == "example_store"


def test_extract_username_from_url_no_trailing_slash():
    assert extract_username("https://instagram.com/example_store") == "example_store"


def test_extract_username_strips_at_symbol():
    assert extract_username("@example_store") == "example_store"


def test_extract_username_rejects_invalid():
    with pytest.raises(ValueError):
        extract_username("not a valid username!!")


def test_normalize_url_adds_scheme():
    assert normalize_url("example.com") == "https://example.com"


def test_normalize_url_keeps_existing_scheme():
    assert normalize_url("http://example.com") == "http://example.com"


def test_normalize_url_empty():
    assert normalize_url("") == ""
