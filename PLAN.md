# PLC Error Classifier - Implementation Plan

## Overview

Build an AI system that classifies PLC compilation errors and suggests fixes for OTee's customers.

**Input**: Raw error logs from Beremiz PLC build pipeline (required), optionally source XML
**Output**: Classification (severity, stage, complexity) + actionable fix suggestions

---

## Context: Beremiz PLC Development

### What is Beremiz?

Beremiz is an open-source IDE for developing SoftPLC applications. Engineers use visual editors
(Function Block Diagram, Ladder Diagram) or text editors (Structured Text) to create PLC logic.
The IDE saves projects in PLCopen XML format.

### Build Pipeline

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  PLCopen XML    │────▶│  IEC 61131-3    │────▶│    C Code       │────▶│  SoftPLC Binary │
│  (project file) │     │  ST Code        │     │  (intermediate) │     │  (.so library)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
     [input]              [code_generation]       [iec_compilation]       [c_compilation]
                              via Beremiz            via matiec/iec2c         via gcc
```

Errors can occur at any stage, and one early error can cascade into multiple downstream errors.

### Sample Data Structure

| File | Type | Description |
|------|------|-------------|
| `*.xml` | **Input** | PLCopen XML project file (source code) |
| `*.txt` | **Output** | Build error log from Beremiz CLI |

The error log contains embedded code snippets from the source, so classification is possible
even without the source XML. The XML provides additional context for better fix suggestions.

### Documentation Landscape

There is no single source of truth for Beremiz/IEC 61131-3:
- Beremiz docs are incomplete
- IEC 61131-3 spec is paid ($300+)
- Engineers rely on vendor docs (Beckhoff, Siemens) and forums

This fragmentation is why an AI assistant is valuable - we embed the scattered knowledge
into the system prompt.

---

## Architecture Decision: Direct LLM Classification (No Parser)

### Why No Separate Parser?

The task specification mentions an "Error Log Parser", but after careful analysis, we decided
**not** to implement a separate parsing layer. Here's our reasoning:

| Consideration | Analysis |
|---------------|----------|
| **LLM capability** | Modern LLMs (Gemini 2.5 Flash) excel at understanding unstructured text, extracting line numbers, detecting stages, and identifying cascading errors |
| **Context window** | Gemini has 1M token context; error logs are ~2K tokens max - no truncation needed |
| **Added complexity** | A parser adds code to maintain with minimal benefit |
| **Information loss** | Preprocessing might remove useful context the LLM could leverage |
| **Cascading errors** | LLM can identify root cause vs. downstream effects via prompting |

### What About the Task Requirement?

The spec asks to "Extract: error type, stage, line numbers, context". Our LLM-based approach
**still fulfills this requirement** - the extraction happens inside the LLM rather than in
a separate regex-based module. The output contains all requested fields.

### When Would a Parser Be Justified?

We evaluated potential use cases:

| Use Case | Applies to Us? |
|----------|----------------|
| Token optimization (truncate long logs) | No - logs are short (~2K tokens vs 1M context) |
| Stage-based model routing | No - single model handles all stages |
| Caching/deduplication | Possibly, but can hash raw input directly |
| Pre-validation | Minor benefit - LLM handles malformed input gracefully |

**Conclusion**: No compelling case for a separate parser in this context.

### Simplified Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        API Request                          │
│       { error_log: "...", source_xml: "..." (optional) }    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      LLM Classifier                         │
│                                                             │
│  • Understands raw error logs directly                      │
│  • Extracts: stage, line numbers, error type, context       │
│  • Identifies cascading errors and root cause               │
│  • Classifies: severity, stage, complexity                  │
│  • Generates fix suggestions with code snippets             │
│  • Uses structured output (JSON schema) for consistency     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       API Response                          │
│       { classification: {...}, suggestions: [...] }         │
└─────────────────────────────────────────────────────────────┘
```

This design prioritizes simplicity and leverages LLM strengths rather than adding
unnecessary preprocessing layers.

### Why No Web Search?

We considered adding Google Search grounding for "deep analysis" but decided against it:

| Concern | Analysis |
|---------|----------|
| **Complexity** | Adds code path, error handling, timeout logic |
| **Unpredictability** | Search results vary, may return irrelevant content |
| **Structured output conflict** | Can't use `response_mime_type` with `google_search` on Gemini 2.5 |
| **Latency** | Adds 2-3s per request |
| **Actual value** | IEC 61131-3 errors are predictable; embedded domain knowledge is sufficient |

**Conclusion**: Structured output consistency is more valuable than web search capability.

---

## Component Design

### 1. Data Models (`models.py`)

```python
from pydantic import BaseModel, Field
from typing import Literal

class ClassifyRequest(BaseModel):
    """API request model."""
    error_log: str                          # Required: build output/error log
    source_xml: str | None = None           # Optional: PLCopen XML for richer suggestions

class ErrorClassification(BaseModel):
    """Classification result."""
    severity: Literal["blocking", "warning", "info"]
    stage: Literal["xml_validation", "code_generation", "iec_compilation", "c_compilation"]
    complexity: Literal["trivial", "moderate", "complex"]

class FixSuggestion(BaseModel):
    """A single fix suggestion."""
    description: str
    root_cause: str
    code_before: str | None = None          # Only if source_xml provided
    code_after: str | None = None           # Only if source_xml provided
    confidence: float = Field(ge=0.0, le=1.0)

class ClassifyResponse(BaseModel):
    """API response model."""
    classification: ErrorClassification
    suggestions: list[FixSuggestion]        # 1-3 suggestions
```

### 2. LLM Classifier (`classifier.py`)

**Approach**: Embed comprehensive IEC 61131-3 knowledge in system prompt + use structured output.

**Rationale**:
- IEC 61131-3 is niche; LLM training data may be limited
- Beremiz documentation is incomplete and scattered
- Few-shot examples + domain context in prompt handles common cases
- Structured output (JSON schema) ensures consistent, parseable responses

```python
async def classify(request: ClassifyRequest) -> ClassifyResponse:
    response = await client.models.generate_content(
        model="gemini-2.5-flash",
        contents=build_prompt(request.error_log, request.source_xml),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=ClassifyResponse,
        ),
    )
    return ClassifyResponse.model_validate_json(response.text)
```

**Required Domain Knowledge** (embedded in system prompt):

```
1. Build Pipeline Stages
   - xml_validation: PLCopen XML schema errors
   - code_generation: Beremiz PLCGenerator Python errors
   - iec_compilation: matiec/iec2c compiler errors
   - c_compilation: gcc/linker errors

2. IEC 61131-3 Fundamentals
   - Data types: BOOL, INT, DINT, REAL, STRING, TIME, DATE, etc.
   - POU types: PROGRAM, FUNCTION, FUNCTION_BLOCK
   - Variable sections: VAR, VAR_INPUT, VAR_OUTPUT, VAR_IN_OUT, VAR_EXTERNAL
   - Languages: ST (Structured Text), FBD, LD, SFC

3. Common Error Patterns
   - Type mismatches, undeclared variables
   - Constant assignment violations
   - Missing body/interface, invalid XML structure
   - Control flow errors (IF/FOR/WHILE with non-BOOL)

4. PLCopen XML Structure
   - Hierarchy: project → types → pous → pou → interface/body
   - ST code embedding: <ST><xhtml>...</xhtml></ST>
```

**LLM Choice**: Google Gemini 2.5 Flash (see [Model Selection](#model-selection) below)

### 3. HTTP API (`api.py`)

FastAPI with single endpoint:

```
POST /classify
Content-Type: application/json

Request:
{
    "error_log": "string (required) - the build output/error log",
    "source_xml": "string (optional) - PLCopen XML source for richer suggestions"
}

Response:
{
    "classification": {
        "severity": "blocking",
        "stage": "iec_compilation",
        "complexity": "trivial"
    },
    "suggestions": [
        {
            "description": "Remove constant modifier from variable",
            "root_cause": "LocalVar1 is declared as CONSTANT but assigned a value",
            "code_before": "<localVars constant=\"true\">",
            "code_after": "<localVars constant=\"false\">",
            "confidence": 0.95
        }
    ]
}
```

**Performance target**: < 3 seconds per request

### 4. Evaluation Framework (`evaluation/`)

#### Synthetic Error Generator

Generate variations of the 2 base errors:

| Base Error | Variations |
|------------|------------|
| constant_error | Different variable names, types (INT, REAL, STRING), multiple assignments |
| empty_project | Empty body, None body, whitespace-only body, missing interface |

Additional synthetic errors (extrapolated):
- Undeclared variable reference
- Type mismatch in assignment
- Invalid XML structure
- Missing POU definition

**Target**: 20-30 test cases with ground truth labels

#### Metrics

```python
class EvaluationMetrics(BaseModel):
    severity_accuracy: float      # % correct severity
    stage_accuracy: float         # % correct stage
    complexity_accuracy: float    # % correct complexity
    overall_accuracy: float       # all three correct
    suggestion_quality: float     # LLM-as-judge score 0-1
    avg_response_time: float      # seconds
```

#### Evaluation Report

Output markdown/JSON report showing:
- Accuracy breakdown by error type
- Confusion matrices for each classification dimension
- Example failures for analysis

---

## Project Structure

```
plc-error-classifier/
├── src/plc_error_classifier/
│   ├── __init__.py
│   ├── models.py          # Pydantic models
│   ├── classifier.py      # LLM integration + prompts
│   ├── api.py             # FastAPI app
│   └── config.py          # Settings, env vars
├── evaluation/
│   ├── __init__.py
│   ├── generator.py       # Synthetic error generator
│   ├── metrics.py         # Accuracy calculations
│   ├── run_eval.py        # Evaluation runner
│   └── test_cases/        # Generated test data
├── tests/
│   ├── test_classifier.py
│   └── test_api.py
├── sample_data/           # Original sample files
│   ├── constant_error.txt
│   ├── constant_error.xml
│   ├── empty_project.txt
│   └── empty_project.xml
├── pyproject.toml
├── uv.lock
├── README.md
├── PLAN.md               # This file
└── .env.example          # API keys template
```

---

## Implementation Order

1. **Models** - Define Pydantic data structures first
2. **Classifier** - LLM prompt engineering, core logic
3. **API** - Wrap classifier in FastAPI
4. **Tests** - Integration tests for classifier and API
5. **Evaluation** - Synthetic generator + metrics
6. **Documentation** - README, evaluation report

---

## Open Questions / Risks

1. **LLM latency**: May need caching for repeated similar errors
2. **Evaluation ground truth**: LLM-as-judge for suggestion quality (potential bias)
3. **Edge cases**: What if error log contains multiple unrelated errors?
4. **Domain coverage**: System prompt may not cover all obscure IEC 61131-3 edge cases

---

## Model Selection

### Why Google Gemini?

| Factor | Benefit |
|--------|---------|
| **Model range** | Flash-Lite for generation, Flash for classification |
| **Context window** | 1M tokens - handles large XML files easily |
| **Cost** | Flash: $0.30/1M input, $2.50/1M output |
| **Structured output** | Native JSON schema support for consistent responses |
| **Thinking mode** | Built-in reasoning capabilities |

### Validation Results (Dec 2025)

Tested both sample errors with `gemini-2.5-flash` and `gemini-2.5-flash-lite`:

| Model | Error | Severity | Stage | Complexity | Score |
|-------|-------|----------|-------|------------|-------|
| **gemini-2.5-flash** | constant_error | ✓ blocking | ✓ iec_compilation | ✓ trivial | 3/3 |
| **gemini-2.5-flash** | empty_project | ✓ blocking | ✓ code_generation | ✓ moderate | 3/3 |
| gemini-2.5-flash-lite | constant_error | ✓ blocking | ✓ iec_compilation | ✗ moderate | 2/3 |
| gemini-2.5-flash-lite | empty_project | ✓ blocking | ✗ xml_validation | ✓ moderate | 2/3 |

**Key findings**:
- **Flash (6/6 correct)**: Perfect classification, accurate root cause analysis
- **Flash-Lite (4/6 correct)**: Confused XML warning with actual code_generation error;
  classified trivial error as moderate

### Model Allocation

| Task | Model | Rationale |
|------|-------|-----------|
| **Error classification** | `gemini-2.5-flash` | High accuracy required |
| **Synthetic data generation** | `gemini-2.5-flash` | Better quality test cases |
| **LLM-as-judge** | `gemini-2.5-flash` | Consistent evaluation |

### Cost Estimate

| Operation | Model | Est. Tokens | Cost |
|-----------|-------|-------------|------|
| Classify 1 error | Flash | ~2K in, ~500 out | ~$0.002 |
| Generate 21 test cases | Flash | ~50K in, ~30K out | ~$0.10 |
| Evaluation run (21 cases) | Flash | ~60K in, ~15K out | ~$0.06 |

### Thinking Budget Control

Gemini 2.5 Flash supports a `thinking_budget` parameter to control reasoning effort and latency:

| Budget Value | Behavior |
|--------------|----------|
| `0` | Thinking OFF - lowest latency |
| `1` - `24576` | Cap on thinking tokens |
| `-1` | Model decides automatically |

**Recommended setting for 3s latency target**: `thinking_budget=1024`

```python
from google.genai import types

config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=ClassifyResponse,
    thinking_config=types.ThinkingConfig(
        thinking_budget=1024  # Balance quality vs latency
    )
)
```

---

## Sample Prompt (Draft)

See `classifier.py` for full implementation. Core structure:

```
SYSTEM: You are an IEC 61131-3 PLC expert specializing in Beremiz toolchain errors.

[Domain knowledge: ST syntax, PLCopen XML, common errors]

Analyze the error and respond in JSON:
{
    "classification": { "severity": "...", "stage": "...", "complexity": "..." },
    "suggestions": [{ "description": "...", "root_cause": "...", ... }]
}

USER:
Error Log:
{error_log}

Source XML (if available):
{source_xml}
```
