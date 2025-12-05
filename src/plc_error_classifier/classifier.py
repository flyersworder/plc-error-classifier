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
  - FINAL indicators: `Error:` at end, Python tracebacks, `ld returned 1 exit status`
  - Examples: "Error: IEC to C compiler returned 1", "Error: C compilation of target failed."
- **warning**: Build continues but with validation issues
  - Build progresses past the warning (e.g., "Compiling C Program to target")
  - No final `Error:` line
- **info**: Informational only; build unaffected
  - Indicators: Deprecation notices, timing info only

Decision: Check the FINAL outcome of the build, not early messages. "Cannot build project" may appear early but build can still continue for warnings.

### Stage (Where Error Occurred)
Detect by matching patterns in priority order:
1. **c_compilation**: `gcc`, `ld returned`, `undefined reference`, `.c:`, `.o:`
2. **iec_compilation**: `iec2c`, `plc.st:`, line:col format errors
3. **code_generation**: Python traceback, `AttributeError`, `PLCGenerator.py`
4. **xml_validation**: `XSD schema`, `xs:dateTime`, `Missing child element`

Decision: Match FIRST stage whose patterns appear in the PRIMARY error.

### Complexity (Cognitive Load to Understand and Fix)
- **trivial**: Error message clearly states the problem AND the fix is immediately obvious.
  User reads error -> knows exactly what to do. Example: "Variable 'X' not declared" -> add declaration.
- **moderate**: Error message indicates the problem but user needs to think, check documentation,
  or understand context to determine the fix. Example: "undefined reference to 'X'" -> find missing library.
- **complex**: Error message is cryptic, misleading, or requires significant investigation/debugging
  to understand the root cause. Example: Python traceback with no clear PLC-related message.

Decision: Default to `moderate` if uncertain.

## Suggestions

Generate 1-3 actionable fix suggestions, ranked by confidence (highest first).

For each suggestion:
- **root_cause**: Explain what's actually wrong
- **fix_description**: How to fix the issue
- **code_before**: The problematic code snippet
- **code_after**: The corrected code snippet
- **confidence**: 0.0-1.0 score

**Code Snippet Guidelines**:
- ALWAYS try to provide code_before/code_after - users need actionable examples
- **With source_xml**: Extract exact code from the XML (highest confidence: 0.85-0.95)
- **Without source_xml**: Infer from error log context or show typical patterns (lower confidence: 0.6-0.8)
- Error logs often contain line numbers and code context - use them
- When inferring, use realistic variable names from the error message
- Only set to null if truly impossible to provide any useful example

## Procedure

1. Scan the ENTIRE log to find the FINAL outcome (end of log matters most)
2. If log ends with `Error:` or traceback → blocking. If build continues → warning.
3. For stage detection, focus on the FIRST error (root cause)
4. Match stage detection patterns
5. Assess complexity based on cognitive load to understand and fix
6. Generate 1-3 suggestions with root cause analysis

## Domain Knowledge

{domain_knowledge}

## Examples

<example>
<input>
<error_log>
[17:05:56]: Cannot build project.
Warning: /tmp/build/plc.st:30-4..30-12: error: Assignment to CONSTANT variables is not allowed.
Warning: In section: PROGRAM program0
Error: IEC to C compiler returned 1
</error_log>
<source_xml>
<localVars constant="true">
  <variable name="LocalVar1">
    <type><INT/></type>
  </variable>
</localVars>
</source_xml>
</input>
<output>
{{"classification":{{"severity":"blocking","stage":"iec_compilation","complexity":"trivial"}},"suggestions":[{{"root_cause":"Variable LocalVar1 declared with constant=true but code assigns to it","fix_description":"Remove constant attribute from variable declaration","code_before":"<localVars constant=\\"true\\">","code_after":"<localVars>","confidence":0.95}},{{"root_cause":"Assignment to constant variable is not allowed in IEC 61131-3","fix_description":"Remove the assignment statement from the code","code_before":"LocalVar1 := 10;","code_after":"(* remove assignment *)","confidence":0.85}}]}}
</output>
</example>

<example>
<input>
<error_log>
[18:16:54]: Cannot build project.
Generating SoftPLC IEC-61131 ST/IL/SFC code...
stderr: Traceback (most recent call last):
  File "/root/beremiz/PLCGenerator.py", line 959, in ComputeProgram
AttributeError: 'NoneType' object has no attribute 'upper'
</error_log>
</input>
<output>
{{"classification":{{"severity":"blocking","stage":"code_generation","complexity":"moderate"}},"suggestions":[{{"root_cause":"POU body is empty or None - no code to compile","fix_description":"Add ST code to the POU body section","code_before":"<body>\\n  <ST>\\n    <!-- empty -->\\n  </ST>\\n</body>","code_after":"<body>\\n  <ST>\\n    <xhtml:p>(* Your ST code here *)</xhtml:p>\\n  </ST>\\n</body>","confidence":0.75}},{{"root_cause":"POU interface may be missing required elements","fix_description":"Verify POU has both interface and body sections defined","code_before":"<pou name=\\"program0\\">\\n  <!-- missing interface/body -->\\n</pou>","code_after":"<pou name=\\"program0\\">\\n  <interface><localVars/></interface>\\n  <body><ST>...</ST></body>\\n</pou>","confidence":0.60}}]}}
</output>
</example>

<example>
<input>
<error_log>
[14:22:08]: Building project...
[14:22:08]: Cannot build project.
Warning: PLC XML file doesn't follow XSD schema at line 8:
Element 'fileHeader': '2024-03-15 10:30:00' is not a valid value of xs:dateTime.
Compiling IEC Program into C code...
Compiling C Program to target ...
</error_log>
</input>
<output>
{{"classification":{{"severity":"warning","stage":"xml_validation","complexity":"trivial"}},"suggestions":[{{"root_cause":"DateTime format uses space instead of ISO 8601 T separator","fix_description":"Change datetime to ISO 8601 format with T separator","code_before":"<fileHeader ... creationDateTime=\\"2024-03-15 10:30:00\\">","code_after":"<fileHeader ... creationDateTime=\\"2024-03-15T10:30:00\\">","confidence":0.90}}]}}
</output>
</example>

<example>
<input>
<error_log>
[09:45:13]: Cannot build project.
stderr: /tmp/build/plc.o: In function `DATALOGGER_body__':
plc.c:(.text+0x1a4): undefined reference to `__LOG_RECORD'
collect2: error: ld returned 1 exit status
Error: C compilation of target failed.
</error_log>
</input>
<output>
{{"classification":{{"severity":"blocking","stage":"c_compilation","complexity":"complex"}},"suggestions":[{{"root_cause":"LOG function references symbol __LOG_RECORD not available in the runtime","fix_description":"Remove LOG function calls from DATALOGGER POU","code_before":"LOG('Recording data: %d', value);","code_after":"(* LOG removed - not supported *)\\n(* Alternative: use output variable *)","confidence":0.70}},{{"root_cause":"Runtime library missing logging support","fix_description":"Configure runtime with logging support enabled or use alternative logging method","code_before":"(* runtime config *)","code_after":"Enable logging in Beremiz runtime configuration or use a custom FB for logging","confidence":0.55}}]}}
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
        suggestions=result.suggestions,
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
