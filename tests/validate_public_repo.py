#!/usr/bin/env python3
from __future__ import annotations
import json, re, sys, xml.etree.ElementTree as ET
from pathlib import Path
try:
    import yaml
except Exception:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []
required = [
    'README.md', 'LICENSE', 'CONTRIBUTING.md', '.gitignore',
    'config/runtime-config/hermes.template.yaml',
    'config/runtime-config/profiles.yaml',
    'config/runtime-config/brain.yaml',
    'config/runtime-config/gateways.yaml',
    'config/runtime-config/cron.manifest.json',
    'config/runtime-config/skills.manifest.json',
    'config/runtime-config/kanban.schema.json',
    'config/runtime-config/brain.manifest.json',
    'docs/operations/fresh-install-agent-prompt.md',
    'docs/operations/full-installation-checklist.md',
    'docs/operations/kurultai-rebuild-runbook.md',
    'brain/AGENTS.md',
    'brain/templates/page.md',
    'profiles/templates/SOUL.profile.md',
]
for rel in required:
    if not (ROOT / rel).exists():
        errors.append(f'missing {rel}')

for p in (ROOT / 'docs' / 'assets').rglob('*.svg'):
    try:
        ET.parse(p)
    except Exception as exc:
        errors.append(f'invalid SVG {p.relative_to(ROOT)}: {exc}')

for p in (ROOT / 'config' / 'runtime-config').glob('*.json'):
    try:
        json.loads(p.read_text())
    except Exception as exc:
        errors.append(f'invalid JSON {p.relative_to(ROOT)}: {exc}')
if yaml:
    for p in (ROOT / 'config' / 'runtime-config').glob('*.yaml'):
        try:
            yaml.safe_load(p.read_text())
        except Exception as exc:
            errors.append(f'invalid YAML {p.relative_to(ROOT)}: {exc}')

private_key_marker = ''.join(['-----', 'BEGIN ']) + r'(?:RSA |OPENSSH |EC |DSA )?' + ''.join(['PRIVATE ', 'KEY', '-----'])
secret_patterns = [
    r'sk-[A-Za-z0-9]{20,}',
    r'gh[pousr]_[A-Za-z0-9_]{20,}',
    r'\b\d{7,12}:[A-Za-z0-9_-]{30,}\b',
    private_key_marker,
    r'(?i)(api[_-]?key|token|secret|password)[ \t]*[:=][ \t]*[^\s#]{16,}',
]
privacy_patterns = [
    '/' + 'Users' + '/' + 'kublai',
    r'(?i)TELEGRAM_CHAT_ID\s*[:=]\s*[-0-9]{6,}',
]
allowed_privacy_files = {'README.md', '.gitignore', 'security-boundary.md', 'validate_public_repo.py'}
skip_dirs = {'.git', '__pycache__', 'node_modules'}
for p in ROOT.rglob('*'):
    if not p.is_file() or any(part in skip_dirs for part in p.parts):
        continue
    if p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.pdf'}:
        continue
    text = p.read_text(errors='ignore')
    for pat in secret_patterns:
        if re.search(pat, text):
            errors.append(f'secret-like pattern in {p.relative_to(ROOT)}: {pat}')
    for pat in privacy_patterns:
        if re.search(pat, text) and p.name not in allowed_privacy_files:
            errors.append(f'privacy pattern in {p.relative_to(ROOT)}: {pat}')

if errors:
    print('\n'.join(errors))
    sys.exit(1)
print('OK: Kurultai public repo validation passed')
