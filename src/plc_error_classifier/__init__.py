"""PLC Error Classifier - AI system for classifying PLC compilation errors."""

from .api import app
from .classifier import classify, classify_sync
from .models import (
    ClassifierOutput,
    ClassifyRequest,
    ClassifyResponse,
    ErrorClassification,
    FixSuggestion,
)

__all__ = [
    "ClassifierOutput",
    "ClassifyRequest",
    "ClassifyResponse",
    "ErrorClassification",
    "FixSuggestion",
    "app",
    "classify",
    "classify_sync",
]


def main() -> None:
    """CLI entry point."""
    print("PLC Error Classifier")
    print("Usage: Import and use classify() or classify_sync()")
    print()
    print("Example:")
    print("  from plc_error_classifier import classify_sync, ClassifyRequest")
    print("  request = ClassifyRequest(error_log='...')")
    print("  response = classify_sync(request)")
