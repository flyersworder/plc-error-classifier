# Evaluation Framework

This directory contains the evaluation framework for the PLC Error Classifier. It provides tools for generating synthetic test cases, evaluating classifier performance, and generating detailed reports.

## Target User Profile: PLC Programmers

Understanding our target users is essential for accurate complexity classification. Based on industry research:

### Background & Education
| Aspect | Finding |
|--------|---------|
| Education | 53% bachelor's degree, 36% associate degree |
| Fields | Electrical Engineering, Mechatronics, Computer Science, Mechanical Engineering |
| Experience | Typically 3-5 years in manufacturing/controls |

### Technical Skills
- **Primary**: Ladder Logic, IEC 61131-3 languages (ST, FBD, LD, SFC), troubleshooting
- **Programming**: C++, Python listed as valuable skills
- **Systems**: SCADA, HMI, Allen Bradley, RSLogix platforms
- **Domain**: Control systems, automated manufacturing, hardware/software integration

### Key Insight
PLC programmers are **technically sophisticated engineers** who:
- Understand hardware/software integration
- Often know C/C++ and Python
- Are experienced troubleshooters used to investigating complex issues
- Have strong problem-solving skills

**Sources**: [Indeed](https://www.indeed.com/hire/job-description/plc-programmer), [Zippia](https://www.zippia.com/plc-programmer-jobs/education/), [SolisPLC](https://www.solisplc.com/blog/plc-programming-jobs)

## Complexity Classification (Cognitive Load)

Complexity measures the **cognitive load** required for a technically capable PLC programmer to understand and fix an error. This is NOT about domain expertise, but about how actionable the error message is.

### Definitions

| Level | Definition | User Experience | Examples |
|-------|------------|-----------------|----------|
| **Trivial** | Error message clearly states the problem AND the fix is immediately obvious | "I read this, I know exactly what to change" | "Variable 'X' not declared" → declare it |
| **Moderate** | Error indicates the problem but requires investigation, context, or tracing back to source | "I understand the error, but need to investigate" | "undefined reference to 'X'" → find which library/code |
| **Complex** | Error is cryptic, misleading, or requires significant investigation to understand root cause | "What does this even mean?" or "Where do I start?" | Cascading errors, cryptic tracebacks, linker issues |

### Classification Guidelines

**TRIVIAL** - Fix is obvious from the message:
- "Assignment to CONSTANT not allowed" → remove assignment or constant attribute
- "Variable not declared" → add declaration
- "Type mismatch: expected REAL, got INT" → change the type

**MODERATE** - Requires investigation but error is understandable:
- C compilation errors (syntax, types) → understand error, trace back to PLC code
- SFC/FBD connection errors → check graphical diagram
- XML schema errors → check project configuration

**COMPLEX** - Requires significant investigation:
- Linker errors (undefined reference, library not found) → build system investigation
- Python tracebacks without clear context ("NoneType has no attribute") → no obvious source
- Cascading errors → must find root cause among multiple errors
- Architecture/relocation errors → deep build system knowledge

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Evaluation Pipeline                                 │
└─────────────────────────────────────────────────────────────────────────────┘

     ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
     │   Generate   │────────▶│   Evaluate   │────────▶│    Report    │
     │  Test Cases  │         │  Classifier  │         │   Results    │
     └──────────────┘         └──────────────┘         └──────────────┘
           │                        │                        │
           ▼                        ▼                        ▼
      test_suite.json         TestCaseResult          eval_report.json
                              + LLM Judge scores      + markdown summary
```

## Dependencies

> **Note**: The evaluation runner (`run_eval.py`) currently contains a **placeholder classifier**.
> The actual classifier in `src/plc_error_classifier/classifier.py` must be built first for
> production evaluation.

| Component | Status | Location |
|-----------|--------|----------|
| Test Generator | ✅ Ready | `evaluation/generator.py` |
| LLM Judge | ✅ Ready | `evaluation/judge.py` |
| Metrics Calculator | ✅ Ready | `evaluation/metrics.py` |
| Evaluation Runner | ⚠️ Uses placeholder | `evaluation/run_eval.py` |
| **Classifier** | ❌ Not built | `src/plc_error_classifier/classifier.py` |
| **Parser** | ❌ Not built | `src/plc_error_classifier/parser.py` |

The placeholder classifier in `run_eval.py` is a simplified version that:
- Uses a basic system prompt (missing full IEC 61131-3 knowledge)
- Does not integrate the lightweight parser
- Does not support `deep_analysis` with web search

Once the classifier is built, update `run_eval.py` to import from `plc_error_classifier.classifier`.

## Directory Structure

```
evaluation/
├── README.md              # This file
├── ERROR_PATTERNS.md      # Research on error patterns by build stage
├── __init__.py            # Public API exports
├── models.py              # Pydantic data models
├── generator.py           # Synthetic test case generator
├── judge.py               # LLM-as-judge for suggestion quality
├── metrics.py             # Metrics calculation utilities
├── run_eval.py            # Main evaluation runner
├── test_cases/            # Generated test suites (JSON)
│   └── .gitkeep
└── reports/               # Evaluation reports
    └── .gitkeep
```

## Components

### 1. Data Models (`models.py`)

Defines all data structures used throughout the evaluation framework.

#### Test Case Models

```python
class TestCase:
    id: str                           # Unique identifier (e.g., "test_xml_001_a1b2c3d4")
    name: str                         # Descriptive name (e.g., "datetime_format_error")
    description: str                  # Human-readable description

    # Input data
    error_log: str                    # Build output/error log
    source_xml: str | None            # Optional PLCopen XML source

    # Ground truth
    expected_classification: ExpectedClassification
    expected_fix: ExpectedFix

    # Metadata
    error_category: str               # Category for grouping
    base_pattern: str                 # Error pattern this was generated from

class ExpectedClassification:
    severity: Literal["blocking", "warning", "info"]
    stage: Literal["xml_validation", "code_generation", "iec_compilation", "c_compilation"]
    complexity: Literal["trivial", "moderate", "complex"]

class ExpectedFix:
    root_cause: str                   # What's actually wrong
    fix_description: str              # How to fix it
    fix_location: str | None          # Where in the code
```

#### Result Models

```python
class ClassificationResult:
    test_case_id: str
    predicted_severity: str
    predicted_stage: str
    predicted_complexity: str
    expected_severity: str
    expected_stage: str
    expected_complexity: str
    severity_correct: bool
    stage_correct: bool
    complexity_correct: bool
    all_correct: bool

class SuggestionResult:
    test_case_id: str
    predicted_root_cause: str
    predicted_fix_description: str
    confidence: float
    expected_root_cause: str
    expected_fix_description: str
    root_cause_score: float           # 0-1, from LLM judge
    fix_quality_score: float          # 0-1, from LLM judge
    overall_score: float              # 0-1, weighted combination
    judge_reasoning: str              # Explanation from judge
```

#### Metrics Models

```python
class ClassificationMetrics:
    total_cases: int
    severity_accuracy: float          # % correct severity
    stage_accuracy: float             # % correct stage
    complexity_accuracy: float        # % correct complexity
    overall_accuracy: float           # All three correct
    accuracy_by_stage: dict[str, float]
    accuracy_by_severity: dict[str, float]

class SuggestionMetrics:
    total_cases: int
    avg_root_cause_score: float
    avg_fix_quality_score: float
    avg_overall_score: float
    high_quality_count: int           # score >= 0.8
    medium_quality_count: int         # 0.5 <= score < 0.8
    low_quality_count: int            # score < 0.5

class PerformanceMetrics:
    total_cases: int
    avg_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    p95_response_time_ms: float
```

### 2. Test Case Generator (`generator.py`)

Generates synthetic test cases using Gemini Flash-Lite.

#### Error Patterns

Error patterns are defined in `patterns.py` with 55 patterns generating 100 test cases:

| Stage | Patterns | Test Cases | Example Patterns |
|-------|----------|------------|------------------|
| xml_validation | 10 | 20 (20%) | datetime format, missing child element, namespace mismatch |
| code_generation | 12 | 25 (25%) | no body defined, NoneType error, SFC transition errors |
| iec_compilation | 23 | 40 (40%) | constant assignment, undeclared variable, type mismatch |
| c_compilation | 10 | 15 (15%) | undefined reference, missing header, linker errors |

**Distribution by Complexity:**
- Trivial: 36 cases (36%) - obvious fix from error message
- Moderate: 44 cases (44%) - requires context understanding
- Complex: 20 cases (20%) - requires investigation/debugging

**Distribution by Severity:**
- Blocking: 83 cases (83%) - build fails
- Warning: 17 cases (17%) - build continues with issues

#### Usage

```python
from evaluation import SyntheticTestGenerator, ERROR_PATTERNS

# Initialize generator (uses GEMINI_API_KEY from .env)
generator = SyntheticTestGenerator()

# Generate a single test case
test_case = await generator.generate_test_case(ERROR_PATTERNS[0])

# Generate full test suite
suite = await generator.generate_test_suite(
    patterns=ERROR_PATTERNS,           # Optional: subset of patterns
    use_search_for_complex=True,       # Use Google Search for complex patterns
)

# Save to file
output_path = generator.save_test_suite(suite, "test_suite.json")
```

#### CLI

```bash
uv run python -m evaluation.generator
```

### 3. LLM Judge (`judge.py`)

Evaluates suggestion quality by comparing predicted fixes against ground truth.

#### Evaluation Criteria

| Score | Root Cause | Fix Quality |
|-------|------------|-------------|
| 1.0 | Exact/semantically equivalent | Definitely resolves error |
| 0.8-0.9 | Correct with minor imprecisions | Likely resolves with minor adjustments |
| 0.5-0.7 | Partially correct | Addresses right area but incomplete |
| 0.2-0.4 | Tangentially related | Vague or partial help |
| 0.0-0.1 | Completely wrong | Would not help |

#### Usage

```python
from evaluation import SuggestionJudge

judge = SuggestionJudge()

result = await judge.evaluate_suggestion(
    test_case_id="test_001",
    error_log="...",
    expected_fix=ExpectedFix(...),
    predicted_root_cause="...",
    predicted_fix_description="...",
    confidence=0.9,
)

print(f"Overall score: {result.overall_score}")
print(f"Reasoning: {result.judge_reasoning}")
```

### 4. Metrics Calculator (`metrics.py`)

Calculates aggregate metrics from evaluation results.

#### Functions

```python
from evaluation import (
    calculate_classification_metrics,
    calculate_suggestion_metrics,
    calculate_performance_metrics,
    identify_failures,
    generate_confusion_matrix,
    format_confusion_matrix,
)

# Calculate metrics
class_metrics = calculate_classification_metrics(classification_results)
sugg_metrics = calculate_suggestion_metrics(suggestion_results)
perf_metrics = calculate_performance_metrics(test_case_results)

# Identify problem cases
failed_ids, low_quality_ids = identify_failures(results)

# Generate confusion matrix
matrix = generate_confusion_matrix(results, "stage")
print(format_confusion_matrix(matrix, "Stage Confusion Matrix"))
```

### 5. Evaluation Runner (`run_eval.py`)

Orchestrates the full evaluation pipeline.

#### Usage

```python
from evaluation import EvaluationRunner, TestSuite, format_report

# Load test suite
with open("evaluation/test_cases/test_suite.json") as f:
    suite = TestSuite.model_validate_json(f.read())

# Run evaluation
runner = EvaluationRunner()
report = await runner.run_evaluation(suite)

# Save and display
report_path = runner.save_report(report)
print(format_report(report))
```

#### CLI

```bash
# Run with default test suite
uv run python -m evaluation.run_eval

# Run with specific test suite
uv run python -m evaluation.run_eval path/to/test_suite.json
```

## Workflow

### Step 1: Generate Test Cases

```bash
uv run python -m evaluation.generator
```

This creates `evaluation/test_cases/test_suite.json` with ~21 test cases.

### Step 2: Review Generated Cases (Optional)

Manually inspect `test_suite.json` to verify:
- Error logs look realistic
- Ground truth labels are correct
- Fix descriptions are accurate

### Step 3: Run Evaluation

```bash
uv run python -m evaluation.run_eval
```

This:
1. Loads the test suite
2. Classifies each error using the classifier
3. Evaluates suggestion quality with LLM judge
4. Calculates metrics
5. Saves report to `evaluation/reports/`

### Step 4: Analyze Results

The report includes:
- **Classification accuracy** by dimension and category
- **Suggestion quality** distribution
- **Performance** timing metrics
- **Confusion matrices** for each dimension
- **Failure analysis** with specific cases

## Configuration

### Environment Variables

```bash
# Required
GEMINI_API_KEY=your_api_key_here
```

### Model Configuration

| Component | Model | Rationale |
|-----------|-------|-----------|
| Test generation | `gemini-2.5-flash-lite` | Cost-efficient for generation |
| Classification | `gemini-2.5-flash` | High accuracy required |
| LLM Judge | `gemini-2.5-flash` | Same model (noted bias risk) |

### Thinking Budget

The classifier uses `thinking_budget=1024` for balanced quality/latency.

## Extending the Framework

### Adding New Error Patterns

Edit `generator.py` and add to `ERROR_PATTERNS`:

```python
ErrorPattern(
    id="iec_013",
    name="new_error_pattern",
    stage="iec_compilation",
    severity="blocking",
    complexity="moderate",
    error_message="Your error message pattern",
    category="your_category",
    description="What triggers this error",
)
```

### Custom Complexity Heuristics

Edit `models.py` `COMPLEXITY_HEURISTICS` dict:

```python
COMPLEXITY_HEURISTICS = {
    "your_category": "trivial",  # or "moderate" or "complex"
    ...
}
```

### Using a Different Judge Model

To use a different LLM as judge (e.g., Claude, GPT-4o):

1. Create a new judge class implementing the same interface
2. Update `run_eval.py` to use your judge

## Limitations & Caveats

1. **Same-model judge bias**: Using Gemini as both classifier and judge may introduce bias. Consider using a different model for production evaluation.

2. **Synthetic data quality**: Generated test cases may not capture all real-world edge cases. Supplement with real error logs when available.

3. **Complexity subjectivity**: The "complexity" dimension is inherently subjective. The heuristics provide consistency but may not match all engineers' intuitions.

4. **Ground truth accuracy**: The expected fixes are generated, not manually verified. Manual review is recommended for high-stakes evaluation.

## Example Output

```
================================================================================
EVALUATION REPORT: PLC Error Classifier Evaluation Suite
================================================================================
Timestamp: 2024-12-03T10:30:00
Model: gemini-2.5-flash
Test Suite: PLC Error Classifier Evaluation Suite v1.0.0

----------------------------------------
CLASSIFICATION METRICS
----------------------------------------
Total Test Cases: 21
Overall Accuracy: 85.7%
  - Severity Accuracy: 95.2%
  - Stage Accuracy: 90.5%
  - Complexity Accuracy: 76.2%

Accuracy by Stage:
  - c_compilation: 100.0%
  - code_generation: 75.0%
  - iec_compilation: 91.7%
  - xml_validation: 66.7%

----------------------------------------
SUGGESTION QUALITY METRICS
----------------------------------------
Average Root Cause Score: 0.82
Average Fix Quality Score: 0.78
Average Overall Score: 0.79

Quality Distribution:
  - High Quality (≥0.8): 14
  - Medium Quality (0.5-0.8): 5
  - Low Quality (<0.5): 2

----------------------------------------
PERFORMANCE METRICS
----------------------------------------
Average Response Time: 2450ms
Min Response Time: 1200ms
Max Response Time: 4100ms
P95 Response Time: 3800ms
================================================================================
```
