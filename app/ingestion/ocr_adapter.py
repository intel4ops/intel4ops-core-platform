from __future__ import annotations

from typing import Protocol


class OcrResult:
    __slots__ = ("text", "confidence")

    def __init__(self, text: str, confidence: float) -> None:
        self.text = text
        self.confidence = confidence


class OcrAdapter(Protocol):
    """Modular OCR/text-extraction interface for image artifacts. No
    concrete implementation is wired this pass -- no Tesseract binary is
    confirmed present in this deployment's build, and no cloud OCR
    credential is available. UnavailableOcrAdapter is the default so images
    always register with extraction_status=unavailable rather than a
    fabricated/low-confidence guess. Swapping in a real backend later is a
    config change (register a different adapter instance), not an
    orchestration change."""

    def is_available(self) -> bool: ...

    def extract_text(self, image_bytes: bytes) -> OcrResult: ...


class UnavailableOcrAdapter:
    def is_available(self) -> bool:
        return False

    def extract_text(self, image_bytes: bytes) -> OcrResult:
        raise NotImplementedError("No OCR backend is provisioned in this deployment")
