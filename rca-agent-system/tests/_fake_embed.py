"""A deterministic fake embedding function for tests.

The real default (`all-MiniLM-L6-v2`) downloads ~90MB on first use and
adds noticeable latency to every test. We don't actually need semantic
correctness in unit tests -- we just need *something* that maps text
deterministically into a fixed-size vector so ChromaDB's index works.

The fake hashes each input to a small float vector. Identical strings
map to identical vectors; nearly-identical strings (e.g. one extra
word) map to *different* vectors -- which is fine because tests that
care about semantic similarity should be integration tests, not unit
tests.
"""

from __future__ import annotations

import hashlib
from typing import Any


class FakeEmbeddingFunction:
    """16-dim deterministic hash embeddings for tests.

    ChromaDB calls this with a list of strings and expects a list of
    list[float]. The class is also required by chromadb 1.x to expose a
    handful of metadata helpers (`name`, `is_legacy`, etc.) so that the
    collection can persist its embedding-function identity to disk.
    """

    DIM = 16

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        out: list[list[float]] = []
        for text in input:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            # Map each byte (0..255) to a float in [-1, 1] so vectors
            # are not all-positive (cosine similarity becomes useless
            # when every vector lies in the same orthant).
            vec = [(b - 128) / 128.0 for b in digest[: self.DIM]]
            out.append(vec)
        return out

    # chromadb 1.x dispatches separately for "embed this query" vs
    # "embed these documents". Both go through the same hash logic;
    # only their normalised input shape differs.
    def embed_query(self, input: list[str] | str) -> list[list[float]]:  # noqa: A002
        items = [input] if isinstance(input, str) else list(input)
        return self(items)

    def embed_documents(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return self(list(input))

    # ----- chromadb 1.x metadata API -----

    @staticmethod
    def name() -> str:
        return "fake-sha256"

    def is_legacy(self) -> bool:
        return False

    def get_config(self) -> dict[str, Any]:
        return {}

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]

    @staticmethod
    def build_from_config(_cfg: dict[str, Any]) -> "FakeEmbeddingFunction":
        return FakeEmbeddingFunction()
