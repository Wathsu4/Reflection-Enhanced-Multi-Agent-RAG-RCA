"""ChromaDB-backed incident memory.

A thin wrapper around `chromadb.PersistentClient` that knows about our
incident metadata schema. Every other module in the system reads/writes
the knowledge base through `IncidentMemory`; we never touch ChromaDB
directly elsewhere. That keeps the schema invariants (e.g. metadata
must be JSON-primitive only, `success_score` is clamped to [0, 2]) in
one place.

Phase 6 introduces this. Phases 7+ extend it with reflection-driven
score updates.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.types import EmbeddingFunction
from chromadb.config import Settings as ChromaSettings

from rca_system.settings import settings


@dataclass
class IncidentRecord:
    """One historical incident.

    The fields here mirror the metadata schema written to ChromaDB. Keep
    them all primitives (str / int / float / bool) -- ChromaDB rejects
    nested structures in metadata, which is why `tags` is a comma-
    separated string rather than a list.
    """

    incident_id: str
    title: str
    severity: str
    root_cause: str
    resolution: str
    tags: str  # comma-separated; e.g. "redis,network,connection"
    success_score: float = 1.0
    usage_count: int = 0
    last_used_ts: float = 0.0
    added_ts: float = 0.0

    def to_document(self) -> str:
        """Natural-language form of this incident, used as the embedding
        input. Including the structured fields here means the embedding
        captures both the human-readable narrative and the categorical
        attributes (severity, tags) that are otherwise only in metadata.
        """
        return (
            f"Title: {self.title}\n"
            f"Severity: {self.severity}\n"
            f"Root cause: {self.root_cause}\n"
            f"Resolution: {self.resolution}\n"
            f"Tags: {self.tags}"
        )


@dataclass
class _QueryHit:
    """Internal type used only as a return-shape contract; consumers see
    plain dicts for ergonomics with ADK tool calls."""

    incident_id: str
    document: str
    metadata: dict[str, Any]
    distance: float
    similarity: float


class IncidentMemory:
    """Persistent vector store of past incidents.

    Construction is cheap apart from the *first* call, which downloads
    the default embedding model (~90 MB) on demand. Tests should pass a
    deterministic `embedding_function` to skip the download.
    """

    def __init__(
        self,
        *,
        persist_dir: str | Path | None = None,
        collection_name: str | None = None,
        embedding_function: EmbeddingFunction | None = None,
    ) -> None:
        # Allow the dir / name to be overridden so tests can use a tmp
        # path without bleeding into the prod collection.
        path = Path(persist_dir) if persist_dir else Path(settings.chroma_persist_dir)
        path.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(path),
            # Disable the anonymous telemetry ping; this is a research
            # project and we don't want network noise on first-run.
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # Cosine is the right space for sentence-embedding similarity;
        # ChromaDB's default is L2 which would invalidate the
        # `similarity = 1 - distance` arithmetic we use downstream.
        kwargs: dict[str, Any] = {
            "name": collection_name or settings.chroma_collection,
            "metadata": {"hnsw:space": "cosine"},
        }
        if embedding_function is not None:
            kwargs["embedding_function"] = embedding_function

        self._collection = self._client.get_or_create_collection(**kwargs)

    # ---------- write side ----------

    def add(
        self,
        record: IncidentRecord,
        document_text: str | None = None,
    ) -> None:
        """Insert or update one record. Idempotent on `incident_id`.

        `document_text` lets callers embed a richer body (e.g. the full
        markdown narrative) than the dataclass's `to_document()` form.
        """
        if record.added_ts == 0.0:
            record.added_ts = time.time()

        self._collection.upsert(
            ids=[record.incident_id],
            documents=[document_text or record.to_document()],
            metadatas=[asdict(record)],
        )

    def update_score(self, incident_id: str, delta: float) -> None:
        """Adjust `success_score` by `delta`, clamped to [0.0, 2.0].

        The reflection agent (Phase 7) calls this after judging whether
        a retrieved incident actually helped solve the new one. Boosts
        on success, penalises on irrelevance.
        """
        res = self._collection.get(
            ids=[incident_id], include=["metadatas"]
        )
        if not res["ids"]:
            return
        meta = dict(res["metadatas"][0])
        new_score = max(
            0.0, min(2.0, float(meta.get("success_score", 1.0)) + delta)
        )
        meta["success_score"] = new_score
        self._collection.update(ids=[incident_id], metadatas=[meta])

    def mark_retrieved(self, incident_ids: list[str]) -> None:
        """Increment `usage_count` and stamp `last_used_ts` for the
        given ids. Called by the retrieval tool every time it returns
        a hit, so we have a "popularity" signal for analytics."""
        if not incident_ids:
            return
        res = self._collection.get(ids=incident_ids, include=["metadatas"])
        if not res["ids"]:
            return
        now = time.time()
        updated = []
        for meta in res["metadatas"]:
            m = dict(meta)
            m["usage_count"] = int(m.get("usage_count", 0)) + 1
            m["last_used_ts"] = now
            updated.append(m)
        self._collection.update(ids=res["ids"], metadatas=updated)

    # ---------- read side ----------

    def query(self, query_text: str, k: int = 5) -> list[dict]:
        """Top-`k` semantic search.

        Returns plain dicts with `incident_id`, `document`, `metadata`,
        `distance` (cosine), `similarity` (= 1 - distance). The list is
        sorted by similarity descending (ChromaDB already returns it in
        that order).
        """
        res = self._collection.query(
            query_texts=[query_text],
            n_results=k,
            include=["metadatas", "documents", "distances"],
        )

        # ChromaDB returns a list-of-lists keyed on the (single) input
        # query. Flatten the inner list.
        ids = (res.get("ids") or [[]])[0]
        metadatas = (res.get("metadatas") or [[]])[0] or []
        documents = (res.get("documents") or [[]])[0] or []
        distances = (res.get("distances") or [[]])[0] or []

        hits: list[dict] = []
        for incident_id, meta, doc, dist in zip(
            ids, metadatas, documents, distances
        ):
            hits.append(
                {
                    "incident_id": incident_id,
                    "document": doc,
                    "metadata": dict(meta) if meta else {},
                    "distance": float(dist),
                    "similarity": 1.0 - float(dist),
                }
            )
        return hits

    def count(self) -> int:
        return self._collection.count()
