"""Tests for FastAPI endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from plc_error_classifier.api import app
from plc_error_classifier.models import (
    ClassifyResponse,
    ErrorClassification,
    FixSuggestion,
)


@pytest.fixture
def mock_classify_response() -> ClassifyResponse:
    """Create a mock ClassifyResponse."""
    return ClassifyResponse(
        classification=ErrorClassification(
            severity="blocking",
            stage="iec_compilation",
            complexity="trivial",
        ),
        suggestions=[
            FixSuggestion(
                root_cause="Variable is constant",
                fix_description="Remove constant attribute",
                code_before='<localVars constant="true">',
                code_after="<localVars>",
                confidence=0.95,
            ),
        ],
    )


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        """Test health endpoint returns healthy status."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestClassifyEndpoint:
    """Tests for /classify endpoint."""

    @pytest.mark.asyncio
    async def test_classify_success(self, mock_classify_response: ClassifyResponse) -> None:
        """Test successful classification."""
        with patch(
            "plc_error_classifier.api.classify",
            new_callable=AsyncMock,
            return_value=mock_classify_response,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/classify",
                    json={"error_log": "Error: constant assignment"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["classification"]["severity"] == "blocking"
        assert data["classification"]["stage"] == "iec_compilation"
        assert len(data["suggestions"]) == 1
        assert data["suggestions"][0]["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_classify_with_source_xml(self, mock_classify_response: ClassifyResponse) -> None:
        """Test classification with source XML provided."""
        with patch(
            "plc_error_classifier.api.classify",
            new_callable=AsyncMock,
            return_value=mock_classify_response,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/classify",
                    json={
                        "error_log": "Error: constant assignment",
                        "source_xml": "<project>...</project>",
                    },
                )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_classify_missing_error_log(self) -> None:
        """Test that missing error_log returns 422."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/classify",
                json={},  # Missing error_log
            )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_classify_invalid_json(self) -> None:
        """Test that invalid JSON returns 422."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/classify",
                content="not valid json",
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_classify_value_error(self) -> None:
        """Test that ValueError from classifier returns 400."""
        with patch(
            "plc_error_classifier.api.classify",
            new_callable=AsyncMock,
            side_effect=ValueError("API key not set"),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/classify",
                    json={"error_log": "Error: test"},
                )

        assert response.status_code == 400
        assert "API key not set" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_classify_internal_error(self) -> None:
        """Test that unexpected errors return 500."""
        with patch(
            "plc_error_classifier.api.classify",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Unexpected error"),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/classify",
                    json={"error_log": "Error: test"},
                )

        assert response.status_code == 500
        assert "Classification failed" in response.json()["detail"]


class TestAPIResponseFormat:
    """Tests for API response format compliance."""

    @pytest.mark.asyncio
    async def test_response_has_required_fields(
        self, mock_classify_response: ClassifyResponse
    ) -> None:
        """Test response contains all required fields."""
        with patch(
            "plc_error_classifier.api.classify",
            new_callable=AsyncMock,
            return_value=mock_classify_response,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/classify",
                    json={"error_log": "Error: test"},
                )

        data = response.json()

        # Check classification fields
        assert "classification" in data
        assert "severity" in data["classification"]
        assert "stage" in data["classification"]
        assert "complexity" in data["classification"]

        # Check suggestions fields
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)
        assert len(data["suggestions"]) > 0

        suggestion = data["suggestions"][0]
        assert "root_cause" in suggestion
        assert "fix_description" in suggestion
        assert "confidence" in suggestion
        # code_before and code_after can be null
        assert "code_before" in suggestion
        assert "code_after" in suggestion

    @pytest.mark.asyncio
    async def test_multiple_suggestions_ordered_by_confidence(self) -> None:
        """Test that multiple suggestions are returned correctly."""
        multi_suggestion_response = ClassifyResponse(
            classification=ErrorClassification(
                severity="blocking",
                stage="code_generation",
                complexity="moderate",
            ),
            suggestions=[
                FixSuggestion(
                    root_cause="Primary cause",
                    fix_description="Primary fix",
                    confidence=0.90,
                ),
                FixSuggestion(
                    root_cause="Secondary cause",
                    fix_description="Secondary fix",
                    confidence=0.70,
                ),
                FixSuggestion(
                    root_cause="Tertiary cause",
                    fix_description="Tertiary fix",
                    confidence=0.50,
                ),
            ],
        )

        with patch(
            "plc_error_classifier.api.classify",
            new_callable=AsyncMock,
            return_value=multi_suggestion_response,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/classify",
                    json={"error_log": "Error: test"},
                )

        data = response.json()
        assert len(data["suggestions"]) == 3
        # Verify order (highest confidence first)
        confidences = [s["confidence"] for s in data["suggestions"]]
        assert confidences == sorted(confidences, reverse=True)
