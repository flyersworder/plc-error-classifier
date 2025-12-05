"""Evaluation framework for PLC Error Classifier.

This module provides:
- Synthetic test case generation
- LLM-as-judge for suggestion quality evaluation
- Classification and suggestion metrics
- Evaluation runner and reporting
"""

# Note: Imports are structured to avoid RuntimeWarning when running modules as __main__
# Modules with CLI entry points (generator.py, run_eval.py, metrics.py) should be
# imported directly when needed, not through __init__.py

from .judge import SuggestionJudge, evaluate_batch
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
from .patterns import ERROR_PATTERNS, ErrorPattern

__all__ = [
    "ERROR_PATTERNS",
    "ClassificationMetrics",
    "ClassificationResult",
    "ErrorPattern",
    "EvaluationReport",
    "ExpectedClassification",
    "ExpectedFix",
    "PerformanceMetrics",
    "SuggestionJudge",
    "SuggestionMetrics",
    "SuggestionResult",
    "TestCase",
    "TestCaseResult",
    "TestSuite",
    "evaluate_batch",
]

# For CLI modules, import directly:
#   from evaluation.generator import SyntheticTestGenerator
#   from evaluation.run_eval import EvaluationRunner, format_report
#   from evaluation.metrics import calculate_classification_metrics, ...
