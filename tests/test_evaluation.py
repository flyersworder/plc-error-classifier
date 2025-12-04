"""Tests for the evaluation framework."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from evaluation.generator import (
    ERROR_PATTERNS,
    GeneratedTestCase,
    validate_xml,
)
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
    ClassificationResult,
    ExpectedClassification,
    ExpectedFix,
    SuggestionResult,
    TestCase,
    TestCaseResult,
    TestSuite,
)

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
