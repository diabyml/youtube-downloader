"""
FastAPI application for YouTube video and MP3 downloads.
"""
import os
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl
from typing import Optional
import time

from .core import download_manager
from .utils import (
    get_file_info, 
    format_file_size, 
    CleanupScheduler,
    ensure_directory
)


# Create FastAPI application
app = FastAPI(
    title="YouTube Downloader",
    description="Download YouTube videos and MP3 audio files",
    version="1.0.0"
)

# Setup templates
templates = Jinja2Templates(directory="templates")

# Setup static files
static_dir = Path("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Ensure downloads directory exists
ensure_directory("downloads")

# Initialize cleanup scheduler
cleanup_scheduler = CleanupScheduler(
    download_dir="downloads",
    max_age_hours=1,
    check_interval=300
)
cleanup_scheduler.start()


# Pydantic models for request validation
class DownloadRequest(BaseModel):
    url: HttpUrl
    format_type: str = "video"
    quality: str = "best"


class DownloadResponse(BaseModel):
    task_id: str
    status: str
    progress: float
    error: Optional[str] = None
    filename: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the home page with download form."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/download")
async def start_download(request: DownloadRequest):
    """
    Start a new download task.
    
    Args:
        request: Download request with URL and options
        
    Returns:
        JSON with task_id and initial status
    """
    url = str(request.url)
    
    # Validate URL is YouTube
    if not validate_youtube_url(url):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid YouTube URL",
                "message": "Please provide a valid YouTube video URL"
            }
        )
    
    # Validate format type
    if request.format_type not in ["video", "audio"]:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid format type",
                "message": "Format must be 'video' or 'audio'"
            }
        )
    
    # Start download
    result = await download_manager.download_video(
        url=url,
        format_type=request.format_type,
        quality=request.quality
    )
    
    return JSONResponse(content=result)


@app.get("/api/status/{task_id}")
async def get_download_status(task_id: str):
    """
    Get the current status of a download task.
    
    Args:
        task_id: The task UUID
        
    Returns:
        JSON with current progress and status
    """
    progress = download_manager.get_progress(task_id)
    
    if progress is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": "Task not found",
                "message": "The requested download task does not exist"
            }
        )
    
    return JSONResponse(content={
        "task_id": task_id,
        "status": progress.status,
        "progress": progress.progress,
        "filename": progress.filename,
        "error": progress.error,
        "file_path": progress.file_path,
        "speed": progress.speed,
        "eta": progress.eta
    })


@app.get("/download/{task_id}")
async def download_file(task_id: str, background_tasks: BackgroundTasks):
    """
    Download the completed file and cleanup afterward.
    
    Args:
        task_id: The task UUID
        background_tasks: FastAPI background tasks for cleanup
        
    Returns:
        FileResponse with the downloaded file
    """
    file_path = download_manager.get_file_path(task_id)
    
    if file_path is None:
        progress = download_manager.get_progress(task_id)
        
        if progress is None:
            raise HTTPException(status_code=404, detail="Download task not found")
        
        if progress.status == "error":
            raise HTTPException(status_code=400, detail=progress.error or "Download failed")
        
        if progress.status != "completed":
            raise HTTPException(status_code=400, detail="Download not yet completed")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    file_info = get_file_info(file_path)
    
    # Add cleanup task to run after file is sent
    background_tasks.add_task(cleanup_download_task, task_id)
    
    return FileResponse(
        path=file_path,
        filename=file_info["name"] if file_info else "download",
        media_type="application/octet-stream"
    )


@app.delete("/api/task/{task_id}")
async def cancel_task(task_id: str):
    """
    Cancel and cleanup a download task.
    
    Args:
        task_id: The task UUID
        
    Returns:
        JSON confirmation of cancellation
    """
    success = download_manager.cleanup_task(task_id)
    
    if success:
        return JSONResponse(content={"message": "Task cancelled and cleaned up"})
    else:
        return JSONResponse(
            status_code=404,
            content={"error": "Task not found or cleanup failed"}
        )


@app.get("/api/cleanup")
async def trigger_cleanup():
    """
    Manually trigger cleanup of old files.
    
    Returns:
        JSON with number of cleaned items
    """
    cleaned = await cleanup_scheduler.perform_cleanup()
    return JSONResponse(content={
        "message": "Cleanup completed",
        "cleaned_items": cleaned
    })


def validate_youtube_url(url: str) -> bool:
    """
    Validate that a URL is a valid YouTube URL.
    
    Args:
        url: URL to validate
        
    Returns:
        True if valid YouTube URL
    """
    youtube_domains = [
        'youtube.com',
        'www.youtube.com',
        'youtu.be',
        'www.youtu.be'
    ]
    
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        
        # Check domain
        if parsed.netloc not in youtube_domains:
            return False
        
        # Check for video ID in various formats
        if parsed.netloc in ['youtu.be', 'www.youtu.be']:
            # Short format: youtu.be/VIDEO_ID
            return len(parsed.path.strip('/')) > 0
        
        if parsed.netloc in ['youtube.com', 'www.youtube.com']:
            # Check for /watch?v= format
            if parsed.path == '/watch':
                query_params = parsed.query
                if 'v' in query_params:
                    return True
            # Check for /shorts/ format
            if parsed.path.startswith('/shorts/'):
                return True
            # Check for /embed/ format
            if parsed.path.startswith('/embed/'):
                return True
        
        return False
    except Exception:
        return False


def cleanup_download_task(task_id: str) -> None:
    """
    Cleanup task to be run in background.
    
    Args:
        task_id: The task UUID to cleanup
    """
    time.sleep(5)  # Wait a bit to ensure file transfer completes
    download_manager.cleanup_task(task_id)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown."""
    cleanup_scheduler.stop()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
