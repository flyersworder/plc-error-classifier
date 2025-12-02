- do not mention claude code in commit messages

## Google Gemini 2.5 Models (as of Dec 2025)

### Model Lineup

| Model | Input Cost | Output Cost | Best For |
|-------|------------|-------------|----------|
| gemini-2.5-flash-lite | $0.10/1M tokens | $0.40/1M tokens | High-volume, low-latency, cheapest |
| gemini-2.5-flash | $0.30/1M tokens | $2.50/1M tokens | Best price-performance, agentic use |
| gemini-2.5-pro | Higher (tiered at 200k+) | Higher (tiered) | Complex reasoning, coding, STEM |

### Key Features
- All models: 1M token context window
- Thinking mode: Off by default for Flash-Lite, On by default for Flash/Pro
- Built-in Google Search grounding available on all models
- Code execution tool available

### Google Search Grounding Usage

```python
from google import genai
from google.genai import types

client = genai.Client()

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Your query here",
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    ),
)
```

### Thinking Budget Control

Control reasoning effort and latency with `thinking_budget` parameter:

| Value | Behavior |
|-------|----------|
| `0` | Thinking OFF - lowest latency |
| `1` - `24576` | Cap on thinking tokens |
| `-1` | Model decides automatically |

```python
config = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(
        thinking_budget=1024  # 0 to 24576, or -1 for auto
    )
)
```

**Note**: Flash-Lite has thinking OFF by default. Set budget > 0 to enable.

### Prompting Best Practices

Full reference: `docs/GEMINI_PROMPTING.md`

**Core principles**:
1. Be direct and specific - avoid verbose instructions
2. Use consistent structure (XML tags or Markdown)
3. Place critical instructions early (system instruction or prompt start)
4. For long context: context FIRST, questions LAST

**Structured output (JSON)**:
```python
from pydantic import BaseModel
from typing import Literal

class Classification(BaseModel):
    severity: Literal["blocking", "warning", "info"]
    stage: str

config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=Classification,
)
```

**Few-shot examples**: Always include when possible - significantly improves quality.

**Temperature**:
- Classification: `0.0 - 0.3` (deterministic)
- Generation: `0.7 - 1.0` (variety)
- With Search: `1.0` (recommended)

### Notes
- Use `google_search` tool (not `google_search_retrieval` which is deprecated)
- Recommended temperature: 1.0 for grounded responses
- Grounding metadata includes citation URLs with character offsets
- SDK: `google-genai` package
