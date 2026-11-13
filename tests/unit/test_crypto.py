"""Encryption of stored model artifacts."""

import pytest

from plotgenre.common.crypto import (ModelEncryptionError, decrypt_object, encrypt_object,
                                     generate_key)

pytestmark = pytest.mark.unit


def test_roundtrip(tmp_path):
    key = generate_key()
    path = encrypt_object({"a": [1, 2, 3]}, tmp_path / "m.enc", key)
    assert b"[1, 2, 3]" not in path.read_bytes()
    assert decrypt_object(path, key) == {"a": [1, 2, 3]}


def test_wrong_key_is_rejected(tmp_path):
    path = encrypt_object("secret", tmp_path / "m.enc", generate_key())
    with pytest.raises(ModelEncryptionError, match="wrong key or tampered"):
        decrypt_object(path, generate_key())


def test_tampered_file_is_rejected(tmp_path):
    key = generate_key()
    path = encrypt_object("secret", tmp_path / "m.enc", key)
    data = bytearray(path.read_bytes())
    data[20] ^= 0x01
    path.write_bytes(bytes(data))
    with pytest.raises(ModelEncryptionError):
        decrypt_object(path, key)


def test_missing_or_invalid_key(tmp_path, monkeypatch):
    monkeypatch.delenv("PLOTGENRE_MODEL_KEY", raising=False)
    monkeypatch.setattr("plotgenre.common.crypto.get_env", lambda *_a, **_k: None)
    with pytest.raises(ModelEncryptionError, match="not set"):
        encrypt_object(1, tmp_path / "x.enc")
    with pytest.raises(ModelEncryptionError, match="invalid"):
        encrypt_object(1, tmp_path / "x.enc", key="not-a-key")
