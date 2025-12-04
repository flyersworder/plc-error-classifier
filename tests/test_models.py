"""Tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from plc_error_classifier.models import (
    ClassifierOutput,
    ClassifyRequest,
    ClassifyResponse,
    ErrorClassification,
    FixSuggestion,
)


class TestErrorClassification:
    """Tests for ErrorClassification model."""

    def test_valid_classification(self) -> None:
        """Test valid classification values."""
        classification = ErrorClassification(
            severity="blocking",
            stage="iec_compilation",
            complexity="trivial",
        )
        assert classification.severity == "blocking"
        assert classification.stage == "iec_compilation"
        assert classification.complexity == "trivial"

    def test_all_severity_values(self) -> None:
        """Test all valid severity values."""
        for severity in ["blocking", "warning", "info"]:
            classification = ErrorClassification(
                severity=severity,
                stage="iec_compilation",
                complexity="trivial",
            )
            assert classification.severity == severity

    def test_all_stage_values(self) -> None:
        """Test all valid stage values."""
        stages = ["xml_validation", "code_generation", "iec_compilation", "c_compilation"]
        for stage in stages:
            classification = ErrorClassification(
                severity="blocking",
                stage=stage,
                complexity="trivial",
            )
            assert classification.stage == stage

    def test_all_complexity_values(self) -> None:
        """Test all valid complexity values."""
        for complexity in ["trivial", "moderate", "complex"]:
            classification = ErrorClassification(
                severity="blocking",
                stage="iec_compilation",
                complexity=complexity,
            )
            assert classification.complexity == complexity

    def test_invalid_severity(self) -> None:
        """Test that invalid severity raises ValidationError."""
        with pytest.raises(ValidationError):
            ErrorClassification(
                severity="critical",
                stage="iec_compilation",
                complexity="trivial",
            )

    def test_invalid_stage(self) -> None:
        """Test that invalid stage raises ValidationError."""
        with pytest.raises(ValidationError):
            ErrorClassification(
                severity="blocking",
                stage="parsing",
                complexity="trivial",
            )

    def test_invalid_complexity(self) -> None:
        """Test that invalid complexity raises ValidationError."""
        with pytest.raises(ValidationError):
            ErrorClassification(
                severity="blocking",
                stage="iec_compilation",
                complexity="easy",
            )


class TestFixSuggestion:
    """Tests for FixSuggestion model."""

    def test_valid_suggestion_with_code(self) -> None:
        """Test valid suggestion with code snippets."""
        suggestion = FixSuggestion(
            root_cause="Variable is constant",
            fix_description="Remove constant attribute",
            code_before='<localVars constant="true">',
            code_after="<localVars>",
            confidence=0.95,
        )
        assert suggestion.root_cause == "Variable is constant"
        assert suggestion.code_before is not None
        assert suggestion.code_after is not None
        assert suggestion.confidence == 0.95

    def test_valid_suggestion_without_code(self) -> None:
        """Test valid suggestion without code snippets."""
        suggestion = FixSuggestion(
            root_cause="POU body is empty",
            fix_description="Add ST code",
            confidence=0.75,
        )
        assert suggestion.code_before is None
        assert suggestion.code_after is None

    def test_confidence_bounds(self) -> None:
        """Test confidence must be between 0.0 and 1.0."""
        # Valid bounds
        FixSuggestion(root_cause="test", fix_description="test", confidence=0.0)
        FixSuggestion(root_cause="test", fix_description="test", confidence=1.0)
        FixSuggestion(root_cause="test", fix_description="test", confidence=0.5)

    def test_confidence_below_zero(self) -> None:
        """Test confidence below 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            FixSuggestion(root_cause="test", fix_description="test", confidence=-0.1)

    def test_confidence_above_one(self) -> None:
        """Test confidence above 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            FixSuggestion(root_cause="test", fix_description="test", confidence=1.1)


class TestClassifyRequest:
    """Tests for ClassifyRequest model."""

    def test_error_log_only(self) -> None:
        """Test request with only error_log."""
        request = ClassifyRequest(error_log="Error: build failed")
        assert request.error_log == "Error: build failed"
        assert request.source_xml is None

    def test_with_source_xml(self) -> None:
        """Test request with both error_log and source_xml."""
        request = ClassifyRequest(
            error_log="Error: build failed",
            source_xml="<project>...</project>",
        )
        assert request.error_log == "Error: build failed"
        assert request.source_xml == "<project>...</project>"

    def test_empty_error_log(self) -> None:
        """Test that empty error_log is allowed (validation happens in classifier)."""
        request = ClassifyRequest(error_log="")
        assert request.error_log == ""


class TestClassifyResponse:
    """Tests for ClassifyResponse model."""

    def test_valid_response(self) -> None:
        """Test valid response with multiple suggestions."""
        response = ClassifyResponse(
            classification=ErrorClassification(
                severity="blocking",
                stage="iec_compilation",
                complexity="trivial",
            ),
            suggestions=[
                FixSuggestion(
                    root_cause="Variable is constant",
                    fix_description="Remove constant attribute",
                    confidence=0.95,
                ),
                FixSuggestion(
                    root_cause="Alternative cause",
                    fix_description="Alternative fix",
                    confidence=0.80,
                ),
            ],
        )
        assert response.classification.severity == "blocking"
        assert len(response.suggestions) == 2
        assert response.suggestions[0].confidence > response.suggestions[1].confidence

    def test_single_suggestion(self) -> None:
        """Test response with single suggestion."""
        response = ClassifyResponse(
            classification=ErrorClassification(
                severity="warning",
                stage="xml_validation",
                complexity="trivial",
            ),
            suggestions=[
                FixSuggestion(
                    root_cause="DateTime format invalid",
                    fix_description="Use ISO 8601 format",
                    confidence=0.90,
                ),
            ],
        )
        assert len(response.suggestions) == 1


class TestClassifierOutput:
    """Tests for ClassifierOutput model (LLM schema)."""

    def test_json_serialization(self) -> None:
        """Test JSON serialization for LLM output."""
        output = ClassifierOutput(
            classification=ErrorClassification(
                severity="blocking",
                stage="code_generation",
                complexity="moderate",
            ),
            suggestions=[
                FixSuggestion(
                    root_cause="Empty body",
                    fix_description="Add code",
                    code_before="<body/>",
                    code_after="<body><ST>...</ST></body>",
                    confidence=0.85,
                ),
            ],
        )
        json_str = output.model_dump_json()
        assert "blocking" in json_str
        assert "code_generation" in json_str

    def test_json_deserialization(self) -> None:
        """Test JSON deserialization from LLM response."""
        json_str = """
        {
            "classification": {
                "severity": "blocking",
                "stage": "iec_compilation",
                "complexity": "trivial"
            },
            "suggestions": [
                {
                    "root_cause": "Constant assignment",
                    "fix_description": "Remove constant",
                    "code_before": null,
                    "code_after": null,
                    "confidence": 0.9
                }
            ]
        }
        """
        output = ClassifierOutput.model_validate_json(json_str)
        assert output.classification.severity == "blocking"
        assert len(output.suggestions) == 1
        assert output.suggestions[0].code_before is None
