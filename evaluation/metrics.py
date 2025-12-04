"""Metrics calculation for evaluation results."""

from collections import defaultdict

from .models import (
    ClassificationMetrics,
    ClassificationResult,
    PerformanceMetrics,
    SuggestionMetrics,
    SuggestionResult,
    TestCaseResult,
)


def calculate_classification_metrics(results: list[ClassificationResult]) -> ClassificationMetrics:
    """Calculate aggregate classification metrics."""
    if not results:
        return ClassificationMetrics(
            total_cases=0,
            severity_accuracy=0.0,
            stage_accuracy=0.0,
            complexity_accuracy=0.0,
            overall_accuracy=0.0,
        )

    total = len(results)

    # Count correct predictions
    severity_correct = sum(1 for r in results if r.severity_correct)
    stage_correct = sum(1 for r in results if r.stage_correct)
    complexity_correct = sum(1 for r in results if r.complexity_correct)
    all_correct = sum(1 for r in results if r.all_correct)

    # Calculate accuracy by stage
    accuracy_by_stage: dict[str, float] = {}
    by_stage: dict[str, list[ClassificationResult]] = defaultdict(list)
    for r in results:
        by_stage[r.expected_stage].append(r)

    for stage, stage_results in by_stage.items():
        correct = sum(1 for r in stage_results if r.all_correct)
        accuracy_by_stage[stage] = correct / len(stage_results) if stage_results else 0.0

    # Calculate accuracy by severity
    accuracy_by_severity: dict[str, float] = {}
    by_severity: dict[str, list[ClassificationResult]] = defaultdict(list)
    for r in results:
        by_severity[r.expected_severity].append(r)

    for severity, severity_results in by_severity.items():
        correct = sum(1 for r in severity_results if r.all_correct)
        accuracy_by_severity[severity] = (
            correct / len(severity_results) if severity_results else 0.0
        )

    return ClassificationMetrics(
        total_cases=total,
        severity_accuracy=severity_correct / total,
        stage_accuracy=stage_correct / total,
        complexity_accuracy=complexity_correct / total,
        overall_accuracy=all_correct / total,
        accuracy_by_stage=accuracy_by_stage,
        accuracy_by_severity=accuracy_by_severity,
    )


def calculate_suggestion_metrics(results: list[SuggestionResult]) -> SuggestionMetrics:
    """Calculate aggregate suggestion quality metrics."""
    if not results:
        return SuggestionMetrics(
            total_cases=0,
            avg_root_cause_score=0.0,
            avg_fix_quality_score=0.0,
            avg_overall_score=0.0,
        )

    total = len(results)

    # Calculate averages
    avg_root_cause = sum(r.root_cause_score for r in results) / total
    avg_fix_quality = sum(r.fix_quality_score for r in results) / total
    avg_overall = sum(r.overall_score for r in results) / total

    # Count by quality tier
    high_quality = sum(1 for r in results if r.overall_score >= 0.8)
    medium_quality = sum(1 for r in results if 0.5 <= r.overall_score < 0.8)
    low_quality = sum(1 for r in results if r.overall_score < 0.5)

    return SuggestionMetrics(
        total_cases=total,
        avg_root_cause_score=avg_root_cause,
        avg_fix_quality_score=avg_fix_quality,
        avg_overall_score=avg_overall,
        high_quality_count=high_quality,
        medium_quality_count=medium_quality,
        low_quality_count=low_quality,
    )


def calculate_performance_metrics(results: list[TestCaseResult]) -> PerformanceMetrics:
    """Calculate performance timing metrics."""
    if not results:
        return PerformanceMetrics(
            total_cases=0,
            avg_response_time_ms=0.0,
            min_response_time_ms=0.0,
            max_response_time_ms=0.0,
            p95_response_time_ms=0.0,
        )

    times = [r.response_time_ms for r in results]
    times_sorted = sorted(times)

    # Calculate percentile
    p95_index = int(len(times_sorted) * 0.95)
    p95 = times_sorted[min(p95_index, len(times_sorted) - 1)]

    return PerformanceMetrics(
        total_cases=len(results),
        avg_response_time_ms=sum(times) / len(times),
        min_response_time_ms=min(times),
        max_response_time_ms=max(times),
        p95_response_time_ms=p95,
    )


def identify_failures(results: list[TestCaseResult]) -> tuple[list[str], list[str]]:
    """Identify failed classifications and low-quality suggestions.

    Returns:
        Tuple of (failed_classification_ids, low_quality_suggestion_ids)
    """
    failed_classifications = [r.test_case_id for r in results if not r.classification.all_correct]

    low_quality_suggestions = [r.test_case_id for r in results if r.suggestion.overall_score < 0.5]

    return failed_classifications, low_quality_suggestions


def generate_confusion_matrix(
    results: list[ClassificationResult],
    dimension: str,
) -> dict[str, dict[str, int]]:
    """Generate a confusion matrix for a classification dimension.

    Args:
        results: List of classification results
        dimension: One of 'severity', 'stage', 'complexity'

    Returns:
        Nested dict: matrix[expected][predicted] = count
    """
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for r in results:
        expected = getattr(r, f"expected_{dimension}")
        predicted = getattr(r, f"predicted_{dimension}")
        matrix[expected][predicted] += 1

    # Convert to regular dict
    return {k: dict(v) for k, v in matrix.items()}


def format_confusion_matrix(matrix: dict[str, dict[str, int]], title: str) -> str:
    """Format confusion matrix as a string for display."""
    if not matrix:
        return f"{title}: No data"

    # Get all labels
    all_labels = sorted(set(matrix.keys()) | {label for row in matrix.values() for label in row})

    # Build header
    lines = [f"\n{title}"]
    lines.append("-" * (15 + 10 * len(all_labels)))

    # Header row
    header = "Expected".ljust(15) + "".join(lbl[:8].center(10) for lbl in all_labels)
    lines.append(header)
    lines.append("-" * (15 + 10 * len(all_labels)))

    # Data rows
    for expected in all_labels:
        row_data = matrix.get(expected, {})
        row = expected[:14].ljust(15)
        for predicted in all_labels:
            count = row_data.get(predicted, 0)
            row += str(count).center(10)
        lines.append(row)

    return "\n".join(lines)
