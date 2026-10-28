from enum import StrEnum


class DocumentType(StrEnum):
    """Identification document type of a Subject (Spanish tax context)."""

    CIF = "CIF"
    NIF = "NIF"
    OTHER = "OTHER"
