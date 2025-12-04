"""Main evaluation runner for PLC error classifier."""

import asyncio
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

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
    ExpectedClassification,
    TestCase,
    TestCaseResult,
    TestSuite,
)

# Load environment variables
load_dotenv()

# Rate limiting: max concurrent API requests
MAX_CONCURRENT_REQUESTS = 5

# ============================================================================
# Classifier Output Schema
# ============================================================================


class SuggestionOutput(BaseModel):
    """Suggestion portion of the classifier output."""

    root_cause: str = Field(description="What's actually wrong")
    fix_description: str = Field(description="How to fix it")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0.0-1.0")


class ClassifierOutput(BaseModel):
    """Full classifier output schema.

    Reuses ExpectedClassification for consistency with ground truth format.
    """

    classification: ExpectedClassification
    suggestion: SuggestionOutput


# ============================================================================
# Configuration
# ============================================================================

# Model to evaluate
CLASSIFIER_MODEL = "gemini-2.5-flash"

# Paths
TEST_CASES_DIR = Path(__file__).parent / "test_cases"
REPORTS_DIR = Path(__file__).parent / "reports"


# ============================================================================
# Classifier Interface
# ============================================================================

# TODO: Replace this placeholder with the actual classifier once implemented
#
# The actual classifier should be imported from:
#   from plc_error_classifier.classifier import classify
#
# This placeholder exists so the evaluation framework can be tested independently.
# It uses a simplified prompt and doesn't include:
#   - Lightweight parser integration
#   - Full IEC 61131-3 domain knowledge
#   - Web search for deep_analysis
#
# Once the classifier is built, update this file to:
#   1. Import the real classifier
#   2. Remove this placeholder implementation

CLASSIFIER_SYSTEM_PROMPT = """You are an IEC 61131-3 PLC expert specializing in Beremiz toolchain errors.

Analyze the provided error log and classify it.

## Build Pipeline Stages
1. **xml_validation**: PLCopen XML schema validation (XSD errors)
2. **code_generation**: Beremiz Python code generator errors (Python tracebacks)
3. **iec_compilation**: matiec/iec2c ST to C compiler errors
4. **c_compilation**: gcc C compiler errors

## Classification Criteria

### Severity
- **blocking**: Build cannot complete (errors, tracebacks)
- **warning**: Build may complete but with issues
- **info**: Informational messages only

### Complexity
- **trivial**: Single-line fix, obvious from error message
- **moderate**: Requires understanding context/type system
- **complex**: Multiple related errors or architectural issues

## Output Format
Respond with JSON containing:
```json
{
    "classification": {
        "severity": "blocking|warning|info",
        "stage": "xml_validation|code_generation|iec_compilation|c_compilation",
        "complexity": "trivial|moderate|complex"
    },
    "suggestion": {
        "root_cause": "What's actually wrong",
        "fix_description": "How to fix it",
        "confidence": 0.0-1.0
    }
}
```"""


async def classify_error(
    aclient: genai.Client,
    error_log: str,
    source_xml: str | None = None,
) -> dict:
    """Classify an error using the Gemini model.

    This is a placeholder classifier for evaluation testing.
    The actual classifier will be in src/plc_error_classifier/classifier.py.

    Args:
        aclient: Async Gemini client (from client.aio context manager).
        error_log: The build output/error log to classify.
        source_xml: Optional PLCopen XML source for context.

    Returns:
        Dict with classification and suggestion fields.
    """
    # Build user prompt
    user_content = f"Error Log:\n```\n{error_log}\n```"
    if source_xml:
        user_content += f"\n\nSource XML (for context):\n```xml\n{source_xml[:2000]}\n```"

    # Per GEMINI_PROMPTING.md: temperature=0.0 for classification tasks
    # Use response_json_schema for guaranteed structured output
    config = types.GenerateContentConfig(
        system_instruction=CLASSIFIER_SYSTEM_PROMPT,
        temperature=0.0,  # Deterministic for evaluation
        response_mime_type="application/json",
        response_json_schema=ClassifierOutput.model_json_schema(),
        thinking_config=types.ThinkingConfig(thinking_budget=1024),  # Standard thinking
    )

    # Use async API for scalability
    response = await aclient.models.generate_content(
        model=CLASSIFIER_MODEL,
        contents=user_content,
        config=config,
    )

    # Parse and validate with Pydantic
    result = ClassifierOutput.model_validate_json(response.text)
    return result.model_dump()


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
        classifier_client: genai.Client,
        judge_client: genai.Client,
        test_case: TestCase,
    ) -> TestCaseResult:
        """Evaluate a single test case.

        Args:
            classifier_client: Async Gemini client for classification.
            judge_client: Async Gemini client for judge evaluation.
            test_case: The test case to evaluate.

        Returns:
            TestCaseResult with classification and suggestion evaluation.
        """
        # Rate limiting
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        async with self._semaphore:
            # Time the classification
            start_time = time.time()

            # Classify the error
            result = await classify_error(
                classifier_client,
                test_case.error_log,
                test_case.source_xml,
            )

            elapsed_ms = (time.time() - start_time) * 1000

            # Extract predictions
            classification = result.get("classification", {})
            suggestion = result.get("suggestion", {})

            predicted_severity = classification.get("severity", "unknown")
            predicted_stage = classification.get("stage", "unknown")
            predicted_complexity = classification.get("complexity", "unknown")

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
                predicted_root_cause=suggestion.get("root_cause", ""),
                predicted_fix_description=suggestion.get("fix_description", ""),
                confidence=suggestion.get("confidence", 0.5),
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
        classifier_client: genai.Client,
        judge_client: genai.Client,
        test_case: TestCase,
        index: int,
        total: int,
    ) -> TestCaseResult | None:
        """Evaluate a test case with progress logging."""
        try:
            result = await self.evaluate_test_case(classifier_client, judge_client, test_case)
            status = "✓" if result.classification.all_correct else "✗"
            print(
                f"  [{index}/{total}] {test_case.name}... {status} ({result.response_time_ms:.0f}ms)"
            )
            return result
        except Exception as e:
            print(f"  [{index}/{total}] {test_case.name}... ERROR: {e}")
            return None

    async def run_evaluation(self, suite: TestSuite) -> EvaluationReport:
        """Run evaluation on entire test suite concurrently.

        Args:
            suite: The test suite to evaluate.

        Returns:
            EvaluationReport with all metrics and results.
        """
        print(f"Running evaluation on {len(suite.test_cases)} test cases...")

        # Use separate async contexts for classifier and judge
        async with (
            self.client.aio as classifier_client,
            self.judge.client.aio as judge_client,
        ):
            tasks = [
                self._evaluate_with_logging(
                    classifier_client,
                    judge_client,
                    test_case,
                    i,
                    len(suite.test_cases),
                )
                for i, test_case in enumerate(suite.test_cases, 1)
            ]
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
