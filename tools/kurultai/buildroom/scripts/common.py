from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BUILDROOM_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = BUILDROOM_ROOT / "schemas"
EXPECTED_ARTIFACTS = {
    "research/research-input.json": "research-input.schema.json",
    "ideas/idea-contract.json": "idea-contract.schema.json",
    "reviews/intent-review.json": "intent-review.schema.json",
    "reviews/main-review.json": "main-review.schema.json",
    "plans/product-plan.json": "product-plan.schema.json",
    "plans/build-plan.json": "build-plan.schema.json",
    "jobs/implementation-receipt.json": "implementation-receipt.schema.json",
    "verification/verification-report.json": "verification-report.schema.json",
    "verification/verification-delta.json": "verification-delta.schema.json",
    "trust/trust-report.json": "trust-report.schema.json",
    "retention/retention-review.json": "retention-review.schema.json",
    "operator/operator-summary.json": "operator-summary.schema.json",
}
SECRETISH = re.compile(r"(?i)(sk-[a-z0-9_-]{12,}|xox[baprs]-[a-z0-9-]{12,}|gh[pousr]_[a-z0-9_]{12,}|token\s*[:=]\s*[^\s,;]+|secret\s*[:=]\s*[^\s,;]+)")
ABSOLUTE_PRIVATE_PATH = re.compile(r"/(Users|home)/[^\s\"']+")

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle: return json.load(handle)

def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if re.search(r"(?i)(secret|token|password|credential|private_key)", key): out[key] = "[REDACTED_SECRET_FIELD]"
            else: out[key] = redact_value(item)
        return out
    if isinstance(value, list): return [redact_value(item) for item in value]
    if isinstance(value, str):
        value = ABSOLUTE_PRIVATE_PATH.sub("[REDACTED_ABSOLUTE_PATH]", value)
        value = SECRETISH.sub("[REDACTED_SECRET]", value)
    return value

def resolve_room_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    cwd_relative = Path.cwd() / path
    if cwd_relative.exists():
        return cwd_relative
    return BUILDROOM_ROOT / path

def copy_sanitized_room(room_dir: Path, dest_dir: Path) -> list[str]:
    if not room_dir.exists():
        raise FileNotFoundError(f"room does not exist: {room_dir}")
    if dest_dir.exists(): shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True)
    skipped=[]
    for path in sorted(room_dir.rglob("*")):
        rel=path.relative_to(room_dir); target=dest_dir/rel
        if path.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
        if path.suffix == ".json":
            data=load_json(path)
            if isinstance(data, dict) and data.get("sensitivity") == "private": skipped.append(str(rel)); continue
            write_json(target, redact_value(data))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            text=SECRETISH.sub("[REDACTED_SECRET]", ABSOLUTE_PRIVATE_PATH.sub("[REDACTED_ABSOLUTE_PATH]", path.read_text(encoding="utf-8")))
            target.write_text(text, encoding="utf-8")
    return skipped
