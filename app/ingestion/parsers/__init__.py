from app.ingestion.parser_registry import ArtifactParserRegistry
from app.ingestion.parsers.csv_parser import CsvParser
from app.ingestion.parsers.email_parser import EmailParser
from app.ingestion.parsers.excel_parser import ExcelParser
from app.ingestion.parsers.image_parser import ImageParser
from app.ingestion.parsers.json_parser import JsonParser
from app.ingestion.parsers.pdf_parser import PdfParser
from app.ingestion.parsers.powerpoint_parser import PowerPointParser
from app.ingestion.parsers.txt_parser import TxtParser
from app.ingestion.parsers.word_parser import WordParser


def default_parser_registry() -> ArtifactParserRegistry:
    """Real parsers registered here, in order. No parser is registered for
    XML/MSG/TIFF/Parquet/other formats this pass -- registry.select()
    returning None for them is the honest "not yet built" signal (never a
    fake stub)."""
    registry = ArtifactParserRegistry()
    for parser in (
        CsvParser(),
        ExcelParser(),
        JsonParser(),
        TxtParser(),
        PdfParser(),
        WordParser(),
        PowerPointParser(),
        EmailParser(),
        ImageParser(),
    ):
        registry.register(parser)
    return registry


__all__ = [
    "CsvParser",
    "ExcelParser",
    "JsonParser",
    "TxtParser",
    "PdfParser",
    "WordParser",
    "PowerPointParser",
    "EmailParser",
    "ImageParser",
    "default_parser_registry",
]
