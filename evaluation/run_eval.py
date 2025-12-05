"""Main evaluation runner for PLC error classifier."""

import asyncio
import os
import random
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai

# Import the actual classifier from the main package
from plc_error_classifier.classifier import classify
from plc_error_classifier.config import CLASSIFIER_MODEL
from plc_error_classifier.models import ClassifyRequest, ClassifyResponse

from .judge import SuggestionJudge
from .metrics import (
    calculate_classification_metrics,
    calculate_performance_metrics,
    calculate_suggestion_metrics,
    format_confusion_matrix,
    generate_confusion_matrix,
    identify_failures,
)
from .models import (
    ClassificationResult,
    EvaluationReport,
    TestCase,
    TestCaseResult,
    TestSuite,
)

# Load environment variables
load_dotenv()

# Rate limiting: max concurrent API requests
MAX_CONCURRENT_REQUESTS = 5


# ============================================================================
# Configuration
# ============================================================================

# Paths
TEST_CASES_DIR = Path(__file__).parent / "test_cases"
REPORTS_DIR = Path(__file__).parent / "reports"


# ============================================================================
# Random XML Hiding for Comprehensive Testing
# ============================================================================

# Seed for reproducibility (can be overridden)
RANDOM_SEED = 42

# Fraction of test cases per category to hide XML (0.5 = 50%)
XML_HIDE_FRACTION = 0.5


def should_hide_xml(test_case_id: str, category: str, seed: int = RANDOM_SEED) -> bool:
    """Determine if XML should be hidden for a test case.

    Uses a deterministic random selection based on test case ID and category
    to ensure reproducibility across runs.

    Args:
        test_case_id: Unique identifier for the test case.
        category: Error category of the test case.
        seed: Random seed for reproducibility.

    Returns:
        True if XML should be hidden for this test case.
    """
    # Create a deterministic hash for this test case
    rng = random.Random(f"{seed}:{category}:{test_case_id}")
    return rng.random() < XML_HIDE_FRACTION


async def classify_error(
    error_log: str,
    source_xml: str | None = None,
) -> ClassifyResponse:
    """Classify an error using the actual classifier.

    This is a thin wrapper around the real classifier that handles
    the conversion between evaluation and classifier interfaces.

    Args:
        error_log: The build output/error log to classify.
        source_xml: Optional PLCopen XML source for context.

    Returns:
        ClassifyResponse with classification and suggestions.
    """
    request = ClassifyRequest(error_log=error_log, source_xml=source_xml)
    return await classify(request)


# ============================================================================
# Evaluation Runner
# ============================================================================


class EvaluationRunner:
    """Runs evaluation on a test suite with async support."""

    def __init__(self, api_key: str | None = None):
        """Initialize the runner."""
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        self.client = genai.Client(api_key=self.api_key)
        self.judge = SuggestionJudge(api_key=self.api_key)
        self._semaphore: asyncio.Semaphore | None = None

    async def evaluate_test_case(
        self,
        judge_client: genai.Client,
        test_case: TestCase,
        hide_xml: bool = False,
    ) -> TestCaseResult:
        """Evaluate a single test case.

        Args:
            judge_client: Async Gemini client for judge evaluation.
            test_case: The test case to evaluate.
            hide_xml: If True, don't pass source_xml to classifier.

        Returns:
            TestCaseResult with classification and suggestion evaluation.
        """
        # Rate limiting
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        async with self._semaphore:
            # Time the classification
            start_time = time.time()

            # Determine if XML should be hidden for this test case
            source_xml = None if hide_xml else test_case.source_xml

            # Classify the error using the actual classifier
            response = await classify_error(
                test_case.error_log,
                source_xml,
            )

            elapsed_ms = (time.time() - start_time) * 1000

            # Extract predictions from ClassifyResponse
            predicted_severity = response.classification.severity
            predicted_stage = response.classification.stage
            predicted_complexity = response.classification.complexity

            # Get the best suggestion (first one, highest confidence)
            best_suggestion = response.suggestions[0] if response.suggestions else None

            # Build classification result
            expected = test_case.expected_classification
            classification_result = ClassificationResult(
                test_case_id=test_case.id,
                predicted_severity=predicted_severity,
                predicted_stage=predicted_stage,
                predicted_complexity=predicted_complexity,
                expected_severity=expected.severity,
                expected_stage=expected.stage,
                expected_complexity=expected.complexity,
                severity_correct=predicted_severity == expected.severity,
                stage_correct=predicted_stage == expected.stage,
                complexity_correct=predicted_complexity == expected.complexity,
                all_correct=(
                    predicted_severity == expected.severity
                    and predicted_stage == expected.stage
                    and predicted_complexity == expected.complexity
                ),
            )

            # Evaluate suggestion quality with LLM judge
            suggestion_result = await self.judge.evaluate_suggestion(
                aclient=judge_client,
                test_case_id=test_case.id,
                error_log=test_case.error_log,
                expected_fix=test_case.expected_fix,
                predicted_root_cause=best_suggestion.root_cause if best_suggestion else "",
                predicted_fix_description=best_suggestion.fix_description
                if best_suggestion
                else "",
                confidence=best_suggestion.confidence if best_suggestion else 0.5,
            )

            return TestCaseResult(
                test_case_id=test_case.id,
                test_case_name=test_case.name,
                classification=classification_result,
                suggestion=suggestion_result,
                response_time_ms=elapsed_ms,
            )

    async def _evaluate_with_logging(
        self,
        judge_client: genai.Client,
        test_case: TestCase,
        index: int,
        total: int,
        hide_xml: bool = False,
    ) -> TestCaseResult | None:
        """Evaluate a test case with progress logging."""
        try:
            xml_status = " (no XML)" if hide_xml else ""
            result = await self.evaluate_test_case(judge_client, test_case, hide_xml)
            status = "✓" if result.classification.all_correct else "✗"
            print(
                f"  [{index}/{total}] {test_case.name}{xml_status}... {status} ({result.response_time_ms:.0f}ms)"
            )
            return result
        except Exception as e:
            print(f"  [{index}/{total}] {test_case.name}... ERROR: {e}")
            return None

    async def run_evaluation(
        self,
        suite: TestSuite,
        random_xml_hiding: bool = True,
    ) -> EvaluationReport:
        """Run evaluation on entire test suite concurrently.

        Args:
            suite: The test suite to evaluate.
            random_xml_hiding: If True, randomly hide XML for ~50% of test cases
                              per category for comprehensive testing.

        Returns:
            EvaluationReport with all metrics and results.
        """
        # Count how many cases will have XML hidden
        if random_xml_hiding:
            hidden_count = sum(
                1
                for tc in suite.test_cases
                if tc.source_xml and should_hide_xml(tc.id, tc.error_category)
            )
            print(f"Running evaluation on {len(suite.test_cases)} test cases...")
            print(f"  (XML hidden for {hidden_count} cases to test inference quality)")
        else:
            print(f"Running evaluation on {len(suite.test_cases)} test cases...")

        # Use async context for judge only (classifier handles its own client)
        async with self.judge.client.aio as judge_client:
            tasks = []
            for i, test_case in enumerate(suite.test_cases, 1):
                # Determine if XML should be hidden for this test case
                hide_xml = (
                    random_xml_hiding
                    and test_case.source_xml is not None
                    and should_hide_xml(test_case.id, test_case.error_category)
                )
                tasks.append(
                    self._evaluate_with_logging(
                        judge_client,
                        test_case,
                        i,
                        len(suite.test_cases),
                        hide_xml,
                    )
                )
            all_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out None results and exceptions
        results: list[TestCaseResult] = []
        for result in all_results:
            if isinstance(result, Exception):
                print(f"Warning: Task failed with exception: {result}")
            elif result is not None:
                results.append(result)

        # Calculate metrics
        classification_results = [r.classification for r in results]
        suggestion_results = [r.suggestion for r in results]

        classification_metrics = calculate_classification_metrics(classification_results)
        suggestion_metrics = calculate_suggestion_metrics(suggestion_results)
        performance_metrics = calculate_performance_metrics(results)

        # Identify failures
        failed, low_quality = identify_failures(results)

        return EvaluationReport(
            report_name=f"Evaluation Report - {suite.name}",
            timestamp=datetime.now().isoformat(),
            model_used=CLASSIFIER_MODEL,
            test_suite_name=suite.name,
            test_suite_version=suite.version,
            classification_metrics=classification_metrics,
            suggestion_metrics=suggestion_metrics,
            performance_metrics=performance_metrics,
            results=results,
            failed_cases=failed,
            low_quality_suggestions=low_quality,
        )

    def save_report(self, report: EvaluationReport, filename: str | None = None) -> Path:
        """Save evaluation report to file."""
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"eval_report_{timestamp}.json"

        output_path = REPORTS_DIR / filename

        with open(output_path, "w") as f:
            f.write(report.model_dump_json(indent=2))

        return output_path


# ============================================================================
# Report Formatting
# ============================================================================


def format_report(report: EvaluationReport) -> str:
    """Format evaluation report as human-readable text."""
    lines = [
        "=" * 80,
        f"EVALUATION REPORT: {report.report_name}",
        "=" * 80,
        f"Timestamp: {report.timestamp}",
        f"Model: {report.model_used}",
        f"Test Suite: {report.test_suite_name} v{report.test_suite_version}",
        "",
        "-" * 40,
        "CLASSIFICATION METRICS",
        "-" * 40,
        f"Total Test Cases: {report.classification_metrics.total_cases}",
        f"Overall Accuracy: {report.classification_metrics.overall_accuracy:.1%}",
        f"  - Severity Accuracy: {report.classification_metrics.severity_accuracy:.1%}",
        f"  - Stage Accuracy: {report.classification_metrics.stage_accuracy:.1%}",
        f"  - Complexity Accuracy: {report.classification_metrics.complexity_accuracy:.1%}",
        "",
        "Accuracy by Stage:",
    ]

    for stage, acc in sorted(report.classification_metrics.accuracy_by_stage.items()):
        lines.append(f"  - {stage}: {acc:.1%}")

    lines.extend(
        [
            "",
            "-" * 40,
            "SUGGESTION QUALITY METRICS",
            "-" * 40,
            f"Average Root Cause Score: {report.suggestion_metrics.avg_root_cause_score:.2f}",
            f"Average Fix Quality Score: {report.suggestion_metrics.avg_fix_quality_score:.2f}",
            f"Average Overall Score: {report.suggestion_metrics.avg_overall_score:.2f}",
            "",
            "Quality Distribution:",
            f"  - High Quality (≥0.8): {report.suggestion_metrics.high_quality_count}",
            f"  - Medium Quality (0.5-0.8): {report.suggestion_metrics.medium_quality_count}",
            f"  - Low Quality (<0.5): {report.suggestion_metrics.low_quality_count}",
            "",
            "-" * 40,
            "PERFORMANCE METRICS",
            "-" * 40,
            f"Average Response Time: {report.performance_metrics.avg_response_time_ms:.0f}ms",
            f"Min Response Time: {report.performance_metrics.min_response_time_ms:.0f}ms",
            f"Max Response Time: {report.performance_metrics.max_response_time_ms:.0f}ms",
            f"P95 Response Time: {report.performance_metrics.p95_response_time_ms:.0f}ms",
        ]
    )

    # Add confusion matrices
    classification_results = [r.classification for r in report.results]

    for dim in ["severity", "stage", "complexity"]:
        matrix = generate_confusion_matrix(classification_results, dim)
        lines.append(format_confusion_matrix(matrix, f"Confusion Matrix: {dim.upper()}"))

    # Add failure analysis
    if report.failed_cases:
        lines.extend(
            [
                "",
                "-" * 40,
                "FAILED CLASSIFICATIONS",
                "-" * 40,
            ]
        )
        for case_id in report.failed_cases[:10]:  # Show first 10
            result = next((r for r in report.results if r.test_case_id == case_id), None)
            if result:
                lines.append(f"  - {case_id}:")
                lines.append(
                    f"    Expected: {result.classification.expected_stage}/{result.classification.expected_severity}/{result.classification.expected_complexity}"
                )
                lines.append(
                    f"    Got: {result.classification.predicted_stage}/{result.classification.predicted_severity}/{result.classification.predicted_complexity}"
                )

    lines.append("")
    lines.append("=" * 80)

    return "\n".join(lines)


# ============================================================================
# CLI Entry Point
# ============================================================================


async def main(test_suite_path: str | None = None) -> None:
    """Run evaluation on a test suite.

    Args:
        test_suite_path: Optional path to test suite JSON file.
                         Defaults to evaluation/test_cases/test_suite.json.
    """
    # Load test suite
    suite_path = Path(test_suite_path) if test_suite_path else TEST_CASES_DIR / "test_suite.json"

    if not suite_path.exists():
        print(f"Test suite not found: {suite_path}")
        print("Run generator.py first to create test cases.")
        return

    print(f"Loading test suite from: {suite_path}")
    with open(suite_path) as f:
        suite = TestSuite.model_validate_json(f.read())

    # Run evaluation
    runner = EvaluationRunner()
    report = await runner.run_evaluation(suite)

    # Save report
    report_path = runner.save_report(report)
    print(f"\nSaved report to: {report_path}")

    # Print formatted report
    print(format_report(report))


if __name__ == "__main__":
    import sys

    test_suite_arg = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main(test_suite_arg))
