"""Cache-key helpers for v4 prompt/model work."""

from __future__ import annotations

import hashlib


def cache_key(body: str | bytes, model_family: str, prompt_template_hash: str) -> str:
    body_bytes = body if isinstance(body, bytes) else body.encode("utf-8")
    digest = hashlib.sha256()
    digest.update(hashlib.sha256(body_bytes).hexdigest().encode("ascii"))
    digest.update(b"\0")
    digest.update(model_family.encode("utf-8"))
    digest.update(b"\0")
    digest.update(prompt_template_hash.encode("utf-8"))
    return digest.hexdigest()
