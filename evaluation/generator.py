"""Synthetic test case generator for PLC error classifier evaluation."""

import asyncio
import os
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from json_repair import repair_json
from pydantic import BaseModel, Field

from .models import (
    EvalTestCase,
    EvalTestSuite,
    ExpectedClassification,
    ExpectedFix,
)
from .patterns import ERROR_PATTERNS, ErrorPattern, get_pattern_distribution

# Load environment variables
load_dotenv()

# Rate limiting: max concurrent API requests to avoid hitting limits
MAX_CONCURRENT_REQUESTS = 5

# ============================================================================
# Generated Test Case Schema
# ============================================================================


class GeneratedTestCase(BaseModel):
    """Schema for LLM-generated test case output.

    Reuses ExpectedFix fields for consistency with ground truth format.
    """

    error_log: str = Field(description="The realistic error log for this pattern")
    root_cause: str = Field(description="What is actually wrong")
    fix_description: str = Field(description="How to fix the error")
    fix_location: str | None = Field(
        default=None, description="Where in the code the fix should be applied"
    )
    source_xml: str | None = Field(
        default=None, description="Optional PLCopen XML source that would trigger this error"
    )


# ============================================================================
# Configuration
# ============================================================================

# Use Flash-Lite for generation (cost-efficient, similar quality for this task)
GENERATOR_MODEL = "gemini-2.5-flash-lite"

# Path to sample data for few-shot examples
SAMPLE_DATA_DIR = Path(__file__).parent.parent / "sample_data"

# Output directory for generated test cases
TEST_CASES_DIR = Path(__file__).parent / "test_cases"


# Note: ErrorPattern class, ERROR_PATTERNS list, and get_pattern_distribution()
# are now imported from .patterns module for maintainability.


# ============================================================================
# XML Validation
# ============================================================================


def validate_xml(xml_string: str) -> tuple[bool, str | None]:
    """Validate that an XML string is well-formed.

    Args:
        xml_string: The XML content to validate.

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is None.
    """
    if not xml_string or not xml_string.strip():
        return True, None  # Empty XML is acceptable

    try:
        ET.fromstring(xml_string)
        return True, None
    except ET.ParseError as e:
        return False, str(e)


# ============================================================================
# Few-Shot Examples
# ============================================================================


def load_sample_data() -> dict[str, dict[str, str]]:
    """Load sample error logs and XML files.

    Samples cover all 4 build stages:
    - xml_datetime_error: xml_validation stage
    - empty_project: code_generation stage
    - constant_error: iec_compilation stage
    - c_linker_error: c_compilation stage
    """
    samples = {}

    sample_names = [
        "xml_datetime_error",  # xml_validation
        "empty_project",  # code_generation
        "constant_error",  # iec_compilation
        "c_linker_error",  # c_compilation
    ]

    for name in sample_names:
        txt_path = SAMPLE_DATA_DIR / f"{name}.txt"
        xml_path = SAMPLE_DATA_DIR / f"{name}.xml"

        samples[name] = {
            "error_log": txt_path.read_text() if txt_path.exists() else "",
            "source_xml": xml_path.read_text() if xml_path.exists() else "",
        }

    return samples


# ============================================================================
# Generator Prompt
# ============================================================================

SYSTEM_PROMPT = """<role>
You are an IEC 61131-3 PLC expert generating test cases for a Beremiz error classifier.
</role>

<critical_rules>
IMPORTANT - Read these first:
1. The error_message pattern provided MUST appear exactly in your error_log
2. source_xml MUST be syntactically valid XML (parseable, matching tags, escaped special chars)
3. XML errors should be SEMANTIC (wrong values), not SYNTACTIC (malformed tags)
4. source_xml is REQUIRED for xml_validation and code_generation stages
</critical_rules>

<context>
Beremiz build pipeline stages:
- xml_validation: PLCopen XML schema validation (Warning: PLC XML file doesn't follow XSD schema)
- code_generation: Python PLCGenerator errors (Traceback or "Error: No body defined")
- iec_compilation: matiec/iec2c errors (plc.st:line-col: error: message)
- c_compilation: gcc/linker errors (undefined reference, No such file)
</context>

<output_format>
JSON with: error_log, source_xml, root_cause, fix_description, fix_location
</output_format>

<error_log_format>
[HH:MM:SS]: Building project...
[HH:MM:SS]: Cannot build project.
stdout: Start build in /tmp/.tmpXXX/build
Generating SoftPLC IEC-61131 ST/IL/SFC code...
[stage-specific output]
stderr: [error messages]
Error: [final error]
</error_log_format>

<variety>
Use different variable names, data types (INT, REAL, STRING, BOOL, TIME), POU names, and line numbers.
</variety>
"""

USER_PROMPT_TEMPLATE = """<pattern>
ID: {pattern_id}
Name: {pattern_name}
Stage: {stage}
Severity: {severity}
Complexity: {complexity}
Error Message: {error_message}
Description: {description}
</pattern>

<examples>
<example stage="xml_validation">
<error_log>
{xml_datetime_error_log}
</error_log>
<source_xml>
{xml_datetime_error_xml}
</source_xml>
</example>

<example stage="code_generation">
<error_log>
{empty_project_log}
</error_log>
<source_xml>
{empty_project_xml}
</source_xml>
</example>

<example stage="iec_compilation">
<error_log>
{constant_error_log}
</error_log>
<source_xml>
{constant_error_xml}
</source_xml>
</example>

<example stage="c_compilation">
<error_log>
{c_linker_error_log}
</error_log>
<source_xml>
{c_linker_error_xml}
</source_xml>
</example>
</examples>

<complexity_guidelines>
The error log MUST match the specified complexity level:

TRIVIAL: Error message clearly states the problem AND fix is immediately obvious.
- Use DIRECT, CLEAR error messages (e.g., "Variable 'X' not declared", "Type mismatch")
- Include the exact offending element in the error (variable name, line number)
- NO cascading errors, NO tracebacks, NO cryptic messages
- A competent engineer reads it and knows EXACTLY what to fix

MODERATE: Error indicates the problem but requires some investigation or tracing.
- Error is understandable but requires context to fix
- May need to trace from generated code back to source
- Include enough context but don't spell out the exact fix
- Examples: C syntax errors (understand error but must find PLC source), XML schema errors

COMPLEX: Error is cryptic, misleading, or requires significant investigation.
- Use CRYPTIC messages: tracebacks, NoneType errors, cascading errors
- Include multiple unrelated-looking errors where root cause is hidden
- Linker errors (undefined reference) where source is unclear
- Python internal errors with no clear user action
- Engineer thinks: "What does this even mean?" or "Where do I start?"
</complexity_guidelines>

<task>
Generate a test case for the "{pattern_name}" pattern.
- Stage must be: {stage}
- Complexity must be: {complexity} (CRITICAL: follow complexity_guidelines above!)
- Error log MUST contain: {error_message}
- Use different names/values than the examples
- source_xml must be valid, parseable XML
</task>"""


# ============================================================================
# Generator Class
# ============================================================================


class SyntheticTestGenerator:
    """Generates synthetic test cases using Gemini.

    Uses async API with concurrent requests for better performance.
    Rate-limited to MAX_CONCURRENT_REQUESTS to avoid API limits.
    """

    def __init__(self, api_key: str | None = None):
        """Initialize the generator."""
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        self.client = genai.Client(api_key=self.api_key)
        self.samples = load_sample_data()
        self._semaphore: asyncio.Semaphore | None = None

    async def generate_test_case(
        self,
        aclient: genai.Client,
        pattern: ErrorPattern,
        variation_num: int = 1,
        use_search: bool = False,
        max_retries: int = 3,
    ) -> EvalTestCase:
        """Generate a single test case for an error pattern.

        Args:
            aclient: Async Gemini client (from client.aio context manager).
            pattern: The error pattern to generate a test case for.
            variation_num: Variation number (1-based) for unique IDs and prompting.
            use_search: If True, enables Google Search grounding for better accuracy.
            max_retries: Maximum retries if XML validation fails.

        Returns:
            A TestCase with generated error log and ground truth labels.
        """
        # Rate limiting
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        last_xml_error: str | None = None

        for attempt in range(max_retries):
            async with self._semaphore:
                # Build prompt with all 4 stage examples
                # Add XML error feedback if retrying
                retry_hint = ""
                if last_xml_error:
                    retry_hint = f"""

**IMPORTANT: Your previous XML was malformed!**
Error: {last_xml_error}

Please ensure the source_xml is syntactically valid XML. The errors should be SEMANTIC (wrong values, missing elements for the build stage), not SYNTACTIC (broken tags, unescaped characters).
"""

                user_prompt = (
                    USER_PROMPT_TEMPLATE.format(
                        pattern_id=pattern.id,
                        pattern_name=pattern.name,
                        stage=pattern.stage,
                        severity=pattern.severity,
                        complexity=pattern.complexity,
                        error_message=pattern.error_message,
                        description=pattern.description,
                        # Error logs
                        xml_datetime_error_log=self.samples["xml_datetime_error"]["error_log"],
                        empty_project_log=self.samples["empty_project"]["error_log"],
                        constant_error_log=self.samples["constant_error"]["error_log"],
                        c_linker_error_log=self.samples["c_linker_error"]["error_log"],
                        # XML sources - crucial for teaching correct XML structure
                        xml_datetime_error_xml=self.samples["xml_datetime_error"]["source_xml"],
                        empty_project_xml=self.samples["empty_project"]["source_xml"],
                        constant_error_xml=self.samples["constant_error"]["source_xml"],
                        c_linker_error_xml=self.samples["c_linker_error"]["source_xml"],
                    )
                    + retry_hint
                )

                # Configure generation
                # Per GEMINI_PROMPTING.md:
                # - Use temperature=1.0 when using Google Search (recommended for grounded responses)
                # - Use temperature=0.7-1.0 for generation/creative tasks
                #
                # IMPORTANT: google_search tool cannot be combined with response_mime_type
                # on gemini-2.5 models (only works on gemini-3-pro-preview).
                # When using search, we request JSON in the prompt and parse manually.
                if use_search:
                    config = types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=1.0,  # Recommended for grounded responses
                        # NOTE: Cannot use response_mime_type with google_search on 2.5 models
                        tools=[types.Tool(google_search=types.GoogleSearch())],
                    )
                else:
                    config = types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.8,  # Some creativity for variety
                        response_mime_type="application/json",
                        response_json_schema=GeneratedTestCase.model_json_schema(),
                        # Enable thinking for better quality test generation
                        # Flash-Lite has thinking OFF by default
                        thinking_config=types.ThinkingConfig(thinking_budget=1024),
                    )

                # Generate using async API
                response = await aclient.models.generate_content(
                    model=GENERATOR_MODEL,
                    contents=user_prompt,
                    config=config,
                )

                # Parse response using json_repair
                # Handles markdown code blocks and malformed JSON from LLM output
                try:
                    result = repair_json(response.text, return_objects=True)
                except Exception as e:
                    raise ValueError(
                        f"Failed to parse generator response: {e}\nResponse: {response.text}"
                    ) from e

                # Validate XML if present
                source_xml = result.get("source_xml")
                if source_xml:
                    is_valid, xml_error = validate_xml(source_xml)
                    if not is_valid:
                        last_xml_error = xml_error
                        if attempt < max_retries - 1:
                            print(
                                f"  XML validation failed for {pattern.name} "
                                f"(attempt {attempt + 1}/{max_retries}): {xml_error}"
                            )
                            continue  # Retry
                        else:
                            print(
                                f"  WARNING: XML still invalid after {max_retries} attempts "
                                f"for {pattern.name}"
                            )
                            # Continue with invalid XML - we'll report it in quality check

                # Build test case with variation-aware ID
                variation_suffix = f"_v{variation_num}" if variation_num > 1 else ""
                return EvalTestCase(
                    id=f"test_{pattern.id}{variation_suffix}_{uuid.uuid4().hex[:8]}",
                    name=f"{pattern.name}{variation_suffix}",
                    description=f"Generated test case for {pattern.name} (variation {variation_num}): {pattern.description}",
                    error_log=result["error_log"],
                    source_xml=source_xml,
                    expected_classification=ExpectedClassification(
                        severity=pattern.severity,
                        stage=pattern.stage,
                        complexity=pattern.complexity,
                    ),
                    expected_fix=ExpectedFix(
                        root_cause=result["root_cause"],
                        fix_description=result["fix_description"],
                        fix_location=result.get("fix_location"),
                    ),
                    error_category=pattern.category,
                    base_pattern=pattern.error_message,
                )

        # Should not reach here, but just in case
        raise ValueError(f"Failed to generate valid test case for {pattern.name}")

    async def generate_test_suite(
        self,
        patterns: list[ErrorPattern] | None = None,
        use_search_for_complex: bool = True,
    ) -> EvalTestSuite:
        """Generate a complete test suite with concurrent requests.

        Generates multiple variations per pattern based on pattern.variations.

        Args:
            patterns: List of error patterns to generate. Defaults to all ERROR_PATTERNS.
            use_search_for_complex: If True, uses Google Search for complex patterns.

        Returns:
            A TestSuite containing all generated test cases.
        """
        patterns = patterns or ERROR_PATTERNS

        # Calculate total expected cases
        total_variations = sum(p.variations for p in patterns)
        print(f"Generating {total_variations} test cases from {len(patterns)} patterns...")

        # Use async context manager for proper resource cleanup
        async with self.client.aio as aclient:
            # Create tasks for all pattern variations
            tasks = []
            task_info = []  # Track (pattern, variation_num) for error reporting

            for pattern in patterns:
                use_search = use_search_for_complex and pattern.complexity == "complex"
                # Generate multiple variations per pattern
                for var_num in range(1, pattern.variations + 1):
                    task = self._generate_with_logging(aclient, pattern, var_num, use_search)
                    tasks.append(task)
                    task_info.append((pattern, var_num))

            # Run concurrently (rate-limited by semaphore)
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful results
        test_cases: list[EvalTestCase] = []
        failed_count = 0
        for (pattern, var_num), result in zip(task_info, results, strict=False):
            if isinstance(result, Exception):
                var_label = f" (v{var_num})" if pattern.variations > 1 else ""
                print(f"Failed to generate {pattern.name}{var_label}: {result}")
                failed_count += 1
            else:
                test_cases.append(result)

        if failed_count > 0:
            print(f"\nWarning: {failed_count} test cases failed to generate")

        return EvalTestSuite(
            name="PLC Error Classifier Evaluation Suite",
            description=f"Synthetic test cases covering all 4 build stages ({len(test_cases)} cases)",
            test_cases=test_cases,
            version="1.0.0",
        )

    async def _generate_with_logging(
        self,
        aclient: genai.Client,
        pattern: ErrorPattern,
        variation_num: int,
        use_search: bool,
    ) -> EvalTestCase:
        """Generate test case with progress logging."""
        test_case = await self.generate_test_case(aclient, pattern, variation_num, use_search)
        var_label = f" v{variation_num}" if pattern.variations > 1 else ""
        print(f"Generated: {test_case.id} ({pattern.name}{var_label})")
        return test_case

    def save_test_suite(self, suite: EvalTestSuite, filename: str = "test_suite.json") -> Path:
        """Save test suite to file."""
        TEST_CASES_DIR.mkdir(parents=True, exist_ok=True)
        output_path = TEST_CASES_DIR / filename

        with open(output_path, "w") as f:
            f.write(suite.model_dump_json(indent=2))

        return output_path


# ============================================================================
# CLI Entry Point
# ============================================================================


async def main() -> None:
    """Generate test suite and save to file."""
    # Show planned distribution
    dist = get_pattern_distribution()
    print("=" * 60)
    print("PLC Error Classifier - Test Suite Generator")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Patterns: {len(ERROR_PATTERNS)}")
    print(f"Target test cases: {dist['total_cases']}")
    print(f"Max concurrent requests: {MAX_CONCURRENT_REQUESTS}")
    print()

    print("Planned distribution:")
    print("  By Stage:")
    for stage, count in sorted(dist["by_stage"].items()):
        pct = count / dist["total_cases"] * 100
        print(f"    {stage}: {count} ({pct:.0f}%)")

    print("  By Severity:")
    for sev, count in sorted(dist["by_severity"].items()):
        pct = count / dist["total_cases"] * 100
        print(f"    {sev}: {count} ({pct:.0f}%)")

    print("  By Complexity:")
    for comp, count in sorted(dist["by_complexity"].items()):
        pct = count / dist["total_cases"] * 100
        print(f"    {comp}: {count} ({pct:.0f}%)")

    print()
    print("-" * 60)

    generator = SyntheticTestGenerator()
    # Disable search, rely on few-shot examples and thinking
    suite = await generator.generate_test_suite(use_search_for_complex=False)

    output_path = generator.save_test_suite(suite)
    print()
    print("=" * 60)
    print(f"Saved test suite to: {output_path}")
    print(f"Total test cases generated: {len(suite.test_cases)}")

    # Print actual summary by stage
    by_stage: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_complexity: dict[str, int] = {}
    for tc in suite.test_cases:
        stage = tc.expected_classification.stage
        sev = tc.expected_classification.severity
        comp = tc.expected_classification.complexity
        by_stage[stage] = by_stage.get(stage, 0) + 1
        by_severity[sev] = by_severity.get(sev, 0) + 1
        by_complexity[comp] = by_complexity.get(comp, 0) + 1

    print("\nActual distribution:")
    print("  By Stage:")
    for stage, count in sorted(by_stage.items()):
        print(f"    {stage}: {count}")
    print("  By Severity:")
    for sev, count in sorted(by_severity.items()):
        print(f"    {sev}: {count}")
    print("  By Complexity:")
    for comp, count in sorted(by_complexity.items()):
        print(f"    {comp}: {count}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
