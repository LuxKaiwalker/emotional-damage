from fastapi import APIRouter, Path

from app.api.deps import HighScoresDep
from app.models import HighScoreResponse

router = APIRouter(prefix="/api/highscores", tags=["highscores"])


@router.get("/{client_id}", response_model=HighScoreResponse)
async def get_high_score(
    highscores: HighScoresDep,
    client_id: str = Path(pattern=r"^[A-Za-z0-9_-]{8,64}$"),
) -> HighScoreResponse:
    """This browser's best final score. Read-only: only the server records scores."""
    score = highscores.get(client_id)
    return HighScoreResponse(**score.model_dump()) if score else HighScoreResponse()
