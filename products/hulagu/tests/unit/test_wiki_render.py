from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from uuid import UUID

import pytest

from hulagu.wiki.model import PublicationRequest, RenderedWiki, WikiPage
from hulagu.wiki.render import render_wiki, validate_rendered


def request() -> PublicationRequest:
    return PublicationRequest(
        tenant_id=UUID("70000000-0000-4000-8000-000000000001"),
        run_id=UUID("71000000-0000-4000-8000-000000000001"),
        profile_id=UUID("72000000-0000-4000-8000-000000000001"),
        lifecycle_epoch=2,
        work_epoch=3,
        profile_version=4,
        manifest_input_digest="a" * 64,
    )


def pages(*, title: str = "Synthetic Engineer") -> tuple[WikiPage, ...]:
    return (
        WikiPage("index.md", "Results", "See [[profile]] and [[jobs/job-1]]."),
        WikiPage("profile.md", "Profile", "Confirmed profile version 4."),
        WikiPage("searches/run-1.md", "Search", "Bounded fixture search."),
        WikiPage("jobs/job-1.md", title, "Fixture evidence only."),
        WikiPage("decisions.md", "Decisions", "No decisions yet."),
    )


def remanifest(rendered: RenderedWiki, manifest: dict[str, object]) -> RenderedWiki:
    files = dict(rendered.files)
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    files["manifest.json"] = manifest_bytes
    return RenderedWiki(tuple(sorted(files.items())), hashlib.sha256(manifest_bytes).hexdigest())


def test_render_is_deterministic_and_manifest_binds_authority() -> None:
    first = render_wiki(request(), pages(), generation=1, publication_sequence=7)
    second = render_wiki(request(), pages(), generation=1, publication_sequence=7)

    assert first == second
    files = dict(first.files)
    manifest = json.loads(files["manifest.json"])
    assert manifest["schema_version"] == "HulaguWikiManifest/v1"
    assert manifest["generation"] == 1
    assert manifest["publication_sequence"] == 7
    assert manifest["manifest_input_digest"] == "a" * 64
    assert manifest["files"] == sorted(manifest["files"], key=lambda item: item["path"])
    validate_rendered(first)


@pytest.mark.parametrize("path", ["../escape.md", "/absolute.md", "jobs/../../escape.md", "jobs\\escape.md", "CURRENT"])
def test_render_rejects_non_canonical_or_reserved_page_paths(path: str) -> None:
    with pytest.raises(ValueError, match="page path"):
        render_wiki(request(), (WikiPage(path, "Bad", "body"),), generation=1, publication_sequence=1)


def test_render_rejects_invalid_or_missing_wikilinks() -> None:
    with pytest.raises(ValueError, match="wikilink"):
        render_wiki(
            request(),
            (WikiPage("index.md", "Bad", "See [[../outside]] and [[missing]]."),),
            generation=1,
            publication_sequence=1,
        )


def test_render_requires_complete_private_wiki_shape() -> None:
    with pytest.raises(ValueError, match="wiki shape"):
        render_wiki(
            request(),
            (WikiPage("index.md", "Incomplete", "Only an index."),),
            generation=1,
            publication_sequence=1,
        )


def test_manifest_validation_rejects_tampering_and_unknown_entries() -> None:
    rendered = render_wiki(request(), pages(), generation=1, publication_sequence=1)
    files = dict(rendered.files)
    files["jobs/job-1.md"] = b"tampered"
    tampered = replace(rendered, files=tuple(sorted(files.items())))
    with pytest.raises(ValueError, match="manifest"):
        validate_rendered(tampered)

    manifest = json.loads(dict(rendered.files)["manifest.json"])
    manifest["unexpected"] = True
    files = dict(rendered.files)
    files["manifest.json"] = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    malformed = RenderedWiki(tuple(sorted(files.items())), rendered.manifest_digest)
    with pytest.raises(ValueError, match="manifest"):
        validate_rendered(malformed)


def test_manifest_validation_requires_complete_private_wiki_shape() -> None:
    rendered = render_wiki(request(), pages(), generation=1, publication_sequence=1)
    files = {path: payload for path, payload in rendered.files if path in {"index.md", "manifest.json"}}
    files["index.md"] = b"---\ntitle: Results\n---\n\nOnly an index.\n"
    manifest = json.loads(files["manifest.json"])
    manifest["files"] = [entry for entry in manifest["files"] if entry["path"] == "index.md"]
    manifest["files"][0]["bytes"] = len(files["index.md"])
    manifest["files"][0]["sha256"] = hashlib.sha256(files["index.md"]).hexdigest()
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    files["manifest.json"] = manifest_bytes
    incomplete = RenderedWiki(tuple(sorted(files.items())), hashlib.sha256(manifest_bytes).hexdigest())

    with pytest.raises(ValueError, match="wiki shape"):
        validate_rendered(incomplete)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", "not-a-uuid"),
        ("run_id", "71000000-0000-1000-8000-000000000001"),
        ("profile_id", 7),
        ("profile_version", True),
        ("lifecycle_epoch", -1),
        ("work_epoch", "3"),
        ("manifest_input_digest", "A" * 64),
        ("generation", 0),
        ("publication_sequence", True),
    ],
)
def test_manifest_validation_rejects_malformed_authority_scalars(field: str, value: object) -> None:
    rendered = render_wiki(request(), pages(), generation=1, publication_sequence=1)
    manifest = json.loads(dict(rendered.files)["manifest.json"])
    manifest[field] = value

    with pytest.raises(ValueError, match="manifest"):
        validate_rendered(remanifest(rendered, manifest))
