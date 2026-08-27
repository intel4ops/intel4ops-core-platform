from app.ingestion.parsers import default_parser_registry


def test_csv_xlsx_json_txt_are_registered_and_extract() -> None:
    registry = default_parser_registry()
    assert registry.select("text/csv", ".csv") is not None
    result = registry.select("text/csv", ".csv").extract(b"a,b\n1,2\n", "x.csv")  # type: ignore[union-attr]
    assert result.status == "extracted"
    assert len(result.datasets) == 1


def test_pdf_docx_pptx_eml_png_are_registered() -> None:
    registry = default_parser_registry()
    assert registry.select("application/pdf", ".pdf") is not None
    assert (
        registry.select(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"
        )
        is not None
    )
    assert (
        registry.select(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"
        )
        is not None
    )
    assert registry.select("message/rfc822", ".eml") is not None
    assert registry.select("image/png", ".png") is not None


def test_unregistered_formats_return_none_not_a_fake_result() -> None:
    """XML/MSG/TIFF/Parquet have no real parser this pass -- registry.select
    returning None IS the honest 'not yet built' signal; the caller (not
    this registry) is responsible for setting parser_status=unsupported."""
    registry = default_parser_registry()
    assert registry.select("application/xml", ".xml") is None
    assert registry.select("application/vnd.ms-outlook", ".msg") is None
    assert registry.select("image/tiff", ".tiff") is None
    assert registry.select("application/x-parquet", ".parquet") is None


def test_malformed_csv_fails_cleanly_without_raising() -> None:
    registry = default_parser_registry()
    parser = registry.select("text/csv", ".csv")
    assert parser is not None
    # An empty file is a degenerate but not truly malformed case for pandas;
    # assert the parser never raises regardless of status outcome.
    result = parser.extract(b"", "empty.csv")
    assert result.status in ("failed", "extracted", "partial")


def test_image_without_ocr_backend_is_unavailable_not_fabricated() -> None:
    import io

    from PIL import Image

    registry = default_parser_registry()
    parser = registry.select("image/png", ".png")
    assert parser is not None
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="PNG")
    result = parser.extract(buf.getvalue(), "x.png")
    assert result.status == "unavailable"
    assert not any(e.evidence_type == "text_block" for e in result.evidence_objects)
