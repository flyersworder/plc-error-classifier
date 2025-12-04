"""Tests for the classifier module."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plc_error_classifier.classifier import (
    build_system_prompt,
    build_user_prompt,
    classify,
    classify_sync,
    load_knowledge_base,
)
from plc_error_classifier.models import ClassifyRequest

# Sample test data paths
SAMPLE_DATA_DIR = Path(__file__).parent.parent / "sample_data"


class TestLoadKnowledgeBase:
    """Tests for knowledge base loading."""

    def test_load_existing_knowledge_base(self) -> None:
        """Test loading existing knowledge base file."""
        knowledge = load_knowledge_base()
        # Should load the IEC_61131_KNOWLEDGE.md file
        assert len(knowledge) > 0
        assert "IEC 61131-3" in knowledge or "Beremiz" in knowledge

    def test_build_system_prompt_includes_knowledge(self) -> None:
        """Test that system prompt includes domain knowledge."""
        prompt = build_system_prompt()
        assert "IEC 61131-3" in prompt
        assert "severity" in prompt.lower()
        assert "stage" in prompt.lower()


class TestBuildUserPrompt:
    """Tests for user prompt building."""

    def test_error_log_only(self) -> None:
        """Test prompt with only error log."""
        prompt = build_user_prompt("Error: build failed")
        assert "<error_log>" in prompt
        assert "Error: build failed" in prompt
        assert "<source_xml>" not in prompt
        assert "Classify this error" in prompt

    def test_with_source_xml(self) -> None:
        """Test prompt with both error log and source XML."""
        prompt = build_user_prompt("Error: build failed", "<project>test</project>")
        assert "<error_log>" in prompt
        assert "<source_xml>" in prompt
        assert "<project>test</project>" in prompt

    def test_xml_truncation(self) -> None:
        """Test that very long XML is truncated."""
        long_xml = "x" * 10000
        prompt = build_user_prompt("Error", long_xml)
        # Should be truncated to 8000 chars
        assert len(prompt) < 10000

    def test_context_first_question_last(self) -> None:
        """Test that context comes before the question (Gemini best practice)."""
        prompt = build_user_prompt("Error: test", "<xml>test</xml>")
        error_pos = prompt.find("<error_log>")
        xml_pos = prompt.find("<source_xml>")
        question_pos = prompt.find("Classify this error")

        assert error_pos < question_pos
        assert xml_pos < question_pos


class TestClassifyWithMockedLLM:
    """Tests for classify function with mocked LLM."""

    @pytest.fixture
    def mock_response_json(self) -> str:
        """Sample LLM response JSON."""
        return """
        {
            "classification": {
                "severity": "blocking",
                "stage": "iec_compilation",
                "complexity": "trivial"
            },
            "suggestions": [
                {
                    "root_cause": "Variable declared as constant but assigned",
                    "fix_description": "Remove constant attribute",
                    "code_before": "<localVars constant=\\"true\\">",
                    "code_after": "<localVars>",
                    "confidence": 0.95
                }
            ]
        }
        """

    @pytest.mark.asyncio
    async def test_classify_returns_valid_response(self, mock_response_json: str) -> None:
        """Test that classify returns properly structured response."""
        mock_response = MagicMock()
        mock_response.text = mock_response_json

        mock_aclient = AsyncMock()
        mock_aclient.models.generate_content = AsyncMock(return_value=mock_response)

        mock_client = MagicMock()
        mock_client.aio.__aenter__ = AsyncMock(return_value=mock_aclient)
        mock_client.aio.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("plc_error_classifier.classifier.genai.Client", return_value=mock_client),
            patch("plc_error_classifier.classifier.GEMINI_API_KEY", "test-key"),
        ):
            request = ClassifyRequest(error_log="Error: constant assignment")
            response = await classify(request)

        assert response.classification.severity == "blocking"
        assert response.classification.stage == "iec_compilation"
        assert response.classification.complexity == "trivial"
        assert len(response.suggestions) == 1
        assert response.suggestions[0].confidence == 0.95

    @pytest.mark.asyncio
    async def test_classify_raises_on_missing_api_key(self) -> None:
        """Test that classify raises ValueError when API key is missing."""
        with patch("plc_error_classifier.classifier.GEMINI_API_KEY", ""):
            request = ClassifyRequest(error_log="Error: test")
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                await classify(request)

    @pytest.mark.asyncio
    async def test_classify_raises_on_empty_response(self) -> None:
        """Test that classify raises ValueError on empty LLM response."""
        mock_response = MagicMock()
        mock_response.text = None

        mock_aclient = AsyncMock()
        mock_aclient.models.generate_content = AsyncMock(return_value=mock_response)

        mock_client = MagicMock()
        mock_client.aio.__aenter__ = AsyncMock(return_value=mock_aclient)
        mock_client.aio.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("plc_error_classifier.classifier.genai.Client", return_value=mock_client),
            patch("plc_error_classifier.classifier.GEMINI_API_KEY", "test-key"),
        ):
            request = ClassifyRequest(error_log="Error: test")
            with pytest.raises(ValueError, match="Empty response"):
                await classify(request)

    def test_classify_sync_wrapper(self, mock_response_json: str) -> None:
        """Test synchronous wrapper for classify."""
        mock_response = MagicMock()
        mock_response.text = mock_response_json

        mock_aclient = AsyncMock()
        mock_aclient.models.generate_content = AsyncMock(return_value=mock_response)

        mock_client = MagicMock()
        mock_client.aio.__aenter__ = AsyncMock(return_value=mock_aclient)
        mock_client.aio.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("plc_error_classifier.classifier.genai.Client", return_value=mock_client),
            patch("plc_error_classifier.classifier.GEMINI_API_KEY", "test-key"),
        ):
            request = ClassifyRequest(error_log="Error: test")
            response = classify_sync(request)

        assert response.classification.severity == "blocking"


class TestClassifyWithRealSamples:
    """Tests using real sample data files (requires API key - marked for integration)."""

    @pytest.fixture
    def constant_error_log(self) -> str:
        """Load constant_error.txt sample."""
        return (SAMPLE_DATA_DIR / "constant_error.txt").read_text()

    @pytest.fixture
    def constant_error_xml(self) -> str:
        """Load constant_error.xml sample."""
        return (SAMPLE_DATA_DIR / "constant_error.xml").read_text()

    @pytest.fixture
    def empty_project_log(self) -> str:
        """Load empty_project.txt sample."""
        return (SAMPLE_DATA_DIR / "empty_project.txt").read_text()

    def test_sample_files_exist(self) -> None:
        """Verify sample data files exist."""
        assert (SAMPLE_DATA_DIR / "constant_error.txt").exists()
        assert (SAMPLE_DATA_DIR / "constant_error.xml").exists()
        assert (SAMPLE_DATA_DIR / "empty_project.txt").exists()
        assert (SAMPLE_DATA_DIR / "empty_project.xml").exists()

    def test_user_prompt_with_real_data(
        self, constant_error_log: str, constant_error_xml: str
    ) -> None:
        """Test prompt building with real sample data."""
        prompt = build_user_prompt(constant_error_log, constant_error_xml)
        assert "Cannot build project" in prompt
        assert "CONSTANT variables" in prompt
        assert "localVars" in prompt
