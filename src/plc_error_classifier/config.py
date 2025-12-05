"""Configuration settings for PLC Error Classifier."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# =============================================================================
# API Configuration
# =============================================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Model selection (see PLAN.md for rationale)
CLASSIFIER_MODEL = "gemini-2.5-flash"

# =============================================================================
# LLM Configuration (per GEMINI_PROMPTING.md best practices)
# =============================================================================

# Temperature: 0.0 for deterministic classification
TEMPERATURE = 0.0

# Thinking budget: 0 to disable thinking for lowest latency (<3s target)
THINKING_BUDGET = 0

# =============================================================================
# Paths
# =============================================================================

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Knowledge base document
KNOWLEDGE_BASE_PATH = PROJECT_ROOT / "docs" / "IEC_61131_KNOWLEDGE.md"
