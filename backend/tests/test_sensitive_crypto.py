import pytest
from cryptography.fernet import Fernet

from app.security.crypto import (
    CorruptedCiphertextError,
    InvalidEncryptionKeyError,
    MissingEncryptionKeyError,
    SensitiveValueCipher,
)


def test_sensitive_cipher_round_trip_and_purpose_binding() -> None:
    cipher = SensitiveValueCipher.from_key(Fernet.generate_key().decode())
    encrypted = cipher.encrypt("sensitive-value", purpose="feishu_signing_secret")

    assert "sensitive-value" not in encrypted
    assert cipher.decrypt(encrypted, purpose="feishu_signing_secret") == "sensitive-value"
    with pytest.raises(CorruptedCiphertextError):
        cipher.decrypt(encrypted, purpose="webhook_url")


def test_sensitive_cipher_rejects_missing_invalid_wrong_and_corrupted_keys() -> None:
    with pytest.raises(MissingEncryptionKeyError):
        SensitiveValueCipher.from_key(None)
    with pytest.raises(InvalidEncryptionKeyError):
        SensitiveValueCipher.from_key("invalid")

    first = SensitiveValueCipher.from_key(Fernet.generate_key().decode())
    second = SensitiveValueCipher.from_key(Fernet.generate_key().decode())
    encrypted = first.encrypt("secret", purpose="llm_api_key")
    with pytest.raises(CorruptedCiphertextError):
        second.decrypt(encrypted, purpose="llm_api_key")
    with pytest.raises(CorruptedCiphertextError):
        first.decrypt(encrypted[:-4] + "AAAA", purpose="llm_api_key")
