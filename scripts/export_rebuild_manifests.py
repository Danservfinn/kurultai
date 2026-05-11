#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "config" / "runtime-config"
HOME = Path.home()


def write_json(name: str, data: Any) -> None:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(path)


def parse_skill_header(path: Path) -> dict[str, Any]:
    text = path.read_text(errors="ignore")
    description = ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            header = text[3:end]
            for line in header.splitlines():
                if line.strip().startswith("description:"):
                    description = line.split(":", 1)[1].strip().strip('"')
                    break
    rel = path.parent.relative_to(HOME / ".hermes" / "skills")
    return {
        "name": path.parent.name,
        "path": str(rel),
        "description": description,
    }


def export_skills() -> None:
    root = HOME / ".hermes" / "skills"
    skills = []
    if root.exists():
        for md in sorted(root.glob("**/SKILL.md")):
            skills.append(parse_skill_header(md))
    write_json("skills.manifest.json", {
        "schema": "kurultai.skills-manifest.v1",
        "source": "~/.hermes/skills/**/SKILL.md",
        "note": "Names, relative paths, and descriptions only. Skill bodies are intentionally not exported by this manifest.",
        "skills": skills,
    })


def export_kanban_schema() -> None:
    db = HOME / ".hermes" / "kanban.db"
    tables = []
    if db.exists():
        con = sqlite3.connect(db)
        for name, typ in con.execute("select name, type from sqlite_master where type in ('table','view') order by name"):
            if name == "sqlite_sequence":
                continue
            cols = []
            if typ == "table":
                for col in con.execute(f"pragma table_info({name})"):
                    cols.append({
                        "name": col[1],
                        "type": col[2],
                        "not_null": bool(col[3]),
                        "default": col[4],
                        "primary_key": bool(col[5]),
                    })
            tables.append({"name": name, "type": typ, "columns": cols})
        con.close()
    write_json("kanban.schema.json", {
        "schema": "kurultai.kanban-schema.v1",
        "source": "~/.hermes/kanban.db sqlite schema only",
        "note": "No task bodies, comments, chat IDs, or run outputs are exported.",
        "tables": tables,
    })


def export_brain_manifest() -> None:
    root = HOME / "brain"
    dirs = []
    if root.exists():
        for child in sorted(root.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                count = sum(1 for p in child.rglob("*.md") if p.is_file())
                dirs.append({"name": child.name, "markdown_files": count})
    write_json("brain.manifest.json", {
        "schema": "kurultai.brain-manifest.v1",
        "wiki_root": str(root),
        "note": "Directory/file-count inventory only. Brain content and private indexes are not copied into this repo.",
        "top_level_directories": dirs,
    })


def main() -> None:
    export_skills()
    export_kanban_schema()
    export_brain_manifest()


if __name__ == "__main__":
    main()
