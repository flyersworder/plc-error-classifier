"""LLM-based PLC error classifier using Google Gemini.

This module implements the core classification logic following:
- CLASSIFIER_PROMPT.md: Prompt template and few-shot examples
- GEMINI_PROMPTING.md: Best practices for Gemini 2.5
- IEC_61131_KNOWLEDGE.md: Domain knowledge
"""

from google import genai
from google.genai import types

from .config import (
    CLASSIFIER_MODEL,
    GEMINI_API_KEY,
    KNOWLEDGE_BASE_PATH,
    TEMPERATURE,
    THINKING_BUDGET,
)
from .models import ClassifierOutput, ClassifyRequest, ClassifyResponse

# =============================================================================
# System Prompt
# =============================================================================

# Following GEMINI_PROMPTING.md: Be direct, use consistent structure
SYSTEM_PROMPT_TEMPLATE = """You are an IEC 61131-3 PLC expert specializing in Beremiz toolchain errors.
Your task is to classify build errors and suggest fixes.

## Classification Rules

### Severity (Impact on Build)
- **blocking**: Build cannot complete; no binary produced
  - Indicators: `error:`, `Error:`, tracebacks, `ld returned 1`
- **warning**: Build may complete but with potential issues
  - Indicators: `Warning:` without subsequent error
- **info**: Informational only; build unaffected
  - Indicators: Deprecation notices, timing info only

Decision: If ANY error message exists (not just warnings), use `blocking`.

### Stage (Where Error Occurred)
Detect by matching patterns in priority order:
1. **c_compilation**: `gcc`, `ld returned`, `undefined reference`, `.c:`, `.o:`
2. **iec_compilation**: `iec2c`, `plc.st:`, line:col format errors
3. **code_generation**: Python traceback, `AttributeError`, `PLCGenerator.py`
4. **xml_validation**: `XSD schema`, `xs:dateTime`, `Missing child element`

Decision: Match FIRST stage whose patterns appear in the PRIMARY error.

### Complexity (User Effort to Fix)
- **trivial**: Single-line fix; obvious from error message
- **moderate**: Requires understanding context, types, or multiple edits
- **complex**: Architectural issue; multiple POUs affected

Decision: Default to `moderate` if uncertain.

## Procedure

1. Scan for `error:` or `Error:` messages (not just warnings)
2. If multiple errors, focus on the FIRST one
3. Match stage detection patterns
4. Determine severity based on error presence
5. Assess complexity based on fix scope
6. Generate root cause and fix suggestion

## Domain Knowledge

{domain_knowledge}

## Examples

<example>
<input>
[17:05:56]: Cannot build project.
Warning: /tmp/build/plc.st:30-4..30-12: error: Assignment to CONSTANT variables is not allowed.
Warning: In section: PROGRAM program0
Error: IEC to C compiler returned 1
</input>
<output>
{{"classification":{{"severity":"blocking","stage":"iec_compilation","complexity":"trivial"}},"suggestion":{{"root_cause":"Variable declared with constant=true but code assigns to it","fix_description":"Remove constant attribute or remove assignment","confidence":0.95}}}}
</output>
</example>

<example>
<input>
[18:16:54]: Cannot build project.
Generating SoftPLC IEC-61131 ST/IL/SFC code...
stderr: Traceback (most recent call last):
  File "/root/beremiz/PLCGenerator.py", line 959, in ComputeProgram
AttributeError: 'NoneType' object has no attribute 'upper'
</input>
<output>
{{"classification":{{"severity":"blocking","stage":"code_generation","complexity":"moderate"}},"suggestion":{{"root_cause":"POU body is empty/None","fix_description":"Add ST code to POU body","confidence":0.90}}}}
</output>
</example>

<example>
<input>
[14:22:08]: Building project...
Warning: PLC XML file doesn't follow XSD schema at line 8:
Element 'fileHeader': '2024-03-15 10:30:00' is not a valid value of xs:dateTime.
Compiling IEC Program into C code...
Compiling C Program to target ...
</input>
<output>
{{"classification":{{"severity":"warning","stage":"xml_validation","complexity":"trivial"}},"suggestion":{{"root_cause":"DateTime uses space instead of T separator","fix_description":"Change to 2024-03-15T10:30:00","confidence":0.95}}}}
</output>
</example>

<example>
<input>
[09:45:13]: Cannot build project.
stderr: /tmp/build/plc.o: In function `DATALOGGER_body__':
plc.c:(.text+0x1a4): undefined reference to `__LOG_RECORD'
collect2: error: ld returned 1 exit status
Error: C compilation of target failed.
</input>
<output>
{{"classification":{{"severity":"blocking","stage":"c_compilation","complexity":"complex"}},"suggestion":{{"root_cause":"LOG function not available in runtime","fix_description":"Remove LOG calls or configure runtime with logging support","confidence":0.80}}}}
</output>
</example>
"""

# =============================================================================
# Knowledge Base Loading
# =============================================================================


def load_knowledge_base() -> str:
    """Load domain knowledge from markdown file."""
    if KNOWLEDGE_BASE_PATH.exists():
        return KNOWLEDGE_BASE_PATH.read_text()
    return ""


def build_system_prompt() -> str:
    """Build the full system prompt with domain knowledge."""
    knowledge = load_knowledge_base()
    return SYSTEM_PROMPT_TEMPLATE.format(domain_knowledge=knowledge)


# =============================================================================
# User Prompt Building
# =============================================================================


def build_user_prompt(error_log: str, source_xml: str | None = None) -> str:
    """Build user prompt following GEMINI_PROMPTING.md: context FIRST, question LAST."""
    parts = [f"<error_log>\n{error_log}\n</error_log>"]

    if source_xml:
        # Truncate very long XML to avoid token bloat
        xml_content = source_xml[:8000] if len(source_xml) > 8000 else source_xml
        parts.append(f"\n<source_xml>\n{xml_content}\n</source_xml>")

    parts.append("\nClassify this error.")

    return "\n".join(parts)


# =============================================================================
# Classifier
# =============================================================================


async def classify(request: ClassifyRequest) -> ClassifyResponse:
    """Classify a PLC build error and suggest fixes.

    Args:
        request: ClassifyRequest with error_log and optional source_xml.

    Returns:
        ClassifyResponse with classification and suggestion.

    Raises:
        ValueError: If GEMINI_API_KEY is not set.
        google.genai.errors.APIError: On API failures.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable not set")

    # Build prompts
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(request.error_log, request.source_xml)

    # Configure Gemini following GEMINI_PROMPTING.md best practices
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=TEMPERATURE,  # 0.0 for deterministic classification
        response_mime_type="application/json",
        response_json_schema=ClassifierOutput.model_json_schema(),
        thinking_config=types.ThinkingConfig(
            thinking_budget=THINKING_BUDGET  # 1024 for balanced quality/latency
        ),
    )

    # Create client and make async request
    client = genai.Client(api_key=GEMINI_API_KEY)

    async with client.aio as aclient:
        response = await aclient.models.generate_content(
            model=CLASSIFIER_MODEL,
            contents=user_prompt,
            config=config,
        )

    # Parse and validate response
    if response.text is None:
        raise ValueError("Empty response from Gemini API")
    result = ClassifierOutput.model_validate_json(response.text)

    return ClassifyResponse(
        classification=result.classification,
        suggestion=result.suggestion,
    )


# =============================================================================
# Synchronous wrapper (for simple use cases)
# =============================================================================


def classify_sync(request: ClassifyRequest) -> ClassifyResponse:
    """Synchronous wrapper for classify().

    For use in non-async contexts. Prefer classify() for better performance.
    """
    import asyncio

    return asyncio.run(classify(request))
