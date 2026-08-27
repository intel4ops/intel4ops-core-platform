from __future__ import annotations

from email import message_from_bytes
from email.message import Message

from app.ingestion.extraction_contract import (
    ArtifactExtractionResult,
    ChildArtifact,
    ExtractedEvidence,
)


def _extract_body(message: Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return ""
    payload = message.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode(message.get_content_charset() or "utf-8", errors="replace")
    return str(payload or "")


class EmailParser:
    """Python stdlib email module -- no new dependency. Attachments become
    ChildArtifact entries, which the orchestrator registers as child
    SourceArtifact rows (parent_artifact_id set) and re-runs through the
    same parser-selection pipeline."""

    code = "eml"
    version = "1.0"

    def supports(self, mime_type: str, extension: str) -> bool:
        return extension.lower() == ".eml" or mime_type == "message/rfc822"

    def extract(self, raw_bytes: bytes, filename: str) -> ArtifactExtractionResult:
        try:
            message = message_from_bytes(raw_bytes)
        except Exception as exc:  # noqa: BLE001
            return ArtifactExtractionResult(
                parser_code=self.code,
                parser_version=self.version,
                status="failed",
                warnings=[f"Email parse failed: {exc}"],
            )
        metadata: dict[str, object] = {
            "sender": message.get("From"),
            "recipients": message.get("To"),
            "timestamp": message.get("Date"),
            "subject": message.get("Subject"),
        }
        body = _extract_body(message)
        evidence = [
            ExtractedEvidence(
                evidence_type="text_block", content=body, lineage={"section": "body"}
            ),
            ExtractedEvidence(evidence_type="metadata", content=str(metadata), lineage=metadata),
        ]
        children = []
        if message.is_multipart():
            for part in message.walk():
                filename_attach = part.get_filename()
                if not filename_attach:
                    continue
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    children.append(
                        ChildArtifact(
                            filename=filename_attach,
                            mime_type=part.get_content_type(),
                            content=payload,
                        )
                    )
        return ArtifactExtractionResult(
            parser_code=self.code,
            parser_version=self.version,
            status="extracted",
            evidence_objects=evidence,
            child_artifacts=children,
            extraction_metadata=metadata,
        )
