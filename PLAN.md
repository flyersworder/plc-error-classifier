# PLC Error Classifier - Implementation Plan

## Overview

Build an AI system that classifies PLC compilation errors and suggests fixes for OTee's customers.

**Input**: Raw error logs from Beremiz PLC build pipeline
**Output**: Classification (severity, stage, complexity) + actionable fix suggestions

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
│ - severity      │
│ - complexity    │
│ - root cause    │
│ - fix snippets  │
└─────────────────┘
```

---

## Component Design

### 1. Data Models (`models.py`)

```python
@dataclass
class ParsedError:
    raw_text: str
    cleaned_text: str
    detected_stage: str | None      # regex guess: xml_validation, code_generation, etc.
    line_numbers: list[int]         # extracted line refs
    source_file: str | None         # if XML provided

@dataclass
class ErrorClassification:
    severity: Literal["blocking", "warning", "info"]
    stage: Literal["xml_validation", "code_generation", "iec_compilation", "c_compilation"]
    complexity: Literal["trivial", "moderate", "complex"]

@dataclass
class FixSuggestion:
    description: str
    root_cause: str
    code_before: str | None
    code_after: str | None
    confidence: float               # 0.0 - 1.0

@dataclass
class ClassificationResult:
    classification: ErrorClassification
    suggestions: list[FixSuggestion]  # 1-3 suggestions
    raw_llm_response: str | None      # for debugging
```

### 2. Lightweight Parser (`parser.py`)

Regex-based extraction, no complex grammar:

```python
def parse_error_log(raw_log: str, source_xml: str = None) -> ParsedError:
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

**Key Decision**: Embed IEC 61131-3 knowledge in system prompt rather than using RAG/web search.

**Rationale**:
- IEC 61131-3 is niche; LLM training data is limited
- RAG setup would exceed time budget
- Few-shot examples + domain context in prompt is sufficient
- Only 2 base error types to handle

**System Prompt Structure**:

```
1. Role: IEC 61131-3 / Beremiz expert
2. Quick reference: ST syntax, PLCopen XML structure
3. Common error patterns with typical fixes
4. Build pipeline stage descriptions
5. Output format specification (JSON)
```

**LLM Choice**: Anthropic Claude or OpenAI GPT-4 (configurable via env var)

### 4. HTTP API (`api.py`)

FastAPI with single endpoint:

```
POST /classify
Content-Type: application/json

Request:
{
    "error_log": "string (required)",
    "source_xml": "string (optional, for context)"
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

**Performance target**: < 3 seconds (mostly LLM latency)

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
@dataclass
class EvaluationMetrics:
    severity_accuracy: float      # % correct severity
    stage_accuracy: float         # % correct stage
    complexity_accuracy: float    # % correct complexity
    overall_accuracy: float       # all three correct
    suggestion_quality: float     # manual score 0-1 (optional)
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
├── src/
│   ├── __init__.py
│   ├── models.py          # Data classes
│   ├── parser.py          # Lightweight regex parser
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
│   ├── test_parser.py
│   ├── test_classifier.py
│   └── test_api.py
├── sample_data/           # Original sample files
│   ├── constant_error.txt
│   ├── constant_error.xml
│   ├── empty_project.txt
│   └── empty_project.xml
├── requirements.txt
├── README.md
├── PLAN.md               # This file
└── .env.example          # API keys template
```

---

## Implementation Order

1. **Models** - Define data structures first
2. **Parser** - Regex extraction, easy to test
3. **Classifier** - LLM prompt engineering, core logic
4. **API** - Wrap classifier in FastAPI
5. **Tests** - Unit tests for parser + integration tests
6. **Evaluation** - Synthetic generator + metrics
7. **Documentation** - README, evaluation report

---

## Dependencies

```
# Core
fastapi>=0.104.0
uvicorn>=0.24.0
pydantic>=2.5.0

# LLM
anthropic>=0.7.0        # or openai>=1.3.0

# Testing
pytest>=7.4.0
httpx>=0.25.0           # for async API tests

# Utilities
python-dotenv>=1.0.0
```

---

## Open Questions / Risks

1. **LLM latency**: May need caching for repeated similar errors
2. **XML context**: How much source XML to include without exceeding token limits?
3. **Evaluation ground truth**: Manual labeling required for suggestion quality
4. **Edge cases**: What if error log contains multiple unrelated errors?

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
