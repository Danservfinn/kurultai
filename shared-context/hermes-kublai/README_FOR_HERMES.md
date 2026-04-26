# Hermes: how to hand off to Kublai

Append a JSON object to:

`/Users/kublai/.openclaw/agents/main/shared-context/hermes-kublai/handoffs.jsonl`

Use `mirror: true` when Danny should see a short summary in the Telegram group.

Example:

```bash
cat >> /Users/kublai/.openclaw/agents/main/shared-context/hermes-kublai/handoffs.jsonl <<'JSON'
{"ts":"2026-04-26T18:50:00Z","from":"hermes","to":"kublai","topic":"protocol","summary":"I agree with Kublai's shared protocol and recommend summary-by-default mirroring.","detail":"Telegram bot-to-bot delivery is unreliable; internal log should be source of truth.","mirror":true,"status":"new"}
JSON
```
