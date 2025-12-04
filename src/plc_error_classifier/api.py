"""FastAPI application for PLC Error Classifier."""

from fastapi import FastAPI, HTTPException

from .classifier import classify
from .models import ClassifyRequest, ClassifyResponse

app = FastAPI(
    title="PLC Error Classifier",
    description="AI system that classifies PLC compilation errors and suggests fixes",
    version="0.1.0",
)


@app.post("/classify", response_model=ClassifyResponse)
async def classify_error(request: ClassifyRequest) -> ClassifyResponse:
    """Classify a PLC build error and suggest fixes.

    Args:
        request: ClassifyRequest with error_log and optional source_xml.

    Returns:
        ClassifyResponse with classification (severity, stage, complexity)
        and suggestion (root_cause, fix_description, confidence).
    """
    try:
        return await classify(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {e}") from e


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
