"""Test google_search tool + structured output compatibility.

Based on official docs: https://ai.google.dev/gemini-api/docs/structured-output
- Structured outputs + tools only works on gemini-3-pro-preview
- For gemini-2.5-flash, must use prompt-based JSON when using google_search
"""

import os

from dotenv import load_dotenv
from google import genai
from json_repair import repair_json
from pydantic import BaseModel, Field

load_dotenv()


class SimpleResponse(BaseModel):  # type: ignore[misc]
    answer: str = Field(description="The answer to the question")
    confidence: float = Field(description="Confidence score from 0.0 to 1.0")


def test_structured_output_official_pattern() -> bool:
    """Test: Official pattern with response_json_schema (no tools)."""
    print("=" * 60)
    print("TEST 1: Official structured output pattern (no tools)")
    print("=" * 60)

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="What is 2 + 2?",
            config={
                "response_mime_type": "application/json",
                "response_json_schema": SimpleResponse.model_json_schema(),
            },
        )
        print(f"SUCCESS! Response: {response.text}")
        # Validate with Pydantic
        result = SimpleResponse.model_validate_json(response.text)
        print(f"Parsed: answer={result.answer}, confidence={result.confidence}")
        return True
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        return False


def test_search_with_structured_output() -> bool:
    """Test: google_search + structured output on gemini-2.5-flash (should fail)."""
    print("\n" + "=" * 60)
    print("TEST 2: google_search + structured output (gemini-2.5-flash)")
    print("=" * 60)

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="What is the current weather in San Francisco?",
            config={
                "tools": [{"google_search": {}}],
                "response_mime_type": "application/json",
                "response_json_schema": SimpleResponse.model_json_schema(),
            },
        )
        print(f"SUCCESS! Response: {response.text}")
        return True
    except Exception as e:
        print(f"FAILED (expected): {type(e).__name__}: {e}")
        return False


def test_search_prompt_json() -> bool:
    """Test: google_search with JSON requested in prompt (correct pattern for 2.5)."""
    print("\n" + "=" * 60)
    print("TEST 3: google_search + prompt-based JSON (gemini-2.5-flash)")
    print("=" * 60)

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="""What is the current weather in San Francisco?

Respond ONLY with valid JSON matching this schema:
{
  "answer": "your answer here",
  "confidence": 0.0-1.0
}""",
            config={
                "tools": [{"google_search": {}}],
                "temperature": 1.0,
            },
        )
        print(f"Raw response: {response.text}")

        # Parse JSON using json_repair (handles markdown code blocks)
        data = repair_json(response.text, return_objects=True)
        result = SimpleResponse.model_validate(data)
        print(f"Parsed: answer={result.answer[:50]}..., confidence={result.confidence}")

        # Show grounding metadata
        if response.candidates[0].grounding_metadata:
            gm = response.candidates[0].grounding_metadata
            if gm.web_search_queries:
                print(f"Search queries: {gm.web_search_queries}")
        return True
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        return False


def test_search_gemini3_preview() -> bool:
    """Test: google_search + structured output on gemini-3-pro-preview."""
    print("\n" + "=" * 60)
    print("TEST 4: google_search + structured output (gemini-3-pro-preview)")
    print("=" * 60)

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    try:
        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents="What is the current weather in San Francisco?",
            config={
                "tools": [{"google_search": {}}],
                "response_mime_type": "application/json",
                "response_json_schema": SimpleResponse.model_json_schema(),
            },
        )
        print(f"SUCCESS! Response: {response.text}")
        result = SimpleResponse.model_validate_json(response.text)
        print(f"Parsed: answer={result.answer[:50]}..., confidence={result.confidence}")
        return True
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    print("Testing Gemini API: google_search + structured output compatibility")
    print("Based on: https://ai.google.dev/gemini-api/docs/structured-output\n")

    results = {
        "structured output (no tools)": test_structured_output_official_pattern(),
        "search + schema (2.5-flash)": test_search_with_structured_output(),
        "search + prompt JSON (2.5-flash)": test_search_prompt_json(),
        "search + schema (3-pro-preview)": test_search_gemini3_preview(),
    }

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for test, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test}: {status}")

    print("\n" + "=" * 60)
    print("CONCLUSION")
    print("=" * 60)
    print("For gemini-2.5-flash with google_search:")
    print("  - Cannot use response_mime_type or response_json_schema")
    print("  - Must request JSON in prompt and parse manually")
    print("For gemini-3-pro-preview with google_search:")
    print("  - Can use structured output with tools (preview feature)")
