"""Tests for the seeder script.

Verifies:
  * Each shipped seed file parses correctly (frontmatter + body).
  * Running the seeder twice does NOT duplicate records (idempotency).
  * Running on a missing or empty seed dir produces a non-zero exit
    code rather than silently succeeding.

We patch `IncidentMemory` inside the seeder module to inject a tmp
chroma directory so the test doesn't write to the prod data dir.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rca_system.memory.chroma_store import IncidentMemory
from scripts import seed_knowledge_base as seeder
from tests._fake_embed import FakeEmbeddingFunction

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHIPPED_SEED_DIR = PROJECT_ROOT / "seed" / "incidents"


@pytest.fixture
def patched_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> IncidentMemory:
    """Inject a tmp-path-backed memory into the seeder."""
    mem_holder = {}

    def make_mem() -> IncidentMemory:
        if "mem" not in mem_holder:
            mem_holder["mem"] = IncidentMemory(
                persist_dir=tmp_path / "chroma",
                collection_name="incident_memory_test",
                embedding_function=FakeEmbeddingFunction(),
            )
        return mem_holder["mem"]

    # The seeder calls `IncidentMemory()` directly; replace the class
    # in its namespace with a callable that returns our shared tmp memory.
    monkeypatch.setattr(seeder, "IncidentMemory", make_mem)
    return make_mem()


# ---------- shipped seeds parse ----------


def test_each_shipped_seed_parses() -> None:
    """If the markdown files in seed/incidents/ go out of date with the
    parser, the seeder will start failing in production. This test
    catches drift on the next CI run."""
    files = list(SHIPPED_SEED_DIR.glob("*.md"))
    assert len(files) >= 6, (
        f"Phase 6 spec requires >=6 seed incidents; found {len(files)}"
    )
    for path in files:
        meta, body = seeder.parse_markdown(path)
        assert meta["incident_id"]
        assert body  # non-empty narrative


def test_parse_rejects_missing_frontmatter(tmp_path: Path) -> None:
    bad = tmp_path / "bad.md"
    bad.write_text("just a body, no frontmatter")
    with pytest.raises(ValueError, match="frontmatter"):
        seeder.parse_markdown(bad)


def test_parse_rejects_missing_required_field(tmp_path: Path) -> None:
    bad = tmp_path / "bad.md"
    bad.write_text(
        "---\n"
        "incident_id: x\n"
        "title: t\n"
        # severity, root_cause, resolution, tags missing
        "---\n"
        "body\n"
    )
    with pytest.raises(ValueError, match="missing fields"):
        seeder.parse_markdown(bad)


# ---------- end-to-end idempotency ----------


def test_seeder_loads_all_shipped_files(
    patched_memory: IncidentMemory, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = seeder.main([])
    assert rc == 0
    expected = len(list(SHIPPED_SEED_DIR.glob("*.md")))
    assert patched_memory.count() == expected


def test_seeder_is_idempotent(
    patched_memory: IncidentMemory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Running the seeder twice is the most important contract:
    deployments and CI both run it on every push."""
    expected = len(list(SHIPPED_SEED_DIR.glob("*.md")))
    seeder.main([])
    assert patched_memory.count() == expected
    seeder.main([])
    assert patched_memory.count() == expected, (
        "Seeder duplicated records on second run -- not idempotent"
    )


# ---------- argv handling ----------


def test_seeder_returns_nonzero_for_missing_dir(
    patched_memory: IncidentMemory, tmp_path: Path
) -> None:
    rc = seeder.main(["--seed-dir", str(tmp_path / "nonexistent")])
    assert rc != 0


def test_seeder_warns_on_empty_dir(
    patched_memory: IncidentMemory, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = seeder.main(["--seed-dir", str(empty)])
    assert rc != 0
