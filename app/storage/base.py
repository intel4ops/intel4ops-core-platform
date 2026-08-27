from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Protocol


class StorageWriteResult:
    """Result of a completed streaming write."""

    __slots__ = ("reference", "size_bytes", "checksum")

    def __init__(self, reference: str, size_bytes: int, checksum: str) -> None:
        self.reference = reference
        self.size_bytes = size_bytes
        self.checksum = checksum


class StorageBackend(Protocol):
    """Provider-agnostic durable byte storage. Streaming, not full-buffer,
    so a large artifact (e.g. a GPS export) is never fully loaded into
    application memory at once. Implementations must generate their own
    storage keys -- callers never control the physical path with a client-
    supplied filename (closes path-traversal risk).

    write_stream computes the checksum incrementally while writing and is
    expected to be atomic: if the caller's registration transaction fails
    after a write, the caller is responsible for invoking cleanup(reference)
    so no orphaned file is left behind.
    """

    def write_stream(self, key: str, chunks: Iterable[bytes]) -> StorageWriteResult: ...

    def open_stream(self, reference: str) -> Iterator[bytes]: ...

    def cleanup(self, reference: str) -> None: ...
