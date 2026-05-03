import asyncio
import json
import subprocess
import sys

import pytest

from kublai.context_bundle import ContextBundleError, Source
from kublai.llm import (
    ContextOverflowError,
    LlmTimeoutError,
    MalformedError,
    RateLimitError,
    RefusedError,
    ensure_external_safe,
    llm_call_fresh_context,
    llm_call_structured,
    model_for,
)
from kublai.prompt_registry import PromptRegistry
from kublai.sanitizer import PrivacyBoundaryError, Sanitizer, SanitizerContext


def test_sanitizer_classifies_path_type_tags_and_public_marker():
    sanitizer = Sanitizer()
    assert sanitizer.classify("hard-private/finance/x.md", {}) == "hard-private"
    assert sanitizer.classify("concepts/x.md", {"type": "human-contact"}) == "hard-private"
    assert sanitizer.classify("concepts/x.md", {"tags": ["pii"]}) == "hard-private"
    assert sanitizer.classify("concepts/x.md", {}) == "private"
    assert sanitizer.classify("concepts/x.md", {"publish": True}) == "public"


def test_sanitizer_scrubs_canary_and_hard_private_paths_for_llm():
    scrubbed, findings = Sanitizer().scrub(
        "see hard-private/finance/x.md KUBLAI_HARD_PRIVATE_CANARY_TEST",
        target_class="public",
        context=SanitizerContext.LLM_PROMPT,
    )
    assert "hard-private/finance/x.md" not in scrubbed
    assert "KUBLAI_HARD_PRIVATE_CANARY_TEST" not in scrubbed
    assert set(findings) == {"hard_private_path", "hard_private_canary"}


def test_context_bundle_requires_resolvable_rel_path():
    with pytest.raises(ContextBundleError):
        Source(rel_path="../secret.md", privacy_class="public")


def test_context_bundle_blocks_private_external_llm():
    bundle = Sanitizer().build_bundle(
        {"rel_path": "concepts/internal.md", "frontmatter": {}, "content": "private"}
    )
    with pytest.raises(PrivacyBoundaryError):
        ensure_external_safe(bundle, destination="external")


def test_llm_error_taxonomy_exposes_expected_failure_modes():
    assert issubclass(RateLimitError, Exception)
    assert issubclass(RefusedError, Exception)
    assert issubclass(MalformedError, Exception)
    assert issubclass(LlmTimeoutError, Exception)
    assert issubclass(ContextOverflowError, Exception)


def test_llm_structured_retries_with_pushback():
    responses = iter([
        json.dumps({"tags": ["a", "b", "c", "d", "e"]}),
        json.dumps({"tags": ["a", "b", "c"]}),
    ])
    prompts = []

    def transport(**request):
        prompts.append(request["user"])
        return next(responses)

    def validator(payload):
        if len(payload["tags"]) != 3:
            raise ValueError("expected exactly 3 tags")

    result = asyncio.run(
        llm_call_structured(
            command="ask",
            user="return tags",
            schema={"required": ["tags"]},
            validator=validator,
            transport=transport,
        )
    )

    assert result == {"tags": ["a", "b", "c"]}
    assert "Previous response was invalid" in prompts[-1]


def test_llm_fresh_context_logs_single_user_message(tmp_path, monkeypatch):
    log_path = tmp_path / "llm.jsonl"
    monkeypatch.setenv("KUBLAI_LLM_REQUEST_LOG", str(log_path))

    asyncio.run(
        llm_call_fresh_context(
            command="research_lens",
            system="system prompt",
            user="single fresh prompt",
            transport=lambda **request: "ok",
        )
    )

    request = json.loads(log_path.read_text().splitlines()[0])
    assert "user" not in request
    assert "system" not in request
    assert request["user_chars"] == len("single fresh prompt")
    assert request["system_chars"] == len("system prompt")
    assert len(request["user_sha256"]) == 64
    assert len(request["system_sha256"]) == 64
    assert request["model"] == model_for("research_lens")


def test_prompt_registry_hash_is_deterministic_and_content_sensitive(tmp_path):
    prompt_root = tmp_path / ".prompts"
    prompt_root.mkdir()
    prompt = prompt_root / "ask.md"
    prompt.write_text("first", encoding="utf-8")
    registry = PromptRegistry(prompt_root)
    first_hash = registry.hash("ask")
    assert registry.hash("ask") == first_hash
    prompt.write_text("second", encoding="utf-8")
    assert registry.hash("ask") != first_hash


def test_ast_lint_flags_ungrounded_brain_read(tmp_path):
    fixture = tmp_path / "bad.py"
    fixture.write_text(
        "def bad(brain_service):\n"
        "    return brain_service.search('private')\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "lints/no_ungrounded_brain_read.py", str(fixture)],
        cwd=".",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "not sanitizer-grounded" in result.stdout


def test_ast_lint_allows_nearby_sanitizer_call(tmp_path):
    fixture = tmp_path / "good.py"
    fixture.write_text(
        "def good(brain_service, sanitizer):\n"
        "    rows = brain_service.search('public')\n"
        "    return sanitizer.scrub(str(rows), target_class='public', context=None)\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "lints/no_ungrounded_brain_read.py", str(fixture)],
        cwd=".",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
