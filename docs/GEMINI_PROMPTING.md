# Gemini 2.5 Prompting Best Practices

Reference documentation for prompting Gemini 2.5 Flash and Flash-Lite models.

Sources:
- [Google AI Prompt Design Strategies](https://ai.google.dev/gemini-api/docs/prompting-strategies)
- [Gemini Structured Output](https://ai.google.dev/gemini-api/docs/structured-output)
- [Gemini 2.5 Flash Documentation](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash)

---

## Core Principles

### 1. Be Direct and Specific

State your goal clearly and concisely. Avoid unnecessary or overly persuasive language.

```
❌ "Could you please help me analyze this error log? It would be really great if you could..."
✓ "Analyze this error log. Classify by severity, stage, and complexity."
```

### 2. Use Consistent Structure

Use XML-style tags or Markdown headings consistently throughout the prompt.

```
<context>
You are an IEC 61131-3 PLC expert.
</context>

<task>
Classify the following error log.
</task>

<format>
Respond in JSON with: severity, stage, complexity, root_cause
</format>
```

### 3. Prioritize Critical Instructions

Place essential constraints and format requirements early—in system instructions or at the beginning of the prompt.

```python
config = types.GenerateContentConfig(
    system_instruction="""You are an IEC 61131-3 expert.
    Always respond in valid JSON.
    Never include markdown formatting.""",
)
```

### 4. Structure Long Contexts

When providing large amounts of context:
1. Supply all context FIRST
2. Place specific instructions/questions at the END

```
<error_log>
[... long error log here ...]
</error_log>

<source_xml>
[... optional XML context ...]
</source_xml>

Now classify this error and suggest fixes.
```

---

## Structured Output (JSON)

### Configuration

Use `response_mime_type` and `response_schema` for guaranteed JSON output:

```python
from google import genai
from google.genai import types
from pydantic import BaseModel

class ErrorClassification(BaseModel):
    severity: str
    stage: str
    complexity: str
    root_cause: str

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ErrorClassification,
    ),
)
```

### Best Practices for Schemas

1. **Use specific types**: `integer`, `string`, `enum` over generic types
2. **Add descriptions**: Help the model understand field purposes
3. **Use enums for limited values**: Ensures valid outputs

```python
from typing import Literal

class ErrorClassification(BaseModel):
    severity: Literal["blocking", "warning", "info"]
    stage: Literal["xml_validation", "code_generation", "iec_compilation", "c_compilation"]
    complexity: Literal["trivial", "moderate", "complex"]
```

---

## Few-Shot Examples

Always include examples when possible. They significantly improve output quality.

```
<examples>
<example>
<input>
Warning: Assignment to CONSTANT variables is not allowed.
</input>
<output>
{"severity": "blocking", "stage": "iec_compilation", "complexity": "trivial"}
</output>
</example>

<example>
<input>
AttributeError: 'NoneType' object has no attribute 'upper'
File "/root/beremiz/PLCGenerator.py"
</input>
<output>
{"severity": "blocking", "stage": "code_generation", "complexity": "moderate"}
</output>
</example>
</examples>

Now classify this error:
<input>
{actual_error_log}
</input>
```

### Few-Shot Best Practices

- **Consistent format**: All examples should use identical structure
- **Representative coverage**: Include examples for each category
- **Similar complexity**: Match example complexity to real inputs

---

## Temperature Settings

| Use Case | Temperature | Rationale |
|----------|-------------|-----------|
| Classification | `0.0 - 0.3` | Deterministic, consistent outputs |
| Generation/Creative | `0.7 - 1.0` | More variety |
| With Google Search | `1.0` | Recommended for grounded responses |

```python
config = types.GenerateContentConfig(
    temperature=0.1,  # Low for classification tasks
)
```

---

## Thinking Budget (Gemini 2.5)

Control reasoning effort and latency:

| Budget | Use Case | Latency |
|--------|----------|---------|
| `0` | Simple extraction, no reasoning needed | Fastest |
| `512-1024` | Standard classification | Balanced |
| `4096+` | Complex multi-step reasoning | Slower |
| `-1` | Let model decide | Variable |

```python
config = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(
        thinking_budget=1024
    )
)
```

**Note**: Flash-Lite has thinking OFF by default. Flash has it ON by default.

---

## Google Search Grounding

For up-to-date information or when model knowledge is insufficient:

```python
config = types.GenerateContentConfig(
    tools=[types.Tool(google_search=types.GoogleSearch())],
    temperature=1.0,  # Recommended for grounded responses
)
```

**When to use**:
- Queries about recent events
- Technical documentation lookups
- Verification of factual claims

**When NOT to use**:
- Classification tasks (adds latency)
- When you have all context in the prompt

---

## Model-Specific Tips

### Gemini 2.5 Flash

- Default thinking: ON
- Best for: Classification, complex reasoning, agentic tasks
- Supports: Structured output, tools, grounding

### Gemini 2.5 Flash-Lite

- Default thinking: OFF (set budget > 0 to enable)
- Best for: High-volume, low-latency tasks, data generation
- More sensitive to prompt quality—be extra clear

---

## Common Pitfalls

### 1. Overly Complex Prompts

```
❌ Long nested instructions with multiple conditions
✓ Break into separate prompts or use clear structure
```

### 2. Relying on Model for Facts

```
❌ "What are all the error codes in matiec?"
✓ Provide the error codes in context, ask model to match
```

### 3. Inconsistent Examples

```
❌ Examples with different formats, some JSON, some plain text
✓ All examples use identical structure and format
```

### 4. Ignoring Token Limits

- Flash/Flash-Lite: 1M token context
- But more tokens = more latency and cost
- Truncate or summarize long inputs when possible

---

## Prompt Template for Error Classification

```python
SYSTEM_PROMPT = """You are an expert in IEC 61131-3 PLC programming and the Beremiz toolchain.

## Your Task
Analyze PLC compilation error logs and provide structured classification.

## Classification Categories

### Severity
- blocking: Build fails, cannot continue
- warning: Build succeeds with warnings
- info: Informational messages only

### Stage
- xml_validation: PLCopen XML schema errors
- code_generation: Beremiz Python errors (PLCGenerator.py, etc.)
- iec_compilation: matiec/iec2c compiler errors
- c_compilation: gcc/linker errors

### Complexity
- trivial: Single error, obvious one-line fix
- moderate: Requires understanding context/types
- complex: Multiple errors, architectural issues

## Output Format
Respond ONLY with valid JSON matching this schema:
{
    "severity": "blocking|warning|info",
    "stage": "xml_validation|code_generation|iec_compilation|c_compilation",
    "complexity": "trivial|moderate|complex",
    "root_cause": "Brief explanation",
    "fix_suggestion": "How to fix"
}"""

USER_PROMPT = """<error_log>
{error_log}
</error_log>

Classify this error."""
```

---

## Performance Optimization

| Goal | Strategy |
|------|----------|
| Lower latency | `thinking_budget=0`, shorter prompts |
| Higher accuracy | Few-shot examples, `thinking_budget=1024+` |
| Lower cost | Flash-Lite, minimal context |
| Consistent output | Low temperature, structured output schema |
