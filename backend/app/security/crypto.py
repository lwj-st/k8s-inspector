from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken


class SensitiveValueError(ValueError):
    """A safe-to-log sensitive value operation failure."""


class MissingEncryptionKeyError(SensitiveValueError):
    pass


class InvalidEncryptionKeyError(SensitiveValueError):
    pass


class CorruptedCiphertextError(SensitiveValueError):
    pass


class SensitiveValueCipher:
    """Authenticated encryption for database-backed application secrets."""

    def __init__(self, fernet: Fernet) -> None:
        self._fernet = fernet

    @classmethod
    def from_key(cls, key: str | None) -> SensitiveValueCipher:
        if not key:
            raise MissingEncryptionKeyError("敏感配置加密密钥未配置")
        try:
            return cls(Fernet(key.encode("ascii")))
        except (ValueError, UnicodeEncodeError) as exc:
            raise InvalidEncryptionKeyError("敏感配置加密密钥格式无效") from exc

    def encrypt(self, value: str, *, purpose: str) -> str:
        if not value:
            raise SensitiveValueError("敏感配置值不能为空")
        if not purpose:
            raise SensitiveValueError("敏感配置用途不能为空")
        payload = json.dumps(
            {"purpose": purpose, "value": value},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._fernet.encrypt(payload).decode("ascii")

    def decrypt(self, ciphertext: str, *, purpose: str) -> str:
        if not ciphertext:
            raise CorruptedCiphertextError("敏感配置密文为空")
        try:
            raw = self._fernet.decrypt(ciphertext.encode("ascii"))
            payload = json.loads(raw.decode("utf-8"))
        except (InvalidToken, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise CorruptedCiphertextError("敏感配置无法解密") from exc
        if not isinstance(payload, dict) or payload.get("purpose") != purpose:
            raise CorruptedCiphertextError("敏感配置用途不匹配")
        value = payload.get("value")
        if not isinstance(value, str) or not value:
            raise CorruptedCiphertextError("敏感配置内容无效")
        return value
