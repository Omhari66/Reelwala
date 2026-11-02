"""API endpoints for serving generated video files with signed expiring URLs."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.models.base import get_db
from app.models.entities import Video
from app.storage.signed_urls import verify_video_signature

router = APIRouter(prefix="/videos", tags=["videos"])


@router.get("/{video_id}")
def get_video(
    video_id: int,
    expires: int = Query(..., description="Unix timestamp expiration"),
    sig: str = Query(..., description="HMAC signature"),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Serve generated video file if signature is valid and has not expired."""
    if not verify_video_signature(video_id, expires, sig):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Expired or invalid video signature",
        )

    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )

    video_file = Path(video.path)
    if not video_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not found on disk",
        )

    return FileResponse(
        path=str(video_file),
        media_type="video/mp4",
        filename=f"reel_{video_id}.mp4",
    )
