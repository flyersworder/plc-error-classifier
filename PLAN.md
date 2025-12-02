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

## Architecture Decision: Lightweight Parser + LLM

### Why Not a Full Parser?

| Consideration | Decision |
|---------------|----------|
| LLMs understand unstructured text well | Skip heavy parsing |
| Error logs are short (<100 lines typically) | Token cost is minimal |
| Only 2 base error types to handle | Don't over-engineer |
| 4-5 hour time budget | Keep it simple |

### Why Keep a Lightweight Parser?

1. **Satisfies task requirement** - spec explicitly asks for "Error Log Parser"
2. **Deterministic extraction** - line numbers, stage detection via regex
3. **Noise reduction** - strip timestamps, temp paths before LLM
4. **Testability** - can unit test parser independently
5. **Structure for API response** - clean data model

### Hybrid Approach

```
Raw Error Log
     │
     ▼
┌─────────────────┐
│ Light Parser    │  ← Regex-based, extracts obvious fields
│ - stage detect  │
│ - line numbers  │
│ - clean text    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ LLM Classifier  │  ← Does heavy lifting: classification + suggestions
│ - severity      │     (optionally with web search for deep analysis)
│ - complexity    │
│ - root cause    │
│ - fix snippets  │
└─────────────────┘
```

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
    deep_analysis: bool = False             # Optional: enable web search for difficult cases

class ParsedError(BaseModel):
    """Output from lightweight parser."""
    raw_text: str
    cleaned_text: str
    detected_stage: str | None              # regex guess: xml_validation, code_generation, etc.
    line_numbers: list[int]                 # extracted line refs
    has_source_xml: bool                    # whether XML context was provided

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
    used_web_search: bool = False           # Whether deep analysis was triggered
```

### 2. Lightweight Parser (`parser.py`)

Regex-based extraction, no complex grammar:

```python
def parse_error_log(raw_log: str, source_xml: str | None = None) -> ParsedError:
    """
    1. Detect stage from keywords:
       - "XSD schema" / "XML" → xml_validation
       - "Generating SoftPLC" / "PLCGenerator" → code_generation
       - "iec2c" / "IEC to C" → iec_compilation
       - "gcc" / "undefined reference" → c_compilation

    2. Extract line numbers via regex: r'line\s*(\d+)|:(\d+)-|^(\d{4}):'

    3. Clean text:
       - Remove temp paths (/tmp/.tmp*/build/)
       - Normalize whitespace
       - Optionally truncate very long logs
    """
```

### 3. LLM Classifier (`classifier.py`)

**Primary approach**: Embed IEC 61131-3 knowledge in system prompt.

**Fallback**: Web search for edge cases when `deep_analysis=True`.

**Rationale**:
- IEC 61131-3 is niche; LLM training data is limited
- Beremiz documentation is incomplete and scattered
- Few-shot examples + domain context in prompt handles common cases
- Web search provides fallback for unknown error patterns

**Two-Tier Response Strategy**:

```python
async def classify(request: ClassifyRequest) -> ClassifyResponse:
    # Fast path: embedded knowledge only
    result = await classify_with_embedded_knowledge(request)

    # If deep_analysis enabled and confidence is low, try web search
    if request.deep_analysis and result.suggestions[0].confidence < 0.7:
        result = await classify_with_web_search(request, result)
        result.used_web_search = True

    return result
```

**System Prompt Structure**:

```
1. Role: IEC 61131-3 / Beremiz expert
2. Quick reference: ST syntax, PLCopen XML structure
3. Common error patterns with typical fixes
4. Build pipeline stage descriptions
5. Output format specification (JSON)
```

**LLM Choice**: Anthropic Claude (configurable via env var)

### 4. HTTP API (`api.py`)

FastAPI with single endpoint:

```
POST /classify
Content-Type: application/json

Request:
{
    "error_log": "string (required) - the build output/error log",
    "source_xml": "string (optional) - PLCopen XML source for richer suggestions",
    "deep_analysis": false (optional) - enable web search for difficult cases
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
    ],
    "used_web_search": false
}
```

**Performance targets**:
- Default (no deep_analysis): < 3 seconds
- With deep_analysis: < 6 seconds (includes potential web search)

### 5. Evaluation Framework (`evaluation/`)

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
    suggestion_quality: float     # manual score 0-1 (optional)
    avg_response_time: float      # seconds
    web_search_rate: float        # % of requests that used web search
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
│   ├── parser.py          # Lightweight regex parser
│   ├── classifier.py      # LLM integration + prompts
│   ├── web_search.py      # Web search fallback (for deep_analysis)
│   ├── api.py             # FastAPI app
│   └── config.py          # Settings, env vars
├── evaluation/
│   ├── __init__.py
│   ├── generator.py       # Synthetic error generator
│   ├── metrics.py         # Accuracy calculations
│   ├── run_eval.py        # Evaluation runner
│   └── test_cases/        # Generated test data
├── tests/
│   ├── test_parser.py
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
2. **Parser** - Regex extraction, easy to test
3. **Classifier** - LLM prompt engineering, core logic
4. **API** - Wrap classifier in FastAPI
5. **Tests** - Unit tests for parser + integration tests
6. **Web Search** - Optional fallback for deep_analysis
7. **Evaluation** - Synthetic generator + metrics
8. **Documentation** - README, evaluation report

---

## Open Questions / Risks

1. **LLM latency**: May need caching for repeated similar errors
2. **XML context**: How much source XML to include without exceeding token limits?
3. **Evaluation ground truth**: Manual labeling required for suggestion quality
4. **Edge cases**: What if error log contains multiple unrelated errors?
5. **Web search reliability**: Search results may be irrelevant or outdated

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
{cleaned_error_log}

Source XML (if available):
{source_xml_snippet}
```
