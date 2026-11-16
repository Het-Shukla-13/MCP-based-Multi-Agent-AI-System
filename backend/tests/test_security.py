import base64
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_is_salted_and_verifiable():
    h1, h2 = hash_password("correct horse"), hash_password("correct horse")
    assert h1.startswith("$argon2id$") and h1 != h2          # random salt per hash
    assert verify_password("correct horse", h1)
    assert not verify_password("wrong", h1)
    assert not verify_password("x", "not-a-hash")             # malformed hash -> False, no crash


def test_token_roundtrip():
    uid = uuid4()
    assert decode_access_token(create_access_token(uid)) == uid


def test_tampered_token_is_rejected():
    token = create_access_token(uuid4())
    header, payload, signature = token.split(".")
    data = json.loads(base64.urlsafe_b64decode(payload + "=="))
    data["sub"] = str(uuid4())  # attacker swaps in another user id
    forged_payload = base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()
    assert decode_access_token(f"{header}.{forged_payload}.{signature}") is None


def test_alg_none_token_is_rejected():
    forged = jwt.encode({"sub": str(uuid4()), "type": "access"}, key=None, algorithm="none")
    assert decode_access_token(forged) is None


def test_expired_and_foreign_key_tokens_are_rejected():
    uid = str(uuid4())
    expired = jwt.encode({"sub": uid, "type": "access", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                         settings.JWT_SECRET, algorithm="HS256")
    other_key = jwt.encode({"sub": uid, "type": "access"}, "some-other-secret-that-is-long-enough", algorithm="HS256")
    assert decode_access_token(expired) is None
    assert decode_access_token(other_key) is None
