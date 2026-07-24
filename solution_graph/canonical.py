from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Return RFC-8785-inspired canonical JSON for the supported contract types.

    Contract numbers are integers or finite decimal JSON numbers; manifests must not
    contain NaN/Infinity. UTF-8 bytes of this representation are the digest input.
    """
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_digest(value: Any) -> str:
    payload = canonical_json(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()
