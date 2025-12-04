"""Pydantic models for PLC Error Classifier."""

from typing import Literal

from pydantic import BaseModel, Field

# =============================================================================
# API Request/Response Models
# =============================================================================


class ClassifyRequest(BaseModel):
    """API request model."""

    error_log: str = Field(description="Build output/error log from Beremiz")
    source_xml: str | None = Field(
        default=None,
        description="Optional PLCopen XML source for richer suggestions",
    )


class ErrorClassification(BaseModel):
    """Classification result with constrained values."""

    severity: Literal["blocking", "warning", "info"] = Field(
        description="Impact on build: blocking=fails, warning=succeeds with issues, info=no impact"
    )
    stage: Literal["xml_validation", "code_generation", "iec_compilation", "c_compilation"] = Field(
        description="Build pipeline stage where error occurred"
    )
    complexity: Literal["trivial", "moderate", "complex"] = Field(
        description="Effort to fix: trivial=one-line, moderate=context needed, complex=architectural"
    )


class FixSuggestion(BaseModel):
    """Fix suggestion with root cause analysis and optional code snippets."""

    root_cause: str = Field(description="What's actually wrong")
    fix_description: str = Field(description="How to fix the issue")
    code_before: str | None = Field(
        default=None,
        description="Code snippet showing the problematic code (only when source_xml provided)",
    )
    code_after: str | None = Field(
        default=None,
        description="Code snippet showing the fix (only when source_xml provided)",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score 0.0-1.0",
    )


class ClassifyResponse(BaseModel):
    """API response model."""

    classification: ErrorClassification
    suggestions: list[FixSuggestion] = Field(
        description="1-3 actionable fix suggestions, ranked by confidence"
    )


# =============================================================================
# Internal Models (for LLM structured output)
# =============================================================================


class ClassifierOutput(BaseModel):
    """Schema for LLM structured output.

    This is what we ask Gemini to produce directly.
    """

    classification: ErrorClassification
    suggestions: list[FixSuggestion] = Field(
        description="1-3 actionable fix suggestions, ranked by confidence"
    )
