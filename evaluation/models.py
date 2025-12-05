"""Data models for evaluation framework."""

from typing import Literal

from pydantic import BaseModel, Field

# ============================================================================
# Ground Truth / Test Case Models
# ============================================================================


class ExpectedClassification(BaseModel):
    """Ground truth classification for a test case."""

    severity: Literal["blocking", "warning", "info"]
    stage: Literal["xml_validation", "code_generation", "iec_compilation", "c_compilation"]
    complexity: Literal["trivial", "moderate", "complex"]


class ExpectedFix(BaseModel):
    """Ground truth fix information for a test case."""

    root_cause: str  # What's actually wrong
    fix_description: str  # How to fix it
    fix_location: str | None = None  # Where in the code (e.g., "line 30", "localVars section")


class TestCase(BaseModel):
    """A single test case for evaluation."""

    id: str  # Unique identifier (e.g., "test_001")
    name: str  # Descriptive name (e.g., "for_loop_invalid_control_var")
    description: str  # Human-readable description

    # Input data
    error_log: str  # The build output/error log
    source_xml: str | None = None  # Optional PLCopen XML source

    # Ground truth
    expected_classification: ExpectedClassification
    expected_fix: ExpectedFix

    # Metadata for analysis
    error_category: str  # Category (e.g., "type_mismatch", "undeclared_var")
    base_pattern: str  # The error pattern this was generated from


class TestSuite(BaseModel):
    """Collection of test cases."""

    name: str
    description: str
    test_cases: list[TestCase]
    version: str = "1.0.0"


# ============================================================================
# Evaluation Result Models
# ============================================================================


class ClassificationResult(BaseModel):
    """Result of classifying a single test case."""

    test_case_id: str

    # Predicted values
    predicted_severity: str
    predicted_stage: str
    predicted_complexity: str

    # Expected values (for comparison)
    expected_severity: str
    expected_stage: str
    expected_complexity: str

    # Match indicators
    severity_correct: bool
    stage_correct: bool
    complexity_correct: bool
    all_correct: bool


class SuggestionResult(BaseModel):
    """Result of evaluating suggestion quality for a single test case."""

    test_case_id: str

    # Predicted suggestion
    predicted_root_cause: str
    predicted_fix_description: str
    confidence: float

    # Expected values
    expected_root_cause: str
    expected_fix_description: str

    # Quality scores (from LLM judge)
    root_cause_score: float = Field(ge=0.0, le=1.0)  # How well root cause was identified
    fix_quality_score: float = Field(ge=0.0, le=1.0)  # How actionable/correct the fix is
    overall_score: float = Field(ge=0.0, le=1.0)  # Combined quality
    judge_reasoning: str  # Explanation from the judge


class TestCaseResult(BaseModel):
    """Complete evaluation result for a single test case."""

    test_case_id: str
    test_case_name: str
    classification: ClassificationResult
    suggestion: SuggestionResult
    response_time_ms: float


# ============================================================================
# Aggregate Metrics Models
# ============================================================================


class ConfidenceInterval(BaseModel):
    """Confidence interval for a metric.

    Represents the uncertainty in a point estimate using bootstrap resampling.
    """

    point_estimate: float = Field(description="The observed value of the metric")
    ci_lower: float = Field(description="Lower bound of confidence interval")
    ci_upper: float = Field(description="Upper bound of confidence interval")
    confidence_level: float = Field(
        default=0.95, ge=0.0, le=1.0, description="Confidence level (e.g., 0.95 for 95%)"
    )
    n_bootstrap: int = Field(default=1000, description="Number of bootstrap samples used")
    std_error: float = Field(default=0.0, ge=0.0, description="Bootstrap standard error")

    @property
    def margin_of_error(self) -> float:
        """Half-width of the confidence interval."""
        return (self.ci_upper - self.ci_lower) / 2


class ClassificationMetrics(BaseModel):
    """Aggregate metrics for classification accuracy."""

    total_cases: int

    # Per-dimension accuracy
    severity_accuracy: float = Field(ge=0.0, le=1.0)
    stage_accuracy: float = Field(ge=0.0, le=1.0)
    complexity_accuracy: float = Field(ge=0.0, le=1.0)

    # Overall (all three correct)
    overall_accuracy: float = Field(ge=0.0, le=1.0)

    # Breakdown by stage
    accuracy_by_stage: dict[str, float] = {}

    # Breakdown by severity
    accuracy_by_severity: dict[str, float] = {}

    # Confidence intervals (optional, populated when bootstrap is run)
    severity_accuracy_ci: ConfidenceInterval | None = None
    stage_accuracy_ci: ConfidenceInterval | None = None
    complexity_accuracy_ci: ConfidenceInterval | None = None
    overall_accuracy_ci: ConfidenceInterval | None = None


class SuggestionMetrics(BaseModel):
    """Aggregate metrics for suggestion quality."""

    total_cases: int

    # Average scores
    avg_root_cause_score: float = Field(ge=0.0, le=1.0)
    avg_fix_quality_score: float = Field(ge=0.0, le=1.0)
    avg_overall_score: float = Field(ge=0.0, le=1.0)

    # Distribution
    high_quality_count: int = 0  # score >= 0.8
    medium_quality_count: int = 0  # 0.5 <= score < 0.8
    low_quality_count: int = 0  # score < 0.5

    # Confidence intervals (optional, populated when bootstrap is run)
    root_cause_score_ci: ConfidenceInterval | None = None
    fix_quality_score_ci: ConfidenceInterval | None = None
    overall_score_ci: ConfidenceInterval | None = None


class PerformanceMetrics(BaseModel):
    """Performance timing metrics."""

    total_cases: int
    avg_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    p95_response_time_ms: float

    # Confidence intervals (optional, populated when bootstrap is run)
    avg_response_time_ci: ConfidenceInterval | None = None
    p95_response_time_ci: ConfidenceInterval | None = None


class EvaluationReport(BaseModel):
    """Complete evaluation report."""

    # Metadata
    report_name: str
    timestamp: str
    model_used: str
    test_suite_name: str
    test_suite_version: str

    # Metrics
    classification_metrics: ClassificationMetrics
    suggestion_metrics: SuggestionMetrics
    performance_metrics: PerformanceMetrics

    # Detailed results
    results: list[TestCaseResult]

    # Failure analysis
    failed_cases: list[str] = []  # IDs of cases where classification was wrong
    low_quality_suggestions: list[str] = []  # IDs of cases with low suggestion scores


# ============================================================================
# Complexity Heuristics
# ============================================================================


COMPLEXITY_HEURISTICS: dict[str, Literal["trivial", "moderate", "complex"]] = {
    # XML Validation - mostly trivial (schema issues)
    "datetime_format": "trivial",
    "missing_child_element": "moderate",
    "invalid_attribute": "trivial",
    "namespace_error": "moderate",
    # Code Generation - moderate to complex (Beremiz internal)
    "nonetype_attribute": "moderate",  # Empty body, need to add content
    "keyerror_config": "moderate",
    "index_out_of_range": "moderate",
    "no_body_defined": "moderate",
    "undefined_block_type": "complex",  # Need to understand block library
    "connector_not_found": "complex",  # FBD/LD connection issues
    "sfc_transition_error": "complex",  # SFC is architecturally complex
    # IEC Compilation - varies by error type
    "constant_assignment": "trivial",  # Just remove constant modifier
    "undeclared_variable": "trivial",  # Add declaration
    "type_mismatch_simple": "trivial",  # Wrong literal type
    "type_mismatch_complex": "moderate",  # Need type conversion
    "invalid_for_loop": "trivial",  # Fix loop variable type
    "invalid_condition_type": "trivial",  # Should be BOOL
    "array_subscript_error": "moderate",  # Need to understand array bounds
    "function_parameter_error": "moderate",  # Need to check function signature
    "overload_resolution": "complex",  # Multiple possible fixes
    "cascading_type_errors": "complex",  # One fix may resolve multiple errors
    # C Compilation - usually moderate (generated code issues)
    "undefined_reference": "moderate",  # Missing library or function
    "missing_header": "moderate",  # Include path issue
    "linker_error": "complex",  # Build configuration issue
}


SEVERITY_RULES: dict[str, Literal["blocking", "warning", "info"]] = {
    # Blocking - build cannot complete
    "error:": "blocking",
    "Error:": "blocking",
    "AttributeError": "blocking",
    "KeyError": "blocking",
    "IndexError": "blocking",
    "TypeError": "blocking",
    "undefined reference": "blocking",
    "ld returned": "blocking",
    "Bailing out": "blocking",
    "Cannot build project": "blocking",
    "compilation failed": "blocking",
    # Warning - build may complete but with issues
    "Warning:": "warning",  # Note: some warnings are actually blocking
    "warning:": "warning",
    "deprecated": "warning",
    # Info - informational only
    "Collecting": "info",
    "Generating": "info",
    "Compiling": "info",
}


STAGE_INDICATORS: dict[
    str, Literal["xml_validation", "code_generation", "iec_compilation", "c_compilation"]
] = {
    # XML Validation
    "XSD schema": "xml_validation",
    "XML file doesn't follow": "xml_validation",
    "plcopen.org/xml": "xml_validation",
    # Code Generation
    "/beremiz/PLCGenerator": "code_generation",
    "/beremiz/ProjectController": "code_generation",
    "/beremiz/PLCControler": "code_generation",
    "Generating SoftPLC": "code_generation",
    "AttributeError": "code_generation",  # Python errors in generator
    # IEC Compilation
    "iec2c": "iec_compilation",
    "IEC to C compiler": "iec_compilation",
    "matiec": "iec_compilation",
    "/build/plc.st:": "iec_compilation",
    # C Compilation
    "gcc": "c_compilation",
    "undefined reference": "c_compilation",
    "ld returned": "c_compilation",
    ".c:": "c_compilation",
}
