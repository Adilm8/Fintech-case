"""Plain-language explanation of an already computed payment check.

Mount in the FastAPI app: ``app.include_router(explain.router)``.
The explanation never changes the verdict and never adds facts that are not in the check.
"""

from app.explain.models import ExplainRequest, ExplainResponse
from app.explain.service import explain, router

__all__ = ["ExplainRequest", "ExplainResponse", "explain", "router"]
