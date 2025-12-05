"""Tests for the evaluation framework."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from evaluation.generator import GeneratedTestCase, validate_xml
from evaluation.judge import JudgeEvaluation, SuggestionJudge
from evaluation.metrics import (
    calculate_classification_metrics,
    calculate_performance_metrics,
    calculate_suggestion_metrics,
    format_confusion_matrix,
    generate_confusion_matrix,
    identify_failures,
)
from evaluation.models import (
    COMPLEXITY_HEURISTICS,
    SEVERITY_RULES,
    STAGE_INDICATORS,
    ClassificationMetrics,
    ClassificationResult,
    ExpectedClassification,
    ExpectedFix,
    PerformanceMetrics,
    SuggestionMetrics,
    SuggestionResult,
    TestCase,
    TestCaseResult,
    TestSuite,
)
from evaluation.patterns import ERROR_PATTERNS

# ============================================================================
# Test Evaluation Models
# ============================================================================


class TestExpectedClassification:
    """Tests for ExpectedClassification model."""

    def test_valid_classification(self) -> None:
        """Test valid expected classification."""
        classification = ExpectedClassification(
            severity="blocking",
            stage="iec_compilation",
            complexity="trivial",
        )
        assert classification.severity == "blocking"
        assert classification.stage == "iec_compilation"
        assert classification.complexity == "trivial"

    def test_invalid_severity(self) -> None:
        """Test that invalid severity raises ValidationError."""
        with pytest.raises(ValidationError):
            ExpectedClassification(
                severity="critical",
                stage="iec_compilation",
                complexity="trivial",
            )


class TestExpectedFix:
    """Tests for ExpectedFix model."""

    def test_with_location(self) -> None:
        """Test fix with location specified."""
        fix = ExpectedFix(
            root_cause="Variable is constant",
            fix_description="Remove constant attribute",
            fix_location="line 30",
        )
        assert fix.fix_location == "line 30"

    def test_without_location(self) -> None:
        """Test fix without location (optional)."""
        fix = ExpectedFix(
            root_cause="Variable is constant",
            fix_description="Remove constant attribute",
        )
        assert fix.fix_location is None


class TestTestCase:
    """Tests for TestCase model."""

    def test_complete_test_case(self) -> None:
        """Test complete test case with all fields."""
        test_case = TestCase(
            id="test_001",
            name="constant_assignment",
            description="Test constant assignment error",
            error_log="Error: constant assignment",
            source_xml="<project>...</project>",
            expected_classification=ExpectedClassification(
                severity="blocking",
                stage="iec_compilation",
                complexity="trivial",
            ),
            expected_fix=ExpectedFix(
                root_cause="Variable is constant",
                fix_description="Remove constant attribute",
            ),
            error_category="constant_assignment",
            base_pattern="Assignment to CONSTANT",
        )
        assert test_case.id == "test_001"
        assert test_case.source_xml is not None

    def test_test_case_without_xml(self) -> None:
        """Test that source_xml is optional."""
        test_case = TestCase(
            id="test_002",
            name="undeclared_variable",
            description="Test undeclared variable",
            error_log="Error: undeclared",
            expected_classification=ExpectedClassification(
                severity="blocking",
                stage="iec_compilation",
                complexity="trivial",
            ),
            expected_fix=ExpectedFix(
                root_cause="Variable not declared",
                fix_description="Add variable declaration",
            ),
            error_category="undeclared_variable",
            base_pattern="Variable not declared",
        )
        assert test_case.source_xml is None


class TestTestSuite:
    """Tests for TestSuite model."""

    def test_test_suite(self) -> None:
        """Test test suite creation."""
        suite = TestSuite(
            name="Test Suite",
            description="A test suite",
            test_cases=[],
            version="1.0.0",
        )
        assert suite.name == "Test Suite"
        assert len(suite.test_cases) == 0


class TestClassificationResult:
    """Tests for ClassificationResult model."""

    def test_all_correct(self) -> None:
        """Test result where all predictions are correct."""
        result = ClassificationResult(
            test_case_id="test_001",
            predicted_severity="blocking",
            predicted_stage="iec_compilation",
            predicted_complexity="trivial",
            expected_severity="blocking",
            expected_stage="iec_compilation",
            expected_complexity="trivial",
            severity_correct=True,
            stage_correct=True,
            complexity_correct=True,
            all_correct=True,
        )
        assert result.all_correct

    def test_partial_correct(self) -> None:
        """Test result where some predictions are incorrect."""
        result = ClassificationResult(
            test_case_id="test_002",
            predicted_severity="blocking",
            predicted_stage="code_generation",  # Wrong
            predicted_complexity="trivial",
            expected_severity="blocking",
            expected_stage="iec_compilation",
            expected_complexity="trivial",
            severity_correct=True,
            stage_correct=False,
            complexity_correct=True,
            all_correct=False,
        )
        assert not result.all_correct
        assert result.severity_correct
        assert not result.stage_correct


class TestSuggestionResult:
    """Tests for SuggestionResult model."""

    def test_high_quality_suggestion(self) -> None:
        """Test high quality suggestion result."""
        result = SuggestionResult(
            test_case_id="test_001",
            predicted_root_cause="Variable is constant",
            predicted_fix_description="Remove constant attribute",
            confidence=0.95,
            expected_root_cause="Variable declared as constant",
            expected_fix_description="Remove constant modifier",
            root_cause_score=0.9,
            fix_quality_score=0.95,
            overall_score=0.92,
            judge_reasoning="Good analysis",
        )
        assert result.overall_score >= 0.8

    def test_score_bounds(self) -> None:
        """Test that scores must be between 0 and 1."""
        with pytest.raises(ValidationError):
            SuggestionResult(
                test_case_id="test_001",
                predicted_root_cause="test",
                predicted_fix_description="test",
                confidence=0.5,
                expected_root_cause="test",
                expected_fix_description="test",
                root_cause_score=1.5,  # Invalid
                fix_quality_score=0.5,
                overall_score=0.5,
                judge_reasoning="test",
            )


class TestHeuristicMappings:
    """Tests for heuristic mappings in models."""

    def test_complexity_heuristics_coverage(self) -> None:
        """Test that complexity heuristics cover common cases."""
        assert "constant_assignment" in COMPLEXITY_HEURISTICS
        assert "undeclared_variable" in COMPLEXITY_HEURISTICS
        assert "datetime_format" in COMPLEXITY_HEURISTICS
        assert COMPLEXITY_HEURISTICS["constant_assignment"] == "trivial"

    def test_severity_rules_coverage(self) -> None:
        """Test that severity rules cover common patterns."""
        assert "error:" in SEVERITY_RULES
        assert "Error:" in SEVERITY_RULES
        assert "Warning:" in SEVERITY_RULES
        assert SEVERITY_RULES["error:"] == "blocking"

    def test_stage_indicators_coverage(self) -> None:
        """Test that stage indicators cover all stages."""
        stages = set(STAGE_INDICATORS.values())
        assert "xml_validation" in stages
        assert "code_generation" in stages
        assert "iec_compilation" in stages
        assert "c_compilation" in stages


# ============================================================================
# Test Metrics Calculations
# ============================================================================


class TestCalculateClassificationMetrics:
    """Tests for classification metrics calculation."""

    def test_empty_results(self) -> None:
        """Test metrics with no results."""
        metrics = calculate_classification_metrics([])
        assert metrics.total_cases == 0
        assert metrics.overall_accuracy == 0.0

    def test_all_correct(self) -> None:
        """Test metrics when all predictions are correct."""
        results = [
            ClassificationResult(
                test_case_id=f"test_{i}",
                predicted_severity="blocking",
                predicted_stage="iec_compilation",
                predicted_complexity="trivial",
                expected_severity="blocking",
                expected_stage="iec_compilation",
                expected_complexity="trivial",
                severity_correct=True,
                stage_correct=True,
                complexity_correct=True,
                all_correct=True,
            )
            for i in range(5)
        ]
        metrics = calculate_classification_metrics(results)
        assert metrics.total_cases == 5
        assert metrics.severity_accuracy == 1.0
        assert metrics.stage_accuracy == 1.0
        assert metrics.complexity_accuracy == 1.0
        assert metrics.overall_accuracy == 1.0

    def test_partial_accuracy(self) -> None:
        """Test metrics with partial accuracy."""
        results = [
            ClassificationResult(
                test_case_id="test_1",
                predicted_severity="blocking",
                predicted_stage="iec_compilation",
                predicted_complexity="trivial",
                expected_severity="blocking",
                expected_stage="iec_compilation",
                expected_complexity="trivial",
                severity_correct=True,
                stage_correct=True,
                complexity_correct=True,
                all_correct=True,
            ),
            ClassificationResult(
                test_case_id="test_2",
                predicted_severity="warning",  # Wrong
                predicted_stage="iec_compilation",
                predicted_complexity="trivial",
                expected_severity="blocking",
                expected_stage="iec_compilation",
                expected_complexity="trivial",
                severity_correct=False,
                stage_correct=True,
                complexity_correct=True,
                all_correct=False,
            ),
        ]
        metrics = calculate_classification_metrics(results)
        assert metrics.total_cases == 2
        assert metrics.severity_accuracy == 0.5
        assert metrics.stage_accuracy == 1.0
        assert metrics.overall_accuracy == 0.5

    def test_accuracy_by_stage(self) -> None:
        """Test accuracy breakdown by stage."""
        results = [
            ClassificationResult(
                test_case_id="test_1",
                predicted_severity="blocking",
                predicted_stage="iec_compilation",
                predicted_complexity="trivial",
                expected_severity="blocking",
                expected_stage="iec_compilation",
                expected_complexity="trivial",
                severity_correct=True,
                stage_correct=True,
                complexity_correct=True,
                all_correct=True,
            ),
            ClassificationResult(
                test_case_id="test_2",
                predicted_severity="blocking",
                predicted_stage="code_generation",
                predicted_complexity="moderate",
                expected_severity="blocking",
                expected_stage="code_generation",
                expected_complexity="moderate",
                severity_correct=True,
                stage_correct=True,
                complexity_correct=True,
                all_correct=True,
            ),
        ]
        metrics = calculate_classification_metrics(results)
        assert "iec_compilation" in metrics.accuracy_by_stage
        assert "code_generation" in metrics.accuracy_by_stage
        assert metrics.accuracy_by_stage["iec_compilation"] == 1.0


class TestCalculateSuggestionMetrics:
    """Tests for suggestion metrics calculation."""

    def test_empty_results(self) -> None:
        """Test metrics with no results."""
        metrics = calculate_suggestion_metrics([])
        assert metrics.total_cases == 0
        assert metrics.avg_overall_score == 0.0

    def test_quality_distribution(self) -> None:
        """Test quality tier distribution."""
        results = [
            SuggestionResult(
                test_case_id="test_1",
                predicted_root_cause="test",
                predicted_fix_description="test",
                confidence=0.9,
                expected_root_cause="test",
                expected_fix_description="test",
                root_cause_score=0.9,
                fix_quality_score=0.9,
                overall_score=0.9,  # High quality
                judge_reasoning="test",
            ),
            SuggestionResult(
                test_case_id="test_2",
                predicted_root_cause="test",
                predicted_fix_description="test",
                confidence=0.7,
                expected_root_cause="test",
                expected_fix_description="test",
                root_cause_score=0.6,
                fix_quality_score=0.7,
                overall_score=0.65,  # Medium quality
                judge_reasoning="test",
            ),
            SuggestionResult(
                test_case_id="test_3",
                predicted_root_cause="test",
                predicted_fix_description="test",
                confidence=0.3,
                expected_root_cause="test",
                expected_fix_description="test",
                root_cause_score=0.3,
                fix_quality_score=0.4,
                overall_score=0.35,  # Low quality
                judge_reasoning="test",
            ),
        ]
        metrics = calculate_suggestion_metrics(results)
        assert metrics.high_quality_count == 1
        assert metrics.medium_quality_count == 1
        assert metrics.low_quality_count == 1


class TestCalculatePerformanceMetrics:
    """Tests for performance metrics calculation."""

    def test_empty_results(self) -> None:
        """Test metrics with no results."""
        metrics = calculate_performance_metrics([])
        assert metrics.total_cases == 0
        assert metrics.avg_response_time_ms == 0.0

    def test_timing_metrics(self) -> None:
        """Test timing metrics calculation."""
        # Create mock test case results with varying response times
        results = []
        for i, time_ms in enumerate([100, 200, 300, 400, 500]):
            results.append(
                TestCaseResult(
                    test_case_id=f"test_{i}",
                    test_case_name=f"test_{i}",
                    classification=ClassificationResult(
                        test_case_id=f"test_{i}",
                        predicted_severity="blocking",
                        predicted_stage="iec_compilation",
                        predicted_complexity="trivial",
                        expected_severity="blocking",
                        expected_stage="iec_compilation",
                        expected_complexity="trivial",
                        severity_correct=True,
                        stage_correct=True,
                        complexity_correct=True,
                        all_correct=True,
                    ),
                    suggestion=SuggestionResult(
                        test_case_id=f"test_{i}",
                        predicted_root_cause="test",
                        predicted_fix_description="test",
                        confidence=0.9,
                        expected_root_cause="test",
                        expected_fix_description="test",
                        root_cause_score=0.9,
                        fix_quality_score=0.9,
                        overall_score=0.9,
                        judge_reasoning="test",
                    ),
                    response_time_ms=float(time_ms),
                )
            )

        metrics = calculate_performance_metrics(results)
        assert metrics.total_cases == 5
        assert metrics.avg_response_time_ms == 300.0
        assert metrics.min_response_time_ms == 100.0
        assert metrics.max_response_time_ms == 500.0


class TestIdentifyFailures:
    """Tests for failure identification."""

    def test_identify_failures(self) -> None:
        """Test identification of failed cases."""
        results = [
            TestCaseResult(
                test_case_id="test_pass",
                test_case_name="test_pass",
                classification=ClassificationResult(
                    test_case_id="test_pass",
                    predicted_severity="blocking",
                    predicted_stage="iec_compilation",
                    predicted_complexity="trivial",
                    expected_severity="blocking",
                    expected_stage="iec_compilation",
                    expected_complexity="trivial",
                    severity_correct=True,
                    stage_correct=True,
                    complexity_correct=True,
                    all_correct=True,
                ),
                suggestion=SuggestionResult(
                    test_case_id="test_pass",
                    predicted_root_cause="test",
                    predicted_fix_description="test",
                    confidence=0.9,
                    expected_root_cause="test",
                    expected_fix_description="test",
                    root_cause_score=0.9,
                    fix_quality_score=0.9,
                    overall_score=0.9,
                    judge_reasoning="test",
                ),
                response_time_ms=100.0,
            ),
            TestCaseResult(
                test_case_id="test_fail_class",
                test_case_name="test_fail_class",
                classification=ClassificationResult(
                    test_case_id="test_fail_class",
                    predicted_severity="warning",
                    predicted_stage="iec_compilation",
                    predicted_complexity="trivial",
                    expected_severity="blocking",
                    expected_stage="iec_compilation",
                    expected_complexity="trivial",
                    severity_correct=False,
                    stage_correct=True,
                    complexity_correct=True,
                    all_correct=False,
                ),
                suggestion=SuggestionResult(
                    test_case_id="test_fail_class",
                    predicted_root_cause="test",
                    predicted_fix_description="test",
                    confidence=0.9,
                    expected_root_cause="test",
                    expected_fix_description="test",
                    root_cause_score=0.9,
                    fix_quality_score=0.9,
                    overall_score=0.9,
                    judge_reasoning="test",
                ),
                response_time_ms=100.0,
            ),
            TestCaseResult(
                test_case_id="test_low_quality",
                test_case_name="test_low_quality",
                classification=ClassificationResult(
                    test_case_id="test_low_quality",
                    predicted_severity="blocking",
                    predicted_stage="iec_compilation",
                    predicted_complexity="trivial",
                    expected_severity="blocking",
                    expected_stage="iec_compilation",
                    expected_complexity="trivial",
                    severity_correct=True,
                    stage_correct=True,
                    complexity_correct=True,
                    all_correct=True,
                ),
                suggestion=SuggestionResult(
                    test_case_id="test_low_quality",
                    predicted_root_cause="wrong",
                    predicted_fix_description="wrong",
                    confidence=0.3,
                    expected_root_cause="test",
                    expected_fix_description="test",
                    root_cause_score=0.2,
                    fix_quality_score=0.3,
                    overall_score=0.25,  # Low quality
                    judge_reasoning="Poor analysis",
                ),
                response_time_ms=100.0,
            ),
        ]

        failed_class, low_quality = identify_failures(results)
        assert "test_fail_class" in failed_class
        assert "test_pass" not in failed_class
        assert "test_low_quality" in low_quality
        assert "test_pass" not in low_quality


class TestConfusionMatrix:
    """Tests for confusion matrix generation."""

    def test_generate_confusion_matrix(self) -> None:
        """Test confusion matrix generation."""
        results = [
            ClassificationResult(
                test_case_id="test_1",
                predicted_severity="blocking",
                predicted_stage="iec_compilation",
                predicted_complexity="trivial",
                expected_severity="blocking",
                expected_stage="iec_compilation",
                expected_complexity="trivial",
                severity_correct=True,
                stage_correct=True,
                complexity_correct=True,
                all_correct=True,
            ),
            ClassificationResult(
                test_case_id="test_2",
                predicted_severity="warning",
                predicted_stage="iec_compilation",
                predicted_complexity="trivial",
                expected_severity="blocking",
                expected_stage="iec_compilation",
                expected_complexity="trivial",
                severity_correct=False,
                stage_correct=True,
                complexity_correct=True,
                all_correct=False,
            ),
        ]

        matrix = generate_confusion_matrix(results, "severity")
        assert matrix["blocking"]["blocking"] == 1
        assert matrix["blocking"]["warning"] == 1

    def test_format_confusion_matrix(self) -> None:
        """Test confusion matrix formatting."""
        matrix = {
            "blocking": {"blocking": 5, "warning": 2},
            "warning": {"blocking": 1, "warning": 3},
        }
        formatted = format_confusion_matrix(matrix, "Severity")
        assert "Severity" in formatted
        assert "blocking" in formatted


# ============================================================================
# Test Generator
# ============================================================================


class TestErrorPatterns:
    """Tests for error pattern definitions."""

    def test_error_patterns_valid(self) -> None:
        """Test that all error patterns are valid."""
        assert len(ERROR_PATTERNS) > 0
        for pattern in ERROR_PATTERNS:
            assert pattern.id
            assert pattern.name
            assert pattern.stage in [
                "xml_validation",
                "code_generation",
                "iec_compilation",
                "c_compilation",
            ]
            assert pattern.severity in ["blocking", "warning", "info"]
            assert pattern.complexity in ["trivial", "moderate", "complex"]

    def test_error_patterns_cover_all_stages(self) -> None:
        """Test that patterns cover all build stages."""
        stages = {p.stage for p in ERROR_PATTERNS}
        assert "xml_validation" in stages
        assert "code_generation" in stages
        assert "iec_compilation" in stages
        assert "c_compilation" in stages


class TestValidateXml:
    """Tests for XML validation function."""

    def test_valid_xml(self) -> None:
        """Test validation of valid XML."""
        is_valid, error = validate_xml("<root><child>text</child></root>")
        assert is_valid
        assert error is None

    def test_invalid_xml(self) -> None:
        """Test validation of invalid XML."""
        is_valid, error = validate_xml("<root><child>text</root>")
        assert not is_valid
        assert error is not None

    def test_empty_xml(self) -> None:
        """Test validation of empty XML (allowed)."""
        is_valid, error = validate_xml("")
        assert is_valid
        assert error is None


class TestGeneratedTestCase:
    """Tests for GeneratedTestCase schema."""

    def test_valid_generated_test_case(self) -> None:
        """Test valid generated test case."""
        test_case = GeneratedTestCase(
            error_log="Error: test",
            root_cause="Test cause",
            fix_description="Test fix",
            fix_location="line 10",
            source_xml="<root/>",
        )
        assert test_case.error_log == "Error: test"
        assert test_case.source_xml == "<root/>"

    def test_optional_fields(self) -> None:
        """Test generated test case with optional fields."""
        test_case = GeneratedTestCase(
            error_log="Error: test",
            root_cause="Test cause",
            fix_description="Test fix",
        )
        assert test_case.fix_location is None
        assert test_case.source_xml is None


# ============================================================================
# Test Judge
# ============================================================================


class TestJudgeEvaluation:
    """Tests for JudgeEvaluation schema."""

    def test_valid_evaluation(self) -> None:
        """Test valid judge evaluation."""
        evaluation = JudgeEvaluation(
            root_cause_score=0.9,
            fix_quality_score=0.85,
            overall_score=0.87,
            reasoning="Good analysis with accurate root cause",
        )
        assert evaluation.root_cause_score == 0.9
        assert evaluation.overall_score == 0.87

    def test_score_bounds(self) -> None:
        """Test that scores must be between 0 and 1."""
        with pytest.raises(ValidationError):
            JudgeEvaluation(
                root_cause_score=1.5,  # Invalid
                fix_quality_score=0.5,
                overall_score=0.5,
                reasoning="test",
            )


class TestSuggestionJudgeWithMock:
    """Tests for SuggestionJudge with mocked LLM."""

    @pytest.fixture
    def mock_judge_response_json(self) -> str:
        """Sample judge response JSON."""
        return """
        {
            "root_cause_score": 0.9,
            "fix_quality_score": 0.85,
            "overall_score": 0.87,
            "reasoning": "Good analysis with accurate root cause identification"
        }
        """

    @pytest.mark.asyncio
    async def test_evaluate_suggestion(self, mock_judge_response_json: str) -> None:
        """Test suggestion evaluation with mocked LLM."""
        mock_response = MagicMock()
        mock_response.text = mock_judge_response_json

        mock_aclient = AsyncMock()
        mock_aclient.models.generate_content = AsyncMock(return_value=mock_response)

        with patch("evaluation.judge.genai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            judge = SuggestionJudge(api_key="test-key")

            result = await judge.evaluate_suggestion(
                aclient=mock_aclient,
                test_case_id="test_001",
                error_log="Error: constant assignment",
                expected_fix=ExpectedFix(
                    root_cause="Variable is constant",
                    fix_description="Remove constant attribute",
                ),
                predicted_root_cause="Variable declared as constant",
                predicted_fix_description="Remove the constant modifier",
                confidence=0.95,
            )

        assert result.test_case_id == "test_001"
        assert result.root_cause_score == 0.9
        assert result.fix_quality_score == 0.85
        assert result.overall_score == 0.87

    def test_judge_init_requires_api_key(self) -> None:
        """Test that judge initialization requires API key."""
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("evaluation.judge.load_dotenv"),
            pytest.raises(ValueError, match="GEMINI_API_KEY"),
        ):
            SuggestionJudge(api_key=None)


# ============================================================================
# Test Bootstrap Statistical Functions
# ============================================================================


class TestBootstrapFunctions:
    """Tests for bootstrap statistical functions."""

    def test_bootstrap_proportion_basic(self) -> None:
        """Test bootstrap CI for a proportion."""
        from evaluation.metrics import bootstrap_proportion

        # 80% accuracy: 80 successes out of 100
        ci = bootstrap_proportion(successes=80, total=100, n_bootstrap=500)

        assert ci.point_estimate == 0.8
        assert ci.ci_lower <= 0.8 <= ci.ci_upper
        assert ci.ci_lower >= 0.0
        assert ci.ci_upper <= 1.0
        assert ci.confidence_level == 0.95
        assert ci.std_error > 0

    def test_bootstrap_proportion_empty(self) -> None:
        """Test bootstrap with zero total."""
        from evaluation.metrics import bootstrap_proportion

        ci = bootstrap_proportion(successes=0, total=0)

        assert ci.point_estimate == 0.0
        assert ci.ci_lower == 0.0
        assert ci.ci_upper == 0.0

    def test_bootstrap_proportion_perfect(self) -> None:
        """Test bootstrap with perfect accuracy."""
        from evaluation.metrics import bootstrap_proportion

        ci = bootstrap_proportion(successes=100, total=100, n_bootstrap=500)

        assert ci.point_estimate == 1.0
        assert ci.ci_lower >= 0.95  # Should be close to 1.0
        assert ci.ci_upper == 1.0

    def test_bootstrap_mean_basic(self) -> None:
        """Test bootstrap CI for a mean."""
        from evaluation.metrics import bootstrap_mean

        values = [0.7, 0.8, 0.9, 0.85, 0.75, 0.82, 0.88, 0.79]
        ci = bootstrap_mean(values, n_bootstrap=500)

        expected_mean = sum(values) / len(values)
        assert abs(ci.point_estimate - expected_mean) < 0.001
        assert ci.ci_lower <= expected_mean <= ci.ci_upper
        assert ci.std_error > 0

    def test_bootstrap_mean_empty(self) -> None:
        """Test bootstrap mean with empty data."""
        from evaluation.metrics import bootstrap_mean

        ci = bootstrap_mean([])

        assert ci.point_estimate == 0.0
        assert ci.ci_lower == 0.0
        assert ci.ci_upper == 0.0

    def test_bootstrap_percentile_basic(self) -> None:
        """Test bootstrap CI for a percentile."""
        from evaluation.metrics import bootstrap_percentile

        values = list(range(100, 600, 10))  # 100, 110, ..., 590
        ci = bootstrap_percentile(values, percentile=95.0, n_bootstrap=500)

        assert ci.point_estimate > 500  # p95 should be near the high end
        assert ci.ci_lower <= ci.point_estimate <= ci.ci_upper

    def test_bootstrap_reproducibility(self) -> None:
        """Test that bootstrap results are reproducible with same seed."""
        from evaluation.metrics import bootstrap_proportion

        ci1 = bootstrap_proportion(80, 100, random_seed=42)
        ci2 = bootstrap_proportion(80, 100, random_seed=42)

        assert ci1.ci_lower == ci2.ci_lower
        assert ci1.ci_upper == ci2.ci_upper

    def test_confidence_interval_margin_of_error(self) -> None:
        """Test ConfidenceInterval margin_of_error property."""
        from evaluation.models import ConfidenceInterval

        ci = ConfidenceInterval(
            point_estimate=0.8,
            ci_lower=0.75,
            ci_upper=0.85,
        )

        assert ci.margin_of_error == pytest.approx(0.05)


class TestMetricsWithConfidenceIntervals:
    """Tests for metrics calculation with CI enabled."""

    def test_classification_metrics_with_ci(self) -> None:
        """Test classification metrics with CI calculation."""
        results = [
            ClassificationResult(
                test_case_id=f"test_{i}",
                predicted_severity="blocking",
                predicted_stage="iec_compilation",
                predicted_complexity="trivial",
                expected_severity="blocking",
                expected_stage="iec_compilation",
                expected_complexity="trivial",
                severity_correct=True,
                stage_correct=True,
                complexity_correct=True,
                all_correct=True,
            )
            for i in range(80)
        ] + [
            ClassificationResult(
                test_case_id=f"test_fail_{i}",
                predicted_severity="warning",
                predicted_stage="code_generation",
                predicted_complexity="moderate",
                expected_severity="blocking",
                expected_stage="iec_compilation",
                expected_complexity="trivial",
                severity_correct=False,
                stage_correct=False,
                complexity_correct=False,
                all_correct=False,
            )
            for i in range(20)
        ]

        metrics = calculate_classification_metrics(results, compute_ci=True, n_bootstrap=500)

        # Check point estimates
        assert metrics.overall_accuracy == 0.8
        assert metrics.severity_accuracy == 0.8

        # Check CIs are populated
        assert metrics.overall_accuracy_ci is not None
        assert metrics.severity_accuracy_ci is not None
        assert metrics.stage_accuracy_ci is not None
        assert metrics.complexity_accuracy_ci is not None

        # Check CI bounds make sense
        assert metrics.overall_accuracy_ci.ci_lower <= 0.8
        assert metrics.overall_accuracy_ci.ci_upper >= 0.8
        assert metrics.overall_accuracy_ci.std_error > 0

    def test_suggestion_metrics_with_ci(self) -> None:
        """Test suggestion metrics with CI calculation."""
        results = [
            SuggestionResult(
                test_case_id=f"test_{i}",
                predicted_root_cause="cause",
                predicted_fix_description="fix",
                confidence=0.9,
                expected_root_cause="cause",
                expected_fix_description="fix",
                root_cause_score=0.7 + (i % 3) * 0.1,
                fix_quality_score=0.8,
                overall_score=0.75 + (i % 3) * 0.05,
                judge_reasoning="test",
            )
            for i in range(50)
        ]

        metrics = calculate_suggestion_metrics(results, compute_ci=True, n_bootstrap=500)

        # Check CIs are populated
        assert metrics.root_cause_score_ci is not None
        assert metrics.fix_quality_score_ci is not None
        assert metrics.overall_score_ci is not None

        # Check point estimates match averages
        expected_avg = metrics.avg_overall_score
        assert abs(metrics.overall_score_ci.point_estimate - expected_avg) < 0.001

    def test_performance_metrics_with_ci(self) -> None:
        """Test performance metrics with CI calculation."""
        results = [
            TestCaseResult(
                test_case_id=f"test_{i}",
                test_case_name=f"test_{i}",
                classification=ClassificationResult(
                    test_case_id=f"test_{i}",
                    predicted_severity="blocking",
                    predicted_stage="iec_compilation",
                    predicted_complexity="trivial",
                    expected_severity="blocking",
                    expected_stage="iec_compilation",
                    expected_complexity="trivial",
                    severity_correct=True,
                    stage_correct=True,
                    complexity_correct=True,
                    all_correct=True,
                ),
                suggestion=SuggestionResult(
                    test_case_id=f"test_{i}",
                    predicted_root_cause="test",
                    predicted_fix_description="test",
                    confidence=0.9,
                    expected_root_cause="test",
                    expected_fix_description="test",
                    root_cause_score=0.9,
                    fix_quality_score=0.9,
                    overall_score=0.9,
                    judge_reasoning="test",
                ),
                response_time_ms=100.0 + i * 10,  # 100, 110, ..., 590
            )
            for i in range(50)
        ]

        metrics = calculate_performance_metrics(results, compute_ci=True, n_bootstrap=500)

        # Check CIs are populated
        assert metrics.avg_response_time_ci is not None
        assert metrics.p95_response_time_ci is not None

        # Check point estimates match
        expected_avg = sum(100 + i * 10 for i in range(50)) / 50
        assert abs(metrics.avg_response_time_ci.point_estimate - expected_avg) < 1


class TestFormatFunctions:
    """Tests for formatting functions."""

    def test_format_ci_as_percent(self) -> None:
        """Test CI formatting as percentage."""
        from evaluation.metrics import format_ci
        from evaluation.models import ConfidenceInterval

        ci = ConfidenceInterval(
            point_estimate=0.85,
            ci_lower=0.80,
            ci_upper=0.90,
        )

        formatted = format_ci(ci, as_percent=True)
        assert "85.0%" in formatted
        assert "80.0%" in formatted
        assert "90.0%" in formatted

    def test_format_ci_as_decimal(self) -> None:
        """Test CI formatting as decimal."""
        from evaluation.metrics import format_ci
        from evaluation.models import ConfidenceInterval

        ci = ConfidenceInterval(
            point_estimate=0.85,
            ci_lower=0.80,
            ci_upper=0.90,
        )

        formatted = format_ci(ci, as_percent=False)
        assert "0.850" in formatted
        assert "0.800" in formatted
        assert "0.900" in formatted

    def test_format_ci_none(self) -> None:
        """Test formatting None CI."""
        from evaluation.metrics import format_ci

        assert format_ci(None) == "N/A"

    def test_format_statistical_summary(self) -> None:
        """Test statistical summary formatting."""
        from evaluation.metrics import format_statistical_summary

        classification_metrics = ClassificationMetrics(
            total_cases=100,
            severity_accuracy=0.9,
            stage_accuracy=0.85,
            complexity_accuracy=0.8,
            overall_accuracy=0.75,
        )
        suggestion_metrics = SuggestionMetrics(
            total_cases=100,
            avg_root_cause_score=0.8,
            avg_fix_quality_score=0.85,
            avg_overall_score=0.82,
        )
        performance_metrics = PerformanceMetrics(
            total_cases=100,
            avg_response_time_ms=250.0,
            min_response_time_ms=100.0,
            max_response_time_ms=500.0,
            p95_response_time_ms=450.0,
        )

        summary = format_statistical_summary(
            classification_metrics, suggestion_metrics, performance_metrics
        )

        assert "STATISTICAL SUMMARY" in summary
        assert "CLASSIFICATION ACCURACY" in summary
        assert "SUGGESTION QUALITY" in summary
        assert "PERFORMANCE" in summary
        assert "100 test cases" in summary
