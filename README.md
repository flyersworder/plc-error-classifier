# PLC Error Classifier

AI-powered system that classifies PLC compilation errors and suggests fixes for the Beremiz toolchain.

## Features

- **Error Classification**: Categorizes build errors by severity, stage, and complexity
- **Fix Suggestions**: Provides actionable fix suggestions with root cause analysis
- **Code Snippets**: When source XML is provided, includes before/after code examples
- **Fast Response**: Average response time <3 seconds
- **REST API**: Simple FastAPI-based HTTP interface

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Google Gemini API key

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd plc-error-classifier

# Install dependencies
uv sync

# Set up environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### Run the Server

```bash
uv run uvicorn plc_error_classifier:app --host 127.0.0.1 --port 8000
```

### Example Request

```bash
curl -X POST http://localhost:8000/classify \
  -H "Content-Type: application/json" \
  -d '{
    "error_log": "[17:05:56]: Cannot build project.\nWarning: /tmp/build/plc.st:30-4..30-12: error: Assignment to CONSTANT variables is not allowed.\nError: IEC to C compiler returned 1"
  }'
```

### Example Response

```json
{
  "classification": {
    "severity": "blocking",
    "stage": "iec_compilation",
    "complexity": "trivial"
  },
  "suggestions": [
    {
      "root_cause": "Variable declared with constant=true but code assigns to it",
      "fix_description": "Remove constant attribute from variable declaration or remove the assignment",
      "code_before": "<localVars constant=\"true\">",
      "code_after": "<localVars>",
      "confidence": 0.95
    }
  ]
}
```

## API Reference

### POST /classify

Classify a PLC build error and get fix suggestions.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `error_log` | string | Yes | Build output/error log from Beremiz |
| `source_xml` | string | No | PLCopen XML source for richer suggestions |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `classification.severity` | enum | `blocking`, `warning`, or `info` |
| `classification.stage` | enum | `xml_validation`, `code_generation`, `iec_compilation`, or `c_compilation` |
| `classification.complexity` | enum | `trivial`, `moderate`, or `complex` |
| `suggestions` | array | 1-3 fix suggestions ranked by confidence |

### GET /health

Health check endpoint. Returns `{"status": "healthy"}`.

## Classification Categories

### Severity

| Value | Description |
|-------|-------------|
| `blocking` | Build fails, no binary produced |
| `warning` | Build succeeds with validation issues |
| `info` | Informational only, build unaffected |

### Stage

| Value | Description |
|-------|-------------|
| `xml_validation` | PLCopen XML schema validation errors |
| `code_generation` | Beremiz Python generator errors |
| `iec_compilation` | matiec/iec2c compiler errors |
| `c_compilation` | gcc/linker errors |

### Complexity

| Value | Description |
|-------|-------------|
| `trivial` | Error clearly states problem, fix is obvious |
| `moderate` | Requires investigation or tracing to source |
| `complex` | Cryptic error, requires significant investigation |

## Project Structure

```
plc-error-classifier/
├── src/plc_error_classifier/
│   ├── __init__.py       # Package exports
│   ├── api.py            # FastAPI endpoints
│   ├── classifier.py     # LLM classification logic
│   ├── config.py         # Configuration settings
│   └── models.py         # Pydantic models
├── evaluation/
│   ├── generator.py      # Synthetic test case generator
│   ├── run_eval.py       # Evaluation runner
│   ├── judge.py          # LLM-as-judge for suggestions
│   ├── metrics.py        # Classification metrics
│   ├── patterns.py       # Error pattern definitions
│   └── models.py         # Evaluation data models
├── docs/
│   ├── GEMINI_PROMPTING.md    # Prompting best practices
│   └── IEC_61131_KNOWLEDGE.md # Domain knowledge base
├── sample_data/          # Example error logs and XML
└── tests/                # Unit and integration tests
```

## Configuration

Environment variables (set in `.env`):

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key (required) |

Model configuration (in `config.py`):

| Setting | Default | Description |
|---------|---------|-------------|
| `CLASSIFIER_MODEL` | `gemini-2.5-flash` | Gemini model for classification |
| `TEMPERATURE` | `0.0` | Deterministic output |
| `THINKING_BUDGET` | `0` | Disabled for lowest latency |

## Development

### Setup

```bash
# Install dev dependencies
uv sync --dev

# Install pre-commit hooks
uv run pre-commit install
```

### Testing

```bash
# Run tests with coverage
uv run pytest

# Run specific test file
uv run pytest tests/test_classifier.py -v
```

## Evaluation

The evaluation framework generates synthetic test cases and measures classifier accuracy. For detailed documentation, see:

- [`evaluation/README.md`](evaluation/README.md) - Full evaluation framework guide
- [`evaluation/ERROR_PATTERNS.md`](evaluation/ERROR_PATTERNS.md) - Error pattern research and classification rules

### Quick Start

```bash
# Generate synthetic test suite (100 cases)
uv run python -m evaluation.generator

# Run evaluation
uv run python -m evaluation.run_eval

# Get detailed metrics with confidence intervals
uv run python -m evaluation.metrics evaluation/reports/<report>.json
```

### Current Results (thinking_budget=0)

Evaluated on 100 synthetic test cases with 95% bootstrap confidence intervals:

**Classification Accuracy:**

| Metric | Accuracy | 95% CI |
|--------|----------|--------|
| Severity | 92.0% | [86.0%, 97.0%] |
| Stage | 94.0% | [89.0%, 98.0%] |
| Complexity | 69.0% | [60.0%, 78.0%] |
| Overall (all correct) | 61.0% | [51.0%, 71.0%] |

**Suggestion Quality** (LLM-as-Judge):

| Metric | Score | 95% CI |
|--------|-------|--------|
| Root Cause Accuracy | 0.945 | [0.917, 0.969] |
| Fix Quality | 0.925 | [0.896, 0.950] |
| Overall Score | 0.933 | [0.905, 0.957] |

*Note: Suggestion quality is evaluated using Gemini Flash as a judge (same model as classifier). This may introduce optimistic bias - the model may rate its own outputs more favorably. For production validation, consider using a different judge model or human evaluation.*

**Classification Time** (Gemini API call only):

| Metric | Value | 95% CI |
|--------|-------|--------|
| Average | 2763ms | [2605ms, 2940ms] |
| P95 | 4079ms | [3815ms, 4299ms] |

*Note: These times measure the classifier function only (Gemini API call). Full API response time adds HTTP overhead. Live API testing (n=10) shows 2.5-3.5s range with 2.7s average. Times vary based on Gemini API load.*

### Thinking Budget Tradeoff

The `THINKING_BUDGET` parameter controls Gemini's reasoning effort:

| Budget | Complexity Accuracy | Avg Response Time | Use Case |
|--------|---------------------|-------------------|----------|
| `0` | 69% | ~2.4s | **Production** - meets <3s target |
| `128` | 71% | ~3.2s | Slightly better accuracy, exceeds target |
| `1024+` | ~72-75% | ~4-5s | Best accuracy, too slow |

**Decision:** We use `thinking_budget=0` because:
1. Response time is a hard constraint (<3s target)
2. Complexity is inherently subjective (+2% accuracy isn't worth +800ms)
3. Severity and stage accuracy are already excellent (92%+)

**Complexity Confusion Matrix:**

```
                 Predicted
Expected     complex  moderate  trivial
─────────────────────────────────────────
complex         12        6        1      (63% correct)
moderate         4       26        9      (67% correct)
trivial          3        8       31      (74% correct)
```

Most errors are adjacent (trivial↔moderate, moderate↔complex), not severe misclassifications.

### Complexity Accuracy Limitations

The ~69% complexity accuracy reflects inherent limitations:

1. **Subjectivity**: What's "trivial" for an expert may be "moderate" for a junior
2. **Synthetic data**: Generated test cases may not perfectly match intended complexity
3. **Adjacent errors**: Most misclassifications are trivial↔moderate or moderate↔complex (not severe)

For production use, treat complexity as a rough guide rather than ground truth.

## Architecture Decisions

### 1. LLM-Only Classification (No Parser)

We chose a pure LLM-based approach without a traditional error parser. Rationale:

- **Flexibility**: LLMs handle novel error formats without rule updates
- **Context Understanding**: Can correlate multiple error lines and understand cascading failures
- **Suggestion Generation**: Natural language suggestions are a core feature that parsers can't provide
- **Diminishing Returns**: A parser would add complexity but provide minimal accuracy gains—the LLM already achieves 92%+ severity/stage accuracy

A hybrid approach (parser + LLM) was considered but rejected as over-engineering for this use case.

### 2. Gemini Model Selection

Chose Google Gemini 2.5 models for the following reasons:

- **Model Variety**: Flash-Lite for cost-effective evaluation suite generation, Flash for production classification
- **Price-Performance**: Flash offers excellent accuracy at $0.30/1M input tokens
- **Large Context Window**: 1M tokens allows embedding the full knowledge base without truncation
- **Structured Output**: Native JSON schema enforcement eliminates parsing errors

*Trade-off*: Large context may introduce "context rot" (degraded attention to middle content), but our knowledge base is small enough (~10KB) that this isn't a concern.

### 3. Evaluation-First Development

We invested significant effort in building a comprehensive evaluation framework before optimizing the classifier:

- **Synthetic Test Generation**: 100 test cases covering all error patterns
- **Statistical Rigor**: Bootstrap confidence intervals for all metrics
- **LLM-as-Judge**: Automated suggestion quality assessment
- **Reproducibility**: Saved reports enable before/after comparisons

Without reliable evaluation, we couldn't measure the impact of prompt changes or model upgrades.

### 4. Embedded Domain Knowledge (No Google Search)

Domain knowledge is embedded directly in the system prompt rather than using Google Search grounding:

- **Specialized Content**: IEC 61131-3 and Beremiz errors are niche—web search results are scattered and often irrelevant
- **Latency**: Search adds 500-1000ms per request, breaking our <3s target
- **Reliability**: Embedded knowledge provides consistent, curated context
- **Control**: We can update the knowledge base without depending on web content changes

### 5. Thinking Budget = 0

Disabled Gemini's reasoning mode for production:

- **Latency Priority**: Saves ~500-800ms per request to meet <3s target
- **Marginal Accuracy Gain**: Only +2-3% complexity accuracy with thinking enabled
- **Acceptable Trade-off**: Severity/stage accuracy already excellent (92%+) without reasoning

See [Thinking Budget Tradeoff](#thinking-budget-tradeoff) for detailed benchmarks.

### Additional Design Choices

- **Structured Output**: Uses Gemini's JSON schema enforcement for reliable parsing
- **Few-Shot Examples**: Classifier prompt includes examples for each error stage to improve accuracy
