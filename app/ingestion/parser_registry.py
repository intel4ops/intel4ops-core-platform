from __future__ import annotations

from typing import Protocol

from app.ingestion.extraction_contract import ArtifactExtractionResult


class ArtifactParser(Protocol):
    code: str
    version: str

    def supports(self, mime_type: str, extension: str) -> bool: ...

    def extract(self, raw_bytes: bytes, filename: str) -> ArtifactExtractionResult: ...


class ArtifactParserRegistry:
    """Modeled on this codebase's existing EngineRegistry/TrustRuleRegistry
    pattern. registry.select() returning None IS the honest "no parser
    exists for this format yet" signal -- callers must never fabricate a
    result for an unregistered format."""

    def __init__(self) -> None:
        self._parsers: list[ArtifactParser] = []

    def register(self, parser: ArtifactParser) -> None:
        self._parsers.append(parser)

    def select(self, mime_type: str, extension: str) -> ArtifactParser | None:
        for parser in self._parsers:
            if parser.supports(mime_type, extension):
                return parser
        return None
