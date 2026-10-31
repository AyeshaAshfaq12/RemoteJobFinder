"""AES-256-GCM for profiles.data, with key versions for rotation (Build Spec section 11).

RJF_PROFILE_KEYS = "<version>:<base64 32-byte key>,..." with the newest key first.
Ciphertext layout: 2-byte big-endian key version | 12-byte nonce | GCM ciphertext+tag.
Plaintext is never logged.
"""

import base64
import os
import struct
from dataclasses import dataclass
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.settings import get_settings

_HEADER = struct.Struct(">H")
_NONCE_LEN = 12


class KeyConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class KeyRing:
    current: int
    keys: dict[int, bytes]

    @classmethod
    def parse(cls, spec: str) -> "KeyRing":
        keys: dict[int, bytes] = {}
        order: list[int] = []
        for item in filter(None, (p.strip() for p in spec.split(","))):
            version_s, _, key_b64 = item.partition(":")
            version = int(version_s)
            key = base64.b64decode(key_b64)
            if len(key) != 32:
                raise KeyConfigError(f"profile key v{version} must be 32 bytes")
            keys[version] = key
            order.append(version)
        if not order:
            raise KeyConfigError("RJF_PROFILE_KEYS is empty")
        return cls(current=order[0], keys=keys)

    def encrypt(self, plaintext: bytes, aad: bytes = b"") -> bytes:
        nonce = os.urandom(_NONCE_LEN)
        ct = AESGCM(self.keys[self.current]).encrypt(nonce, plaintext, aad)
        return _HEADER.pack(self.current) + nonce + ct

    def decrypt(self, blob: bytes, aad: bytes = b"") -> bytes:
        (version,) = _HEADER.unpack_from(blob)
        key = self.keys.get(version)
        if key is None:
            raise KeyConfigError(f"no profile key for version {version}")
        nonce = blob[_HEADER.size : _HEADER.size + _NONCE_LEN]
        return AESGCM(key).decrypt(nonce, blob[_HEADER.size + _NONCE_LEN :], aad)


@lru_cache
def keyring() -> KeyRing:
    return KeyRing.parse(get_settings().profile_keys.get_secret_value())
