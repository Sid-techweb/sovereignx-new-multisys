from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def get_health():
    """
    Returns the backend service health status.
    """
    return {
        "status": "ok",
        "service": "sovereignx-backend"
    }
