import pytest
from fastapi import HTTPException

from app.auth import _verify_dev


def test_dev_token_accepts_zennify_email():
    user = _verify_dev("dev-alice@zennify.com")
    assert user.email == "alice@zennify.com"


def test_dev_token_rejects_non_zennify_email():
    with pytest.raises(HTTPException) as excinfo:
        _verify_dev("dev-mallory@evil.com")
    assert excinfo.value.status_code == 403


def test_dev_token_rejects_malformed():
    with pytest.raises(HTTPException) as excinfo:
        _verify_dev("not-a-dev-token")
    assert excinfo.value.status_code == 401
