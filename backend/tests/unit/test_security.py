"""密码哈希与 JWT 单元测试。"""

from datetime import timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.exceptions import Unauthorized
from app.core.security import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify_success(self) -> None:
        hashed = hash_password("Admin@123456")
        assert hashed != "Admin@123456"
        assert verify_password("Admin@123456", hashed) is True

    def test_verify_wrong_password(self) -> None:
        hashed = hash_password("Admin@123456")
        assert verify_password("wrong-password", hashed) is False

    def test_hash_is_random_salt(self) -> None:
        assert hash_password("same") != hash_password("same")

    def test_verify_with_invalid_hash(self) -> None:
        assert verify_password("x", "not-a-bcrypt-hash") is False

    def test_verify_with_empty_hash(self) -> None:
        assert verify_password("x", "") is False

    def test_long_password_is_truncated_not_crashed(self) -> None:
        # bcrypt 仅处理前 72 字节，超长密码不应抛错
        long_password = "a" * 200
        hashed = hash_password(long_password)
        assert verify_password(long_password, hashed) is True


class TestToken:
    def test_access_token_roundtrip(self) -> None:
        token, jti, expires_in = create_access_token(42)
        payload = decode_token(token, expected_type=TOKEN_TYPE_ACCESS)
        assert payload["sub"] == "42"
        assert payload["jti"] == jti
        assert payload["type"] == TOKEN_TYPE_ACCESS
        assert expires_in == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    def test_refresh_token_roundtrip(self) -> None:
        token, _, expires_in = create_refresh_token(7)
        payload = decode_token(token, expected_type=TOKEN_TYPE_REFRESH)
        assert payload["sub"] == "7"
        assert expires_in == settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600

    def test_token_type_mismatch_rejected(self) -> None:
        token, _, _ = create_refresh_token(1)
        with pytest.raises(Unauthorized):
            decode_token(token, expected_type=TOKEN_TYPE_ACCESS)

    def test_expired_token_rejected(self) -> None:
        token = jwt.encode(
            {"sub": "1", "type": TOKEN_TYPE_ACCESS, "jti": "x", "exp": -1},
            settings.SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        with pytest.raises(Unauthorized):
            decode_token(token)

    def test_tampered_token_rejected(self) -> None:
        token, _, _ = create_access_token(1)
        with pytest.raises(Unauthorized):
            decode_token(f"{token}tampered")

    def test_tokens_are_unique(self) -> None:
        first, first_jti, _ = create_access_token(1)
        second, second_jti, _ = create_refresh_token(1)
        assert first != second
        assert first_jti != second_jti

    def test_expiry_is_ordered(self) -> None:
        _, _, access_ttl = create_access_token(1)
        _, _, refresh_ttl = create_refresh_token(1)
        assert access_ttl < refresh_ttl
        assert timedelta(seconds=access_ttl) < timedelta(seconds=refresh_ttl)
