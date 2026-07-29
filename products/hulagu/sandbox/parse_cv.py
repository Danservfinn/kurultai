"""Secret-free bounded synthetic PDF/DOCX parser container entrypoint."""

from __future__ import annotations

import hashlib
import html
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path

MAX_INPUT = 10 * 1024 * 1024
MAX_TEXT = 64 * 1024


def _read(path: Path) -> bytes:
    if path == Path("-"):
        data = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(data) > MAX_INPUT:
            raise ValueError("input limit")
        return data
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        data = os.read(descriptor, MAX_INPUT + 1)
        if len(data) > MAX_INPUT:
            raise ValueError("input limit")
        return data
    finally:
        os.close(descriptor)


def _pdf_text(data: bytes) -> str:
    if any(marker in data for marker in (b"/Encrypt", b"/JavaScript", b"/JS", b"/OpenAction", b"/Launch")):
        raise ValueError("unsafe PDF")
    candidates = re.findall(rb"\(([^()]*)\)\s*Tj", data)
    return " ".join(item.decode("utf-8", "replace") for item in candidates)


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        if "word/document.xml" not in names or any(name.casefold().endswith("vbaproject.bin") for name in names):
            raise ValueError("unsafe DOCX")
        document = archive.read("word/document.xml")
    values = re.findall(rb"<w:t(?:\s[^>]*)?>(.*?)</w:t>", document)
    return " ".join(html.unescape(item.decode("utf-8", "replace")) for item in values)


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    data = _read(input_path)
    if data.startswith(b"%PDF-"):
        text = _pdf_text(data)
    elif data.startswith(b"PK\x03\x04"):
        text = _docx_text(data)
    else:
        raise ValueError("unsupported input")
    text = text[:MAX_TEXT]
    fields = [] if not text else [{
        "field_id": "cv_text",
        "value": text,
        "source": "cv",
        "confidence": 0.5,
        "source_span": "document",
    }]
    result = {
        "schema_version": "ParsedCv/v1",
        "document_sha256": hashlib.sha256(data).hexdigest(),
        "fields": fields,
    }
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
    descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    sys.stdout.buffer.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
