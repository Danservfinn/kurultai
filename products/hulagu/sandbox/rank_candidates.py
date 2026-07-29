#!/usr/local/bin/python
"""Networkless stdin/stdout-only deterministic ranker entrypoint."""

from __future__ import annotations

import json
import sys

from hulagu.domain.ranking import rank_input_payload


def main() -> int:
    payload = json.load(sys.stdin)
    json.dump(rank_input_payload(payload), sys.stdout, allow_nan=False, separators=(",", ":"), sort_keys=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
