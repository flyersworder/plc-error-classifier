"""Evaluation framework for PLC Error Classifier.

This module provides:
- Synthetic test case generation
- LLM-as-judge for suggestion quality evaluation
- Classification and suggestion metrics
- Evaluation runner and reporting
"""

from .generator import (
    ERROR_PATTERNS,
    ErrorPattern,
    SyntheticTestGenerator,
)
from .judge import SuggestionJudge, evaluate_batch
from .metrics import (
    calculate_classification_metrics,
    calculate_performance_metrics,
    calculate_suggestion_metrics,
    format_confusion_matrix,
    generate_confusion_matrix,
    identify_failures,
)
from .models import (
    ClassificationMetrics,
    ClassificationResult,
    EvaluationReport,
    ExpectedClassification,
    ExpectedFix,
    PerformanceMetrics,
    SuggestionMetrics,
    SuggestionResult,
    TestCase,
    TestCaseResult,
    TestSuite,
)
from .run_eval import EvaluationRunner, format_report

__all__ = [
    "ERROR_PATTERNS",
    "ClassificationMetrics",
    "ClassificationResult",
    "ErrorPattern",
    "EvaluationReport",
    "EvaluationRunner",
    "ExpectedClassification",
    "ExpectedFix",
    "PerformanceMetrics",
    "SuggestionJudge",
    "SuggestionMetrics",
    "SuggestionResult",
    "SyntheticTestGenerator",
    "TestCase",
    "TestCaseResult",
    "TestSuite",
    "calculate_classification_metrics",
    "calculate_performance_metrics",
    "calculate_suggestion_metrics",
    "evaluate_batch",
    "format_confusion_matrix",
    "format_report",
    "generate_confusion_matrix",
    "identify_failures",
]
