"""Encryption of stored model artifacts (security requirement).

The trained model is serialised with pickle and then encrypted with Fernet
(AES-128-CBC + HMAC-SHA256) before it is written to disk, versioned by DVC
or uploaded to the MLflow artifact store. Only processes that hold the key
(``PLOTGENRE_MODEL_KEY``) - the model server - can decrypt it.
"""

from __future__ import annotations

import os
import pickle
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from plotgenre.common.config import get_env

KEY_ENV = "PLOTGENRE_MODEL_KEY"


class ModelEncryptionError(RuntimeError):
    """Raised when a key is missing/invalid or decryption fails."""


def generate_key() -> str:
    """Return a new random Fernet key as a URL-safe base64 string."""
    return Fernet.generate_key().decode("ascii")


def _fernet(key: str | None = None) -> Fernet:
    key = key or get_env(KEY_ENV)
    if not key:
        raise ModelEncryptionError(
            f"encryption key not set; export {KEY_ENV} (see .env.example)")
    try:
        return Fernet(key.encode("ascii") if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise ModelEncryptionError(f"invalid {KEY_ENV}: {exc}") from exc


def encrypt_object(obj: Any, path: str | os.PathLike, key: str | None = None) -> Path:
    """Pickle ``obj``, encrypt it and write it to ``path``."""
    token = _fernet(key).encrypt(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(token)
    return out


def decrypt_object(path: str | os.PathLike, key: str | None = None) -> Any:
    """Read ``path``, decrypt it and unpickle the object.

    Only call this on files produced by :func:`encrypt_object` - the HMAC check
    guarantees the payload was created by a holder of the key.
    """
    try:
        data = _fernet(key).decrypt(Path(path).read_bytes())
    except InvalidToken as exc:
        raise ModelEncryptionError(
            f"cannot decrypt {path}: wrong key or tampered file") from exc
    except FileNotFoundError as exc:
        raise ModelEncryptionError(f"model file not found: {path}") from exc
    return pickle.loads(data)  # noqa: S301 - authenticated by Fernet HMAC
