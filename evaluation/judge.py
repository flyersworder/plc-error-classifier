"""LLM-as-judge for evaluating suggestion quality."""

import asyncio
import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from .models import ExpectedFix, SuggestionResult

# Load environment variables
load_dotenv()

# Rate limiting: max concurrent API requests
MAX_CONCURRENT_REQUESTS = 5


# ============================================================================
# Configuration
# ============================================================================

# Use Flash for judging (same as classifier, noted bias risk)
JUDGE_MODEL = "gemini-2.5-flash"


# ============================================================================
# Judge Response Schema
# ============================================================================


class JudgeEvaluation(BaseModel):
    """Structured evaluation from the LLM judge."""

    root_cause_score: float = Field(
        ge=0.0,
        le=1.0,
        description="How well the predicted root cause matches the expected one (0-1)",
    )
    fix_quality_score: float = Field(
        ge=0.0,
        le=1.0,
        description="How actionable and correct the suggested fix is (0-1)",
    )
    overall_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall quality of the suggestion (0-1)",
    )
    reasoning: str = Field(
        description="Explanation of the evaluation",
    )


# ============================================================================
# Judge Prompts
# ============================================================================

JUDGE_SYSTEM_PROMPT = """You are an expert evaluator for PLC error classification systems. Your task is to assess the quality of error analysis and fix suggestions.

## Evaluation Criteria

### Root Cause Score (0-1)
- **1.0**: Exact match or semantically equivalent identification of the root cause
- **0.8-0.9**: Correct root cause but with minor imprecisions
- **0.5-0.7**: Partially correct, identifies related issues but misses key aspects
- **0.2-0.4**: Tangentially related but mostly incorrect
- **0.0-0.1**: Completely wrong or irrelevant

### Fix Quality Score (0-1)
- **1.0**: Fix would definitely resolve the error, clear and actionable
- **0.8-0.9**: Fix would likely resolve the error with minor adjustments needed
- **0.5-0.7**: Fix addresses the right area but may not fully resolve the issue
- **0.2-0.4**: Fix is vague or would only partially help
- **0.0-0.1**: Fix would not help or is incorrect

### Overall Score (0-1)
- Weighted combination: 40% root_cause + 60% fix_quality
- A good diagnosis is less valuable without a good fix

## Important Notes

1. Be lenient with wording differences - focus on semantic equivalence
2. Partial credit for reasonable attempts
3. Consider whether the fix is actionable for a PLC engineer
4. IEC 61131-3 specific knowledge should be rewarded

Output your evaluation as JSON matching the schema provided."""

JUDGE_USER_PROMPT = """Evaluate this error analysis:

## Error Context
**Error Log:**
```
{error_log}
```

## Expected Analysis (Ground Truth)
- **Root Cause**: {expected_root_cause}
- **Fix Description**: {expected_fix}
- **Fix Location**: {expected_location}

## Predicted Analysis (To Evaluate)
- **Root Cause**: {predicted_root_cause}
- **Fix Description**: {predicted_fix}
- **Confidence**: {confidence}

Now evaluate the prediction against the expected analysis:"""


# ============================================================================
# Judge Class
# ============================================================================


class SuggestionJudge:
    """Evaluates suggestion quality using LLM-as-judge.

    Uses async API for better performance in concurrent evaluation scenarios.
    """

    def __init__(self, api_key: str | None = None):
        """Initialize the judge."""
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        self.client = genai.Client(api_key=self.api_key)
        self._semaphore: asyncio.Semaphore | None = None

    async def evaluate_suggestion(
        self,
        aclient: genai.Client,
        test_case_id: str,
        error_log: str,
        expected_fix: ExpectedFix,
        predicted_root_cause: str,
        predicted_fix_description: str,
        confidence: float,
    ) -> SuggestionResult:
        """Evaluate a single suggestion against ground truth.

        Args:
            aclient: Async Gemini client (from client.aio context manager).
            test_case_id: Unique identifier for the test case.
            error_log: The original error log being analyzed.
            expected_fix: Ground truth fix information.
            predicted_root_cause: The classifier's predicted root cause.
            predicted_fix_description: The classifier's suggested fix.
            confidence: The classifier's confidence score.

        Returns:
            SuggestionResult with quality scores from the LLM judge.
        """
        # Rate limiting
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        async with self._semaphore:
            # Build prompt
            user_prompt = JUDGE_USER_PROMPT.format(
                error_log=error_log[:2000],  # Truncate long logs
                expected_root_cause=expected_fix.root_cause,
                expected_fix=expected_fix.fix_description,
                expected_location=expected_fix.fix_location or "Not specified",
                predicted_root_cause=predicted_root_cause,
                predicted_fix=predicted_fix_description,
                confidence=confidence,
            )

            # Configure judge
            # Per GEMINI_PROMPTING.md: temperature=0.0 for deterministic evaluation
            config = types.GenerateContentConfig(
                system_instruction=JUDGE_SYSTEM_PROMPT,
                temperature=0.0,  # Deterministic evaluation
                response_mime_type="application/json",
                response_schema=JudgeEvaluation,
                thinking_config=types.ThinkingConfig(thinking_budget=0),  # Fast evaluation
            )

            # Get evaluation using async API
            response = await aclient.models.generate_content(
                model=JUDGE_MODEL,
                contents=user_prompt,
                config=config,
            )

            # Parse response
            try:
                evaluation = JudgeEvaluation.model_validate_json(response.text)
            except Exception as e:
                # Fallback to manual parsing
                try:
                    data = json.loads(response.text)
                    evaluation = JudgeEvaluation(**data)
                except Exception as parse_err:
                    raise ValueError(
                        f"Failed to parse judge response: {e}\nResponse: {response.text}"
                    ) from parse_err

            return SuggestionResult(
                test_case_id=test_case_id,
                predicted_root_cause=predicted_root_cause,
                predicted_fix_description=predicted_fix_description,
                confidence=confidence,
                expected_root_cause=expected_fix.root_cause,
                expected_fix_description=expected_fix.fix_description,
                root_cause_score=evaluation.root_cause_score,
                fix_quality_score=evaluation.fix_quality_score,
                overall_score=evaluation.overall_score,
                judge_reasoning=evaluation.reasoning,
            )


# ============================================================================
# Batch Evaluation
# ============================================================================


async def evaluate_batch(
    judge: SuggestionJudge,
    evaluations: list[dict],
) -> list[SuggestionResult]:
    """Evaluate a batch of suggestions concurrently.

    Args:
        judge: The SuggestionJudge instance
        evaluations: List of dicts with keys:
            - test_case_id
            - error_log
            - expected_fix (ExpectedFix)
            - predicted_root_cause
            - predicted_fix_description
            - confidence

    Returns:
        List of SuggestionResult objects
    """
    async with judge.client.aio as aclient:
        tasks = [
            judge.evaluate_suggestion(
                aclient=aclient,
                test_case_id=item["test_case_id"],
                error_log=item["error_log"],
                expected_fix=item["expected_fix"],
                predicted_root_cause=item["predicted_root_cause"],
                predicted_fix_description=item["predicted_fix_description"],
                confidence=item["confidence"],
            )
            for item in evaluations
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions and return successful results
    successful_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Warning: Evaluation failed for {evaluations[i]['test_case_id']}: {result}")
        else:
            successful_results.append(result)

    return successful_results
