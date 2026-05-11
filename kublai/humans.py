"""Phase 2.5 Step 8 — Human read helper backed by hard-private/human-contacts/.

Intentionally read-mostly. The only mutation is consent updates, which
overwrite the consent block in the human-contact frontmatter.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def _split(text: str) -> tuple[dict[str, Any], str, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, "", text
    raw = m.group(1)
    body = text[m.end():]
    fm: dict[str, Any] = {}
    current_key = None
    for line in raw.splitlines():
        if not line.strip():
            current_key = None
            continue
        if line.startswith(" ") and current_key is not None and line.lstrip().startswith("- "):
            fm.setdefault(current_key, []).append(line.lstrip()[2:].strip())
            continue
        if ": " in line:
            k, _, v = line.partition(": ")
            k = k.strip()
            v = v.strip()
            if v == "":
                fm[k] = []
                current_key = k
            elif v.startswith("[") and v.endswith("]"):
                inner = v[1:-1].strip()
                fm[k] = [x.strip() for x in inner.split(",")] if inner else []
                current_key = None
            else:
                fm[k] = v.strip('"').strip("'")
                current_key = None
    return fm, raw, body


def _atomic_write(path: Path, content: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


class HumansStore:
    """Read/limited-write helper for hard-private/human-contacts/*.md."""

    def __init__(self, wiki_root: str | Path):
        self.wiki_root = Path(wiki_root).expanduser().resolve()
        self.dir = self.wiki_root / "hard-private" / "human-contacts"

    def _iter_pages(self):
        if not self.dir.is_dir():
            return
        for p in sorted(self.dir.glob("*.md")):
            yield p

    def list(self, *, limit: int = 100, offset: int = 0,
             search: str | None = None,
             include_private: bool = False,
             include_consents: bool = False,
             include_identifiers: bool = False) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        skipped = 0
        for p in self._iter_pages():
            try:
                fm, _, _ = _split(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            display = fm.get("display_name") or fm.get("name") or p.stem
            if search and search.lower() not in str(display).lower():
                continue
            if skipped < offset:
                skipped += 1
                continue
            item = {
                "human_id": fm.get("human_id") or p.stem,
                "name": display,
                "status": fm.get("status"),
                "social_cluster": fm.get("social_cluster"),
                "rel_path": str(p.relative_to(self.wiki_root)),
            }
            if include_private or include_consents:
                item["consents"] = fm.get("consents") or []
            if include_private or include_identifiers:
                for key in (
                    "identifiers",
                    "signal_phone",
                    "phone",
                    "phone_number",
                    "timezone",
                ):
                    if key in fm:
                        item[key] = fm.get(key)
            out.append(item)
            if len(out) >= limit:
                break
        return out

    def get(self, *, human_id: str) -> dict[str, Any] | None:
        for p in self._iter_pages():
            try:
                fm, _, _ = _split(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if (fm.get("human_id") or p.stem) == human_id:
                return {
                    "human_id": fm.get("human_id") or p.stem,
                    "name": fm.get("display_name") or fm.get("name") or p.stem,
                    "status": fm.get("status"),
                    "social_cluster": fm.get("social_cluster"),
                    "first_known": fm.get("first_known"),
                    "last_contact": fm.get("last_contact"),
                    "topics": fm.get("topics") or [],
                    "consents": fm.get("consents") or [],
                    "rel_path": str(p.relative_to(self.wiki_root)),
                }
        return None

    def update_consent(self, *, human_id: str, category: str, granted: bool = True) -> bool:
        for p in self._iter_pages():
            try:
                text = p.read_text(encoding="utf-8")
                fm, raw, body = _split(text)
            except Exception:
                continue
            if (fm.get("human_id") or p.stem) != human_id:
                continue
            consents = fm.get("consents") or []
            existing = [c for c in consents if not c.startswith(f"{category}:")]
            existing.append(f"{category}:{'granted' if granted else 'revoked'}")
            new_lines = []
            inserted = False
            in_consents_block = False
            for line in raw.splitlines():
                if line.startswith("consents:"):
                    new_lines.append("consents: [" + ", ".join(existing) + "]")
                    inserted = True
                    in_consents_block = True
                    continue
                if in_consents_block and line.startswith("  - "):
                    continue
                in_consents_block = False
                new_lines.append(line)
            if not inserted:
                new_lines.append("consents: [" + ", ".join(existing) + "]")
            new_text = "---\n" + "\n".join(new_lines) + "\n---\n" + body
            _atomic_write(p, new_text)
            return True
        return False
