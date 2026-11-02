"""RequirementDelta: local, evidence-traceable requirement change review."""

from .evidence import Evidence, build_evidence, locate_quote, verify_evidence
from .ingest import DocumentSnapshot, read_document, read_pair
from .changes import Comparison, Change, FieldChange, analyze

__version__ = "0.1.0"

__all__ = [
    "Comparison",
    "Change",
    "FieldChange",
    "analyze",
    "DocumentSnapshot",
    "Evidence",
    "build_evidence",
    "locate_quote",
    "read_document",
    "read_pair",
    "verify_evidence",
]
