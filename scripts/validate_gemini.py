"""
Quick validation test to check if Gemini models understand PLC/Beremiz errors.

Tests both gemini-2.5-flash and gemini-2.5-flash-lite with our sample error logs.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables
load_dotenv()

# Initialize client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Models to test
MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]

# System prompt for classification
SYSTEM_PROMPT = """You are an expert in IEC 61131-3 PLC programming and the Beremiz toolchain.

Analyze the provided error log and respond with a JSON object containing:
1. classification:
   - severity: "blocking", "warning", or "info"
   - stage: "xml_validation", "code_generation", "iec_compilation", or "c_compilation"
   - complexity: "trivial", "moderate", or "complex"
2. root_cause: Brief explanation of why the error occurred
3. fix_suggestion: How to fix the error

Respond ONLY with valid JSON, no markdown formatting."""

# Sample error logs
SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"


def load_sample(name: str) -> str:
    """Load a sample error log."""
    path = SAMPLE_DIR / f"{name}.txt"
    return path.read_text()


def test_model(model_name: str, error_log: str, error_name: str) -> dict[str, str]:
    """Test a model with an error log."""
    print(f"\n{'=' * 60}")
    print(f"Model: {model_name}")
    print(f"Error: {error_name}")
    print("=" * 60)

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=f"Error Log:\n```\n{error_log}\n```",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.1,  # Low temperature for consistent classification
            ),
        )

        print(f"\nResponse:\n{response.text}")
        return {"model": model_name, "error": error_name, "response": response.text}

    except Exception as e:
        print(f"\nError: {e}")
        return {"model": model_name, "error_name": error_name, "exception": str(e)}


def main() -> None:
    """Run validation tests."""
    print("=" * 60)
    print("Gemini Model Validation Test")
    print("Testing PLC/Beremiz error understanding")
    print("=" * 60)

    # Load sample errors
    samples = {
        "constant_error": load_sample("constant_error"),
        "empty_project": load_sample("empty_project"),
    }

    results = []

    # Test each model with each sample
    for model in MODELS:
        for name, error_log in samples.items():
            result = test_model(model, error_log, name)
            results.append(result)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print("\nExpected classifications:")
    print("  constant_error: blocking, iec_compilation, trivial")
    print("  empty_project:  blocking, code_generation, moderate")

    print("\nTest completed. Review responses above for accuracy.")


if __name__ == "__main__":
    main()
