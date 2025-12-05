"""Metrics calculation for evaluation results.

This module provides metrics calculation with optional bootstrap-based
confidence intervals for statistical rigor.

Bootstrap resampling is used to estimate uncertainty in metrics without
making assumptions about the underlying distribution.
"""

import random
from collections import defaultdict
from collections.abc import Callable
from typing import TypeVar

import numpy as np

from .models import (
    ClassificationMetrics,
    ClassificationResult,
    ConfidenceInterval,
    EvalCaseResult,
    PerformanceMetrics,
    SuggestionMetrics,
    SuggestionResult,
)

T = TypeVar("T")

# Default bootstrap parameters
DEFAULT_N_BOOTSTRAP = 1000
DEFAULT_CONFIDENCE_LEVEL = 0.95
DEFAULT_RANDOM_SEED = 42


# ============================================================================
# Bootstrap Core Functions
# ============================================================================


def bootstrap_resample(
    data: list[T],
    statistic_fn: Callable[[list[T]], float],
    n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
) -> ConfidenceInterval:
    """Calculate bootstrap confidence interval for a statistic.

    Uses the percentile method to construct confidence intervals.

    Args:
        data: Original sample data.
        statistic_fn: Function that computes the statistic from a sample.
        n_bootstrap: Number of bootstrap resamples.
        confidence_level: Confidence level (e.g., 0.95 for 95% CI).
        random_seed: Random seed for reproducibility. None for no seeding.

    Returns:
        ConfidenceInterval with point estimate and CI bounds.
    """
    if not data:
        return ConfidenceInterval(
            point_estimate=0.0,
            ci_lower=0.0,
            ci_upper=0.0,
            confidence_level=confidence_level,
            n_bootstrap=n_bootstrap,
            std_error=0.0,
        )

    # Set random seed for reproducibility
    if random_seed is not None:
        random.seed(random_seed)
        np.random.seed(random_seed)

    # Calculate point estimate from original data
    point_estimate = statistic_fn(data)

    # Generate bootstrap samples and calculate statistic for each
    n = len(data)
    bootstrap_stats = []

    for _ in range(n_bootstrap):
        # Resample with replacement
        resample = [data[random.randint(0, n - 1)] for _ in range(n)]
        bootstrap_stats.append(statistic_fn(resample))

    # Calculate percentile-based confidence interval
    alpha = 1 - confidence_level
    lower_percentile = alpha / 2 * 100
    upper_percentile = (1 - alpha / 2) * 100

    bootstrap_array = np.array(bootstrap_stats)
    ci_lower = float(np.percentile(bootstrap_array, lower_percentile))
    ci_upper = float(np.percentile(bootstrap_array, upper_percentile))
    std_error = float(np.std(bootstrap_array, ddof=1))

    return ConfidenceInterval(
        point_estimate=point_estimate,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        confidence_level=confidence_level,
        n_bootstrap=n_bootstrap,
        std_error=std_error,
    )


def bootstrap_proportion(
    successes: int,
    total: int,
    n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
) -> ConfidenceInterval:
    """Calculate bootstrap CI for a proportion (accuracy).

    Creates binary data from success/total counts and bootstraps.

    Args:
        successes: Number of successes.
        total: Total number of trials.
        n_bootstrap: Number of bootstrap resamples.
        confidence_level: Confidence level.
        random_seed: Random seed for reproducibility.

    Returns:
        ConfidenceInterval for the proportion.
    """
    if total == 0:
        return ConfidenceInterval(
            point_estimate=0.0,
            ci_lower=0.0,
            ci_upper=0.0,
            confidence_level=confidence_level,
            n_bootstrap=n_bootstrap,
            std_error=0.0,
        )

    # Create binary data: 1 for success, 0 for failure
    data = [1] * successes + [0] * (total - successes)

    def mean_fn(sample: list[int]) -> float:
        return sum(sample) / len(sample) if sample else 0.0

    return bootstrap_resample(
        data=data,
        statistic_fn=mean_fn,
        n_bootstrap=n_bootstrap,
        confidence_level=confidence_level,
        random_seed=random_seed,
    )


def bootstrap_mean(
    values: list[float],
    n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
) -> ConfidenceInterval:
    """Calculate bootstrap CI for a mean.

    Args:
        values: List of numeric values.
        n_bootstrap: Number of bootstrap resamples.
        confidence_level: Confidence level.
        random_seed: Random seed for reproducibility.

    Returns:
        ConfidenceInterval for the mean.
    """

    def mean_fn(sample: list[float]) -> float:
        return sum(sample) / len(sample) if sample else 0.0

    return bootstrap_resample(
        data=values,
        statistic_fn=mean_fn,
        n_bootstrap=n_bootstrap,
        confidence_level=confidence_level,
        random_seed=random_seed,
    )


def bootstrap_percentile(
    values: list[float],
    percentile: float = 95.0,
    n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    random_seed: int | None = DEFAULT_RANDOM_SEED,
) -> ConfidenceInterval:
    """Calculate bootstrap CI for a percentile (e.g., p95).

    Args:
        values: List of numeric values.
        percentile: The percentile to estimate (0-100).
        n_bootstrap: Number of bootstrap resamples.
        confidence_level: Confidence level.
        random_seed: Random seed for reproducibility.

    Returns:
        ConfidenceInterval for the percentile.
    """

    def percentile_fn(sample: list[float]) -> float:
        if not sample:
            return 0.0
        return float(np.percentile(sample, percentile))

    return bootstrap_resample(
        data=values,
        statistic_fn=percentile_fn,
        n_bootstrap=n_bootstrap,
        confidence_level=confidence_level,
        random_seed=random_seed,
    )


# ============================================================================
# Metrics Calculation Functions
# ============================================================================


def calculate_classification_metrics(
    results: list[ClassificationResult],
    compute_ci: bool = False,
    n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> ClassificationMetrics:
    """Calculate aggregate classification metrics.

    Args:
        results: List of classification results to aggregate.
        compute_ci: If True, compute bootstrap confidence intervals.
        n_bootstrap: Number of bootstrap samples for CI calculation.
        confidence_level: Confidence level for intervals (e.g., 0.95).

    Returns:
        ClassificationMetrics with accuracy values and optional CIs.
    """
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

    # Build base metrics
    metrics = ClassificationMetrics(
        total_cases=total,
        severity_accuracy=severity_correct / total,
        stage_accuracy=stage_correct / total,
        complexity_accuracy=complexity_correct / total,
        overall_accuracy=all_correct / total,
        accuracy_by_stage=accuracy_by_stage,
        accuracy_by_severity=accuracy_by_severity,
    )

    # Compute confidence intervals if requested
    if compute_ci:
        metrics.severity_accuracy_ci = bootstrap_proportion(
            severity_correct, total, n_bootstrap, confidence_level
        )
        metrics.stage_accuracy_ci = bootstrap_proportion(
            stage_correct, total, n_bootstrap, confidence_level
        )
        metrics.complexity_accuracy_ci = bootstrap_proportion(
            complexity_correct, total, n_bootstrap, confidence_level
        )
        metrics.overall_accuracy_ci = bootstrap_proportion(
            all_correct, total, n_bootstrap, confidence_level
        )

    return metrics


def calculate_suggestion_metrics(
    results: list[SuggestionResult],
    compute_ci: bool = False,
    n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> SuggestionMetrics:
    """Calculate aggregate suggestion quality metrics.

    Args:
        results: List of suggestion results to aggregate.
        compute_ci: If True, compute bootstrap confidence intervals.
        n_bootstrap: Number of bootstrap samples for CI calculation.
        confidence_level: Confidence level for intervals (e.g., 0.95).

    Returns:
        SuggestionMetrics with average scores and optional CIs.
    """
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

    # Build base metrics
    metrics = SuggestionMetrics(
        total_cases=total,
        avg_root_cause_score=avg_root_cause,
        avg_fix_quality_score=avg_fix_quality,
        avg_overall_score=avg_overall,
        high_quality_count=high_quality,
        medium_quality_count=medium_quality,
        low_quality_count=low_quality,
    )

    # Compute confidence intervals if requested
    if compute_ci:
        root_cause_scores = [r.root_cause_score for r in results]
        fix_quality_scores = [r.fix_quality_score for r in results]
        overall_scores = [r.overall_score for r in results]

        metrics.root_cause_score_ci = bootstrap_mean(
            root_cause_scores, n_bootstrap, confidence_level
        )
        metrics.fix_quality_score_ci = bootstrap_mean(
            fix_quality_scores, n_bootstrap, confidence_level
        )
        metrics.overall_score_ci = bootstrap_mean(overall_scores, n_bootstrap, confidence_level)

    return metrics


def calculate_performance_metrics(
    results: list[EvalCaseResult],
    compute_ci: bool = False,
    n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> PerformanceMetrics:
    """Calculate performance timing metrics.

    Args:
        results: List of test case results with timing data.
        compute_ci: If True, compute bootstrap confidence intervals.
        n_bootstrap: Number of bootstrap samples for CI calculation.
        confidence_level: Confidence level for intervals (e.g., 0.95).

    Returns:
        PerformanceMetrics with timing statistics and optional CIs.
    """
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

    # Build base metrics
    metrics = PerformanceMetrics(
        total_cases=len(results),
        avg_response_time_ms=sum(times) / len(times),
        min_response_time_ms=min(times),
        max_response_time_ms=max(times),
        p95_response_time_ms=p95,
    )

    # Compute confidence intervals if requested
    if compute_ci:
        metrics.avg_response_time_ci = bootstrap_mean(times, n_bootstrap, confidence_level)
        metrics.p95_response_time_ci = bootstrap_percentile(
            times, percentile=95.0, n_bootstrap=n_bootstrap, confidence_level=confidence_level
        )

    return metrics


def identify_failures(results: list[EvalCaseResult]) -> tuple[list[str], list[str]]:
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


# ============================================================================
# Statistical Formatting Functions
# ============================================================================


def format_ci(ci: ConfidenceInterval | None, as_percent: bool = False) -> str:
    """Format a confidence interval for display.

    Args:
        ci: ConfidenceInterval to format, or None.
        as_percent: If True, format as percentages.

    Returns:
        Formatted string like "85.0% [82.1%, 87.9%]" or "0.85 [0.82, 0.88]".
    """
    if ci is None:
        return "N/A"

    if as_percent:
        return (
            f"{ci.point_estimate * 100:.1f}% "
            f"[{ci.ci_lower * 100:.1f}%, {ci.ci_upper * 100:.1f}%]"
        )
    else:
        return f"{ci.point_estimate:.3f} [{ci.ci_lower:.3f}, {ci.ci_upper:.3f}]"


def format_statistical_summary(
    classification_metrics: ClassificationMetrics,
    suggestion_metrics: SuggestionMetrics,
    performance_metrics: PerformanceMetrics,
) -> str:
    """Format a statistical summary with confidence intervals.

    Args:
        classification_metrics: Classification accuracy metrics.
        suggestion_metrics: Suggestion quality metrics.
        performance_metrics: Performance timing metrics.

    Returns:
        Formatted multi-line string with statistical insights.
    """
    lines = [
        "",
        "=" * 60,
        "STATISTICAL SUMMARY (with 95% Confidence Intervals)",
        "=" * 60,
        "",
        "CLASSIFICATION ACCURACY",
        "-" * 40,
    ]

    # Classification metrics
    if classification_metrics.overall_accuracy_ci:
        lines.append(
            f"  Overall Accuracy:    {format_ci(classification_metrics.overall_accuracy_ci, as_percent=True)}"
        )
        lines.append(
            f"  Severity Accuracy:   {format_ci(classification_metrics.severity_accuracy_ci, as_percent=True)}"
        )
        lines.append(
            f"  Stage Accuracy:      {format_ci(classification_metrics.stage_accuracy_ci, as_percent=True)}"
        )
        lines.append(
            f"  Complexity Accuracy: {format_ci(classification_metrics.complexity_accuracy_ci, as_percent=True)}"
        )
    else:
        lines.append(f"  Overall Accuracy:    {classification_metrics.overall_accuracy:.1%}")
        lines.append("  (Run with compute_ci=True for confidence intervals)")

    lines.extend(
        [
            "",
            "SUGGESTION QUALITY",
            "-" * 40,
        ]
    )

    # Suggestion metrics
    if suggestion_metrics.overall_score_ci:
        lines.append(f"  Avg Root Cause Score: {format_ci(suggestion_metrics.root_cause_score_ci)}")
        lines.append(
            f"  Avg Fix Quality:      {format_ci(suggestion_metrics.fix_quality_score_ci)}"
        )
        lines.append(f"  Avg Overall Score:    {format_ci(suggestion_metrics.overall_score_ci)}")
    else:
        lines.append(f"  Avg Overall Score:   {suggestion_metrics.avg_overall_score:.3f}")
        lines.append("  (Run with compute_ci=True for confidence intervals)")

    lines.extend(
        [
            "",
            "PERFORMANCE",
            "-" * 40,
        ]
    )

    # Performance metrics
    if performance_metrics.avg_response_time_ci:
        avg_ci = performance_metrics.avg_response_time_ci
        p95_ci = performance_metrics.p95_response_time_ci
        lines.append(
            f"  Avg Response Time:   {avg_ci.point_estimate:.0f}ms "
            f"[{avg_ci.ci_lower:.0f}ms, {avg_ci.ci_upper:.0f}ms]"
        )
        if p95_ci:
            lines.append(
                f"  P95 Response Time:   {p95_ci.point_estimate:.0f}ms "
                f"[{p95_ci.ci_lower:.0f}ms, {p95_ci.ci_upper:.0f}ms]"
            )
    else:
        lines.append(f"  Avg Response Time:   {performance_metrics.avg_response_time_ms:.0f}ms")
        lines.append("  (Run with compute_ci=True for confidence intervals)")

    lines.extend(
        [
            "",
            "INTERPRETATION GUIDE",
            "-" * 40,
            "  - CI width indicates measurement uncertainty",
            "  - Narrow CI = precise estimate, Wide CI = more uncertainty",
            "  - Non-overlapping CIs suggest significant differences",
            f"  - Sample size: {classification_metrics.total_cases} test cases",
            "",
            "=" * 60,
        ]
    )

    return "\n".join(lines)


# ============================================================================
# CLI Entry Point
# ============================================================================


def load_results_from_report(
    report_path: str,
) -> tuple[list[ClassificationResult], list[SuggestionResult], list[EvalCaseResult]]:
    """Load results from a saved evaluation report JSON file."""
    import json

    with open(report_path) as f:
        report = json.load(f)

    classification_results = []
    suggestion_results = []
    test_case_results = []

    for r in report["results"]:
        cls = r["classification"]
        classification_results.append(
            ClassificationResult(
                test_case_id=cls["test_case_id"],
                predicted_severity=cls["predicted_severity"],
                predicted_stage=cls["predicted_stage"],
                predicted_complexity=cls["predicted_complexity"],
                expected_severity=cls["expected_severity"],
                expected_stage=cls["expected_stage"],
                expected_complexity=cls["expected_complexity"],
                severity_correct=cls["severity_correct"],
                stage_correct=cls["stage_correct"],
                complexity_correct=cls["complexity_correct"],
                all_correct=cls["all_correct"],
            )
        )

        sug = r["suggestion"]
        suggestion_results.append(
            SuggestionResult(
                test_case_id=sug["test_case_id"],
                predicted_root_cause=sug["predicted_root_cause"],
                predicted_fix_description=sug["predicted_fix_description"],
                confidence=sug["confidence"],
                expected_root_cause=sug["expected_root_cause"],
                expected_fix_description=sug["expected_fix_description"],
                root_cause_score=sug["root_cause_score"],
                fix_quality_score=sug["fix_quality_score"],
                overall_score=sug["overall_score"],
                judge_reasoning=sug["judge_reasoning"],
            )
        )

        test_case_results.append(
            EvalCaseResult(
                test_case_id=r["test_case_id"],
                test_case_name=r["test_case_name"],
                classification=classification_results[-1],
                suggestion=suggestion_results[-1],
                response_time_ms=r["response_time_ms"],
            )
        )

    return classification_results, suggestion_results, test_case_results


def main() -> None:
    """CLI entry point for metrics analysis with confidence intervals."""
    import argparse
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Analyze evaluation results with bootstrap confidence intervals"
    )
    parser.add_argument(
        "report_path",
        nargs="?",
        help="Path to evaluation report JSON (default: latest in reports/)",
    )
    parser.add_argument(
        "--n-bootstrap",
        type=int,
        default=1000,
        help="Number of bootstrap samples (default: 1000)",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.95,
        help="Confidence level (default: 0.95)",
    )
    args = parser.parse_args()

    # Find report file
    if args.report_path:
        report_path = Path(args.report_path)
    else:
        # Find latest report
        reports_dir = Path(__file__).parent / "reports"
        reports = sorted(reports_dir.glob("eval_report_*.json"), reverse=True)
        if not reports:
            print("No evaluation reports found in reports/", file=sys.stderr)
            print("Run: uv run python -m evaluation.run_eval", file=sys.stderr)
            sys.exit(1)
        report_path = reports[0]

    print(f"Loading report: {report_path}")
    print(f"Bootstrap samples: {args.n_bootstrap}")
    print(f"Confidence level: {args.confidence:.0%}")

    # Load results
    classification_results, suggestion_results, test_case_results = load_results_from_report(
        str(report_path)
    )

    print(f"Loaded {len(test_case_results)} test case results")
    print()

    # Calculate metrics with CIs
    classification_metrics = calculate_classification_metrics(
        classification_results,
        compute_ci=True,
        n_bootstrap=args.n_bootstrap,
        confidence_level=args.confidence,
    )

    suggestion_metrics = calculate_suggestion_metrics(
        suggestion_results,
        compute_ci=True,
        n_bootstrap=args.n_bootstrap,
        confidence_level=args.confidence,
    )

    performance_metrics = calculate_performance_metrics(
        test_case_results,
        compute_ci=True,
        n_bootstrap=args.n_bootstrap,
        confidence_level=args.confidence,
    )

    # Print statistical summary
    print(
        format_statistical_summary(
            classification_metrics,
            suggestion_metrics,
            performance_metrics,
        )
    )

    # Print confusion matrices
    print("\n" + "=" * 60)
    print("CONFUSION MATRICES")
    print("=" * 60)

    for dim in ["severity", "stage", "complexity"]:
        matrix = generate_confusion_matrix(classification_results, dim)
        print(format_confusion_matrix(matrix, f"Confusion Matrix: {dim.upper()}"))


if __name__ == "__main__":
    main()
