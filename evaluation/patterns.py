"""Error pattern definitions for PLC error classifier evaluation.

This module defines the error patterns used to generate synthetic test cases.
Each pattern represents a specific type of error that can occur in the
Beremiz PLC development toolchain.

Target distribution: 100 total test cases
  - xml_validation: 20 (10 trivial, 8 moderate, 2 complex)
  - code_generation: 25 (8 trivial, 10 moderate, 7 complex)
  - iec_compilation: 40 (15 trivial, 18 moderate, 7 complex)
  - c_compilation: 15 (3 trivial, 8 moderate, 4 complex)

Severity distribution: ~75% blocking, ~20% warning, ~5% info
Complexity distribution: ~35% trivial, ~45% moderate, ~20% complex
"""

from typing import Literal

from pydantic import BaseModel


class ErrorPattern(BaseModel):
    """Definition of an error pattern to generate test cases from.

    Attributes:
        id: Unique identifier for the pattern.
        name: Human-readable name.
        stage: Build pipeline stage where error occurs.
        severity: Impact on build process.
            - "blocking": Build fails completely, cannot proceed.
            - "warning": Build continues despite the issue.
            - "info": Informational message, no impact.
        complexity: User's cognitive load to resolve the error.
            This measures how much effort a programmer needs to go from
            seeing the error to fixing it. It combines message clarity
            and domain knowledge required.
            - "trivial": Error message clearly states the problem AND the fix
              is immediately obvious. User reads error -> knows what to do.
              Example: "Variable 'X' not declared" -> add declaration.
            - "moderate": Error message indicates the problem but user needs
              to think, check documentation, or understand context to fix.
              Example: "undefined reference to 'X'" -> need to find missing library.
            - "complex": Error message is cryptic, misleading, or requires
              significant investigation/debugging to understand root cause.
              Example: Python traceback with no clear PLC-related message.
        error_message: The core error message pattern to match.
        category: Error category for grouping similar errors.
        description: What triggers this error.
        variations: Number of test case variations to generate (default=1).
    """

    id: str
    name: str
    stage: Literal["xml_validation", "code_generation", "iec_compilation", "c_compilation"]
    severity: Literal["blocking", "warning", "info"]
    complexity: Literal["trivial", "moderate", "complex"]
    error_message: str  # The core error message pattern
    category: str  # Error category for grouping
    description: str  # What triggers this error
    variations: int = 1  # Number of test cases to generate from this pattern


# =============================================================================
# XML Validation Errors (20 cases: 10 trivial, 8 moderate, 2 complex)
# =============================================================================

XML_VALIDATION_PATTERNS: list[ErrorPattern] = [
    # Trivial (10 cases)
    ErrorPattern(
        id="xml_001",
        name="datetime_format_error",
        stage="xml_validation",
        severity="warning",
        complexity="trivial",
        error_message="'{value}' is not a valid value of the atomic type 'xs:dateTime'",
        category="datetime_format",
        description="DateTime attribute uses space instead of 'T' separator",
        variations=3,
    ),
    ErrorPattern(
        id="xml_002",
        name="invalid_attribute_value",
        stage="xml_validation",
        severity="warning",
        complexity="trivial",
        error_message="'{value}' is not a valid value for attribute '{name}'",
        category="invalid_attribute",
        description="Attribute has invalid value for its type (e.g., negative for unsigned)",
        variations=3,
    ),
    ErrorPattern(
        id="xml_003",
        name="invalid_enum_value",
        stage="xml_validation",
        severity="warning",
        complexity="trivial",
        error_message="'{value}' is not an element of the set",
        category="invalid_attribute",
        description="Attribute value not in allowed enumeration",
        variations=2,
    ),
    ErrorPattern(
        id="xml_004",
        name="missing_required_attribute",
        stage="xml_validation",
        severity="blocking",
        complexity="trivial",
        error_message="The attribute '{name}' is required but missing",
        category="missing_attribute",
        description="Required attribute is not present on element",
        variations=2,
    ),
    # Moderate (8 cases)
    ErrorPattern(
        id="xml_005",
        name="missing_child_element",
        stage="xml_validation",
        severity="warning",
        complexity="moderate",
        error_message="Missing child element(s). Expected is one of",
        category="missing_child_element",
        description="Required child element is missing from parent",
        variations=3,
    ),
    ErrorPattern(
        id="xml_006",
        name="wrong_element_order",
        stage="xml_validation",
        severity="warning",
        complexity="moderate",
        error_message="Element '{name}' is not expected at this location",
        category="element_order",
        description="Child elements are in wrong order per schema",
        variations=2,
    ),
    ErrorPattern(
        id="xml_007",
        name="namespace_mismatch",
        stage="xml_validation",
        severity="blocking",
        complexity="moderate",
        error_message="No matching global declaration available for the validation root",
        category="namespace_error",
        description="XML namespace doesn't match PLCopen schema",
        variations=2,
    ),
    ErrorPattern(
        id="xml_008",
        name="invalid_content_type",
        stage="xml_validation",
        severity="warning",
        complexity="moderate",
        error_message="'{value}' is not a valid value of the atomic type",
        category="invalid_attribute",
        description="Element content doesn't match expected type (e.g., text in numeric field)",
        variations=1,
    ),
    # Complex (2 cases)
    ErrorPattern(
        id="xml_009",
        name="multi_element_violation",
        stage="xml_validation",
        severity="blocking",
        complexity="complex",
        error_message="This element is not expected. Expected is one of",
        category="schema_violation",
        description="Multiple schema violations requiring understanding of PLCopen structure",
        variations=1,
    ),
    ErrorPattern(
        id="xml_010",
        name="nested_type_mismatch",
        stage="xml_validation",
        severity="blocking",
        complexity="complex",
        error_message="Element content is not allowed for content model",
        category="schema_violation",
        description="Nested type definitions don't match schema constraints",
        variations=1,
    ),
]

# =============================================================================
# Code Generation Errors (25 cases: 8 trivial, 10 moderate, 7 complex)
# =============================================================================

CODE_GENERATION_PATTERNS: list[ErrorPattern] = [
    # Trivial (8 cases)
    ErrorPattern(
        id="codegen_001",
        name="no_body_defined",
        stage="code_generation",
        severity="blocking",
        complexity="trivial",
        error_message='No body defined in "{pou_name}" POU',
        category="no_body_defined",
        description="Body element is COMPLETELY MISSING from the POU XML. "
        "Beremiz shows clear error: 'No body defined in X POU'.",
        variations=3,
    ),
    ErrorPattern(
        id="codegen_002",
        name="undefined_block_type",
        stage="code_generation",
        severity="blocking",
        complexity="trivial",
        error_message='Undefined block type "{block_name}" in "{pou_name}" POU',
        category="undefined_block_type",
        description="Reference to unknown function block in FBD/LD",
        variations=3,
    ),
    ErrorPattern(
        id="codegen_003",
        name="no_variable_defined",
        stage="code_generation",
        severity="blocking",
        complexity="trivial",
        error_message='No variable defined in "{pou_name}" POU',
        category="missing_variable",
        description="POU has no variable declarations in interface section",
        variations=2,
    ),
    # Complex (Python tracebacks are cryptic for PLC developers)
    ErrorPattern(
        id="codegen_004",
        name="empty_body_nonetype",
        stage="code_generation",
        severity="blocking",
        complexity="complex",  # "NoneType" is meaningless to PLC developers
        error_message="AttributeError: 'NoneType' object has no attribute",
        category="nonetype_attribute",
        description="Body element EXISTS but is EMPTY (no ST/FBD/LD content). "
        "Causes Python traceback with NoneType error.",
        variations=3,
    ),
    ErrorPattern(
        id="codegen_005",
        name="connector_not_found",
        stage="code_generation",
        severity="blocking",
        complexity="moderate",
        error_message='No connector found corresponding to "{name}" continuation in "{pou_name}" POU',
        category="connector_error",
        description="FBD/LD continuation element references non-existent connector",
        variations=2,
    ),
    ErrorPattern(
        id="codegen_006",
        name="inout_not_connected",
        stage="code_generation",
        severity="blocking",
        complexity="moderate",
        error_message='InOut variable "{name}" in block "{block}" in POU "{pou_name}" must be connected',
        category="connection_error",
        description="InOut variable in function block not connected to both input and output",
        variations=2,
    ),
    ErrorPattern(
        id="codegen_007",
        name="duplicate_connector",
        stage="code_generation",
        severity="blocking",
        complexity="moderate",
        error_message='More than one connector found corresponding to "{name}" continuation in "{pou_name}" POU',
        category="connector_error",
        description="Multiple connectors with same name cause ambiguity in FBD/LD",
        variations=2,
    ),
    ErrorPattern(
        id="codegen_008",
        name="output_not_found",
        stage="code_generation",
        severity="blocking",
        complexity="moderate",
        error_message='No output "{output}" variable found in block "{block}" in POU "{pou_name}". Connection must be broken',
        category="connection_error",
        description="Block output variable referenced but not found - connection is broken",
        variations=1,
    ),
    # Moderate (SFC errors - message is clear but requires SFC knowledge)
    ErrorPattern(
        id="codegen_009",
        name="sfc_transition_not_connected",
        stage="code_generation",
        severity="blocking",
        complexity="moderate",  # Message is clear: "must be connected" - connect it
        error_message='SFC transition in POU "{pou_name}" must be connected',
        category="sfc_error",
        description="SFC transition element not properly connected to steps",
        variations=2,
    ),
    ErrorPattern(
        id="codegen_010",
        name="sfc_jump_invalid_step",
        stage="code_generation",
        severity="blocking",
        complexity="moderate",  # Message tells you which step is wrong
        error_message='SFC jump in pou "{pou_name}" refers to non-existent SFC step "{step}"',
        category="sfc_error",
        description="SFC jump element references a step name that doesn't exist",
        variations=2,
    ),
    ErrorPattern(
        id="codegen_011",
        name="sfc_transition_not_connected_prev",
        stage="code_generation",
        severity="blocking",
        complexity="moderate",  # Message is clear about what's wrong
        error_message='Transition with content "{transition}" not connected to a previous step in "{pou_name}" POU',
        category="sfc_error",
        description="SFC transition has no connection to a preceding step",
        variations=2,
    ),
    # Complex (cryptic errors requiring investigation)
    ErrorPattern(
        id="codegen_012",
        name="nested_pou_error",
        stage="code_generation",
        severity="blocking",
        complexity="complex",  # "KeyError:" is cryptic - requires investigation
        error_message="KeyError:",
        category="keyerror",
        description="Internal generator error from malformed nested POU structure",
        variations=1,
    ),
]

# =============================================================================
# IEC Compilation Errors (40 cases: 15 trivial, 18 moderate, 7 complex)
# =============================================================================

IEC_COMPILATION_PATTERNS: list[ErrorPattern] = [
    # Trivial (15 cases)
    ErrorPattern(
        id="iec_001",
        name="constant_assignment",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",
        error_message="Assignment to CONSTANT variables is not allowed",
        category="constant_assignment",
        description="Attempting to assign value to a constant variable",
        variations=2,
    ),
    ErrorPattern(
        id="iec_002",
        name="undeclared_variable",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",
        error_message="Variable not declared in this scope",
        category="undeclared_variable",
        description="Using a variable that hasn't been declared in the current scope",
        variations=2,
    ),
    ErrorPattern(
        id="iec_003",
        name="type_mismatch_assignment",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",
        error_message="Incompatible data types for ':=' operation",
        category="type_mismatch",
        description="Assignment between incompatible types (e.g., STRING to INT)",
        variations=2,
    ),
    ErrorPattern(
        id="iec_004",
        name="invalid_for_control_var",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",
        error_message="Invalid data type for 'FOR' control variable",
        category="invalid_for_loop",
        description="FOR loop control variable is not an integer type",
        variations=2,
    ),
    ErrorPattern(
        id="iec_005",
        name="invalid_if_condition",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",
        error_message="Invalid data type for 'IF' condition",
        category="invalid_condition",
        description="IF condition expression is not BOOL type",
        variations=2,
    ),
    ErrorPattern(
        id="iec_006",
        name="integer_overflow",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",
        error_message="Numerical value exceeds range",
        category="overflow",
        description="Integer literal too large for target type",
        variations=1,
    ),
    ErrorPattern(
        id="iec_007",
        name="invalid_time_syntax",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",
        error_message="Invalid syntax for TIME data type",
        category="syntax_error",
        description="Malformed TIME literal (e.g., T#1h2m instead of T#1h2m0s)",
        variations=1,
    ),
    ErrorPattern(
        id="iec_008",
        name="duplicate_parameter",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",
        error_message="Duplicate parameter",
        category="duplicate",
        description="Same parameter name used more than once in function/FB call",
        variations=1,
    ),
    ErrorPattern(
        id="iec_009",
        name="invalid_while_condition",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",
        error_message="Invalid data type for 'WHILE' condition",
        category="invalid_condition",
        description="WHILE condition is not BOOL type",
        variations=1,
    ),
    ErrorPattern(
        id="iec_010",
        name="case_not_integer",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",
        error_message="'CASE' quantity not an integer or enumerated",
        category="invalid_condition",
        description="CASE expression is not integer or enum type",
        variations=1,
    ),
    # Moderate (18 cases)
    ErrorPattern(
        id="iec_011",
        name="invalid_array_subscript",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",  # Clear message: use integer for array index
        error_message="Invalid data type for array subscript",
        category="array_error",
        description="Non-integer used as array index",
        variations=2,
    ),
    ErrorPattern(
        id="iec_012",
        name="struct_field_not_found",
        stage="iec_compilation",
        severity="blocking",
        complexity="moderate",
        error_message="Undeclared structured (or FB) variable, or non-existant field in structure",
        category="struct_error",
        description="Accessing non-existent field on struct or FB instance",
        variations=2,
    ),
    ErrorPattern(
        id="iec_013",
        name="function_param_type_mismatch",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",  # Message shows "Expected X, got Y" - fix is clear
        error_message="Data type incompatibility between parameter",
        category="function_error",
        description="Function called with incompatible parameter type",
        variations=2,
    ),
    ErrorPattern(
        id="iec_014",
        name="return_type_mismatch",
        stage="iec_compilation",
        severity="blocking",
        complexity="moderate",
        error_message="Type mismatch for 'RETURN' value",
        category="function_error",
        description="Function returns wrong type",
        variations=2,
    ),
    ErrorPattern(
        id="iec_015",
        name="invalid_function_parameters",
        stage="iec_compilation",
        severity="blocking",
        complexity="moderate",
        error_message="Invalid parameters when invoking",
        category="function_error",
        description="Function/FB invoked with invalid or missing parameters",
        variations=2,
    ),
    ErrorPattern(
        id="iec_016",
        name="array_bounds_exceeded",
        stage="iec_compilation",
        severity="blocking",
        complexity="moderate",
        error_message="Array subscript out of range",
        category="array_error",
        description="Array index exceeds declared bounds",
        variations=2,
    ),
    ErrorPattern(
        id="iec_017",
        name="ambiguous_enum_or_undeclared",
        stage="iec_compilation",
        severity="blocking",
        complexity="moderate",
        error_message="Ambiguous enumerate value or Variable not declared in this scope",
        category="enum_error",
        description="Identifier could be enum value or undeclared variable - ambiguous",
        variations=2,
    ),
    ErrorPattern(
        id="iec_018",
        name="string_length_exceeded",
        stage="iec_compilation",
        severity="blocking",
        complexity="moderate",
        error_message="Numerical value exceeds range for STRING data type",
        category="string_error",
        description="String literal longer than maximum allowed STRING size",
        variations=2,
    ),
    ErrorPattern(
        id="iec_019",
        name="fb_output_assignment",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",  # "not allowed" - fix is obvious: don't assign to outputs
        error_message="Assignment to FB output variable is not allowed",
        category="fb_error",
        description="Attempting to assign a value to a function block output variable",
        variations=2,
    ),
    # Complex (truly cryptic errors requiring investigation)
    ErrorPattern(
        id="iec_020",
        name="cascading_type_errors",
        stage="iec_compilation",
        severity="blocking",
        complexity="complex",  # Multiple errors from one root cause - requires investigation
        error_message="Incompatible data types",
        category="cascading_error",
        description="One type error causes multiple downstream errors",
        variations=2,
    ),
    ErrorPattern(
        id="iec_021",
        name="overload_resolution_ambiguous",
        stage="iec_compilation",
        severity="blocking",
        complexity="complex",  # Requires understanding overload resolution rules
        error_message="Unable to resolve which overloaded",
        category="overload_error",
        description="Multiple function overloads match call signature - compiler cannot choose",
        variations=2,
    ),
    # Trivial (message clearly states problem and fix is obvious)
    ErrorPattern(
        id="iec_022",
        name="for_control_var_assignment",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",  # "not allowed" - obviously don't do it
        error_message="Assignment to FOR control variable is not allowed",
        category="loop_error",
        description="Attempting to modify the FOR loop control variable inside the loop body",
        variations=1,
    ),
    ErrorPattern(
        id="iec_023",
        name="literal_assignment",
        stage="iec_compilation",
        severity="blocking",
        complexity="trivial",  # "not allowed" - obviously don't assign to literals
        error_message="Assignment to an expression or a literal value is not allowed",
        category="assignment_error",
        description="Attempting to assign to a literal or computed expression (not an lvalue)",
        variations=2,
    ),
]

# =============================================================================
# C Compilation Errors (15 cases: 3 trivial, 8 moderate, 4 complex)
# =============================================================================

C_COMPILATION_PATTERNS: list[ErrorPattern] = [
    # Moderate (C errors - PLC devs understand C but need to trace back to PLC code)
    ErrorPattern(
        id="c_001",
        name="simple_syntax_error",
        stage="c_compilation",
        severity="blocking",
        complexity="moderate",  # Understand error, need to trace back to PLC code
        error_message="error: expected ';'",
        category="syntax_error",
        description="Basic C syntax error from malformed generated code",
        variations=2,
    ),
    ErrorPattern(
        id="c_002",
        name="undeclared_identifier",
        stage="c_compilation",
        severity="blocking",
        complexity="moderate",  # Understand error, need to trace back to PLC code
        error_message="error: undeclared identifier",
        category="undeclared",
        description="C variable not declared (generator bug)",
        variations=1,
    ),
    # Complex (linker/C errors are foreign to PLC developers)
    ErrorPattern(
        id="c_003",
        name="undefined_reference",
        stage="c_compilation",
        severity="blocking",
        complexity="complex",  # PLC devs don't understand linker errors
        error_message="undefined reference to",
        category="linker_error",
        description="Linker cannot find symbol definition",
        variations=3,
    ),
    ErrorPattern(
        id="c_004",
        name="missing_header",
        stage="c_compilation",
        severity="blocking",
        complexity="complex",  # PLC devs don't understand C includes
        error_message="fatal error: No such file or directory",
        category="include_error",
        description="Required header file not found",
        variations=2,
    ),
    ErrorPattern(
        id="c_005",
        name="incompatible_pointer_type",
        stage="c_compilation",
        severity="warning",
        complexity="moderate",  # PLC devs understand C, need to trace back
        error_message="warning: incompatible pointer type",
        category="type_error",
        description="Pointer type mismatch in generated code",
        variations=2,
    ),
    ErrorPattern(
        id="c_006",
        name="implicit_declaration",
        stage="c_compilation",
        severity="warning",
        complexity="moderate",  # PLC devs understand C, need to trace back
        error_message="warning: implicit declaration of function",
        category="undeclared",
        description="Function used without declaration/prototype",
        variations=1,
    ),
    # Complex (4 cases)
    ErrorPattern(
        id="c_007",
        name="multiple_definition",
        stage="c_compilation",
        severity="blocking",
        complexity="complex",
        error_message="multiple definition of",
        category="linker_error",
        description="Symbol defined in multiple object files",
        variations=1,
    ),
    ErrorPattern(
        id="c_008",
        name="library_not_found",
        stage="c_compilation",
        severity="blocking",
        complexity="complex",
        error_message="cannot find -l",
        category="linker_error",
        description="Required library not found during linking",
        variations=1,
    ),
    ErrorPattern(
        id="c_009",
        name="architecture_mismatch",
        stage="c_compilation",
        severity="blocking",
        complexity="complex",
        error_message="incompatible with target",
        category="build_config",
        description="Object file compiled for different architecture",
        variations=1,
    ),
    ErrorPattern(
        id="c_010",
        name="relocation_error",
        stage="c_compilation",
        severity="blocking",
        complexity="complex",
        error_message="relocation truncated to fit",
        category="linker_error",
        description="Linking error from address space issues",
        variations=1,
    ),
]

# =============================================================================
# Combined Pattern List
# =============================================================================

ERROR_PATTERNS: list[ErrorPattern] = (
    XML_VALIDATION_PATTERNS
    + CODE_GENERATION_PATTERNS
    + IEC_COMPILATION_PATTERNS
    + C_COMPILATION_PATTERNS
)


# =============================================================================
# Distribution Utilities
# =============================================================================


def get_pattern_distribution() -> dict:
    """Get the distribution statistics for ERROR_PATTERNS.

    Returns:
        Dict with counts by stage, severity, and complexity.
    """
    total_cases = sum(p.variations for p in ERROR_PATTERNS)

    by_stage: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_complexity: dict[str, int] = {}

    for p in ERROR_PATTERNS:
        by_stage[p.stage] = by_stage.get(p.stage, 0) + p.variations
        by_severity[p.severity] = by_severity.get(p.severity, 0) + p.variations
        by_complexity[p.complexity] = by_complexity.get(p.complexity, 0) + p.variations

    return {
        "total_cases": total_cases,
        "by_stage": by_stage,
        "by_severity": by_severity,
        "by_complexity": by_complexity,
    }


def get_patterns_by_stage(
    stage: Literal["xml_validation", "code_generation", "iec_compilation", "c_compilation"],
) -> list[ErrorPattern]:
    """Get all patterns for a specific build stage.

    Args:
        stage: The build pipeline stage to filter by.

    Returns:
        List of ErrorPattern objects for that stage.
    """
    return [p for p in ERROR_PATTERNS if p.stage == stage]


def get_patterns_by_complexity(
    complexity: Literal["trivial", "moderate", "complex"],
) -> list[ErrorPattern]:
    """Get all patterns for a specific complexity level.

    Args:
        complexity: The complexity level to filter by.

    Returns:
        List of ErrorPattern objects for that complexity.
    """
    return [p for p in ERROR_PATTERNS if p.complexity == complexity]
