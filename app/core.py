"""
Core yt-dlp downloader module with progress tracking and file management.
"""
import os
import uuid
import asyncio
from pathlib import Path
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field
import yt_dlp
from concurrent.futures import ThreadPoolExecutor


@dataclass
class DownloadProgress:
    """Data class to track download progress."""
    task_id: str
    status: str = "pending"
    progress: float = 0.0
    filename: str = ""
    error: Optional[str] = None
    file_path: Optional[str] = None
    file_size: int = 0
    downloaded_bytes: int = 0
    speed: float = 0.0
    eta: float = 0.0
    total_bytes: int = 0
    percent: float = 0.0


class DownloadManager:
    """Manages YouTube downloads with progress tracking."""
    
    def __init__(self, download_dir: str = "downloads"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._progress_store: Dict[str, DownloadProgress] = {}
        self._semaphore = asyncio.Semaphore(3)  # Limit concurrent downloads
    
    def get_progress(self, task_id: str) -> Optional[DownloadProgress]:
        """Get the current progress of a download task."""
        return self._progress_store.get(task_id)
    
    def _create_progress_hook(self, task_id: str) -> Callable[[Dict[str, Any]], None]:
        """Create a progress hook for yt-dlp to track download progress."""
        progress = self._progress_store.get(task_id)
        
        def hook(data: Dict[str, Any]) -> None:
            if progress is None:
                return
            
            status = data.get('status', '')
            
            if status == 'downloading':
                # Get downloaded bytes
                downloaded_bytes = data.get('downloaded_bytes', 0)
                total_bytes = data.get('total_bytes', 0)
                
                # Update progress object
                progress.downloaded_bytes = downloaded_bytes
                progress.total_bytes = total_bytes
                progress.speed = data.get('speed', 0)
                progress.eta = data.get('eta', 0)
                progress.status = "downloading"
                
                # Calculate progress percentage
                if total_bytes > 0:
                    # Calculate percentage based on downloaded vs total
                    progress.percent = (downloaded_bytes / total_bytes) * 100
                    progress.progress = progress.percent
                elif 'fragment_index' in data and 'fragment_count' in data:
                    # For fragmented downloads
                    fragment_percent = data['fragment_index'] / data['fragment_count'] * 100
                    progress.percent = fragment_percent
                    progress.progress = fragment_percent
                else:
                    # If we can't calculate percentage, estimate based on state
                    progress.progress = 0
                    progress.percent = 0
                    
            elif status == 'finished':
                progress.progress = 100.0
                progress.percent = 100.0
                progress.status = "processing"
                progress.filename = data.get('filename', '')
                
            elif status == 'error':
                progress.status = "error"
                progress.error = data.get('error', 'Download failed')
                
        return hook
    
    async def download_video(self, url: str, format_type: str = "video", 
                            quality: str = "best") -> Dict[str, Any]:
        """
        Download a YouTube video or audio.
        
        Args:
            url: YouTube video URL
            format_type: "video" for MP4, "audio" for MP3
            quality: Video quality preference
        
        Returns:
            Dictionary containing task_id and initial status
        """
        task_id = str(uuid.uuid4())
        output_folder = self.download_dir / task_id
        output_folder.mkdir(parents=True, exist_ok=True)
        
        # Initialize progress tracking
        progress = DownloadProgress(task_id=task_id, status="starting")
        self._progress_store[task_id] = progress
        
        # Run download in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        async with self._semaphore:
            try:
                await loop.run_in_executor(
                    self.executor,
                    self._perform_download,
                    task_id, url, format_type, quality, str(output_folder)
                )
            except Exception as e:
                progress.status = "error"
                progress.error = str(e)
                
        return {
            "task_id": task_id,
            "status": progress.status,
            "progress": progress.progress,
            "error": progress.error,
            "file_path": progress.file_path
        }
    
    def _perform_download(self, task_id: str, url: str, format_type: str,
                         quality: str, output_folder: str) -> None:
        """Execute the actual download using yt-dlp."""
        progress = self._progress_store.get(task_id)
        
        ydl_opts = {
            'outtmpl': f'{output_folder}/%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [self._create_progress_hook(task_id)],
            'nocheckcertificate': True,
            'nocheckcertificate': True,
            'extractor_retries': 3,
            'fragment_retries': 3,
            'retries': 3,
            'file_access_retries': 3,
            'socket_timeout': 30,
        }
        
        if format_type == "audio":
            # MP3 download configuration
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'postprocessor_args': [
                    '-metadata', 'title=%(title)s',
                    '-metadata', 'artist=%(uploader)s',
                ],
                'writethumbnail': False,
            })
        else:
            # Video download configuration
            if quality == "best":
                ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            elif quality == "worst":
                ydl_opts['format'] = 'worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst'
            else:
                # Specific quality
                ydl_opts['format'] = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}]'
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract video info first
                info = ydl.extract_info(url, download=False)
                progress.filename = info.get('title', 'video')
                
                # Perform actual download
                ydl.download([url])
            
            # Find the downloaded file
            progress = self._progress_store.get(task_id)
            if progress and progress.status != "error":
                progress.status = "completed"
                
                # Find the actual file path
                downloaded_files = list(Path(output_folder).glob("*"))
                for f in downloaded_files:
                    if f.is_file() and not f.name.startswith('.'):
                        progress.file_path = str(f)
                        progress.filename = f.name
                        break
                        
        except Exception as e:
            if progress:
                progress.status = "error"
                progress.error = str(e)
    
    def get_file_path(self, task_id: str) -> Optional[str]:
        """Get the file path for a completed download."""
        progress = self._progress_store.get(task_id)
        if progress and progress.status == "completed":
            return progress.file_path
        return None
    
    def cleanup_task(self, task_id: str) -> bool:
        """
        Clean up files for a specific task.
        
        Args:
            task_id: The task UUID
            
        Returns:
            True if cleanup was successful, False otherwise
        """
        try:
            task_folder = self.download_dir / task_id
            if task_folder.exists():
                import shutil
                shutil.rmtree(task_folder)
            
            # Remove from progress store
            if task_id in self._progress_store:
                del self._progress_store[task_id]
                
            return True
        except Exception as e:
            print(f"Cleanup failed for task {task_id}: {e}")
            return False
    
    def cleanup_old_files(self, max_age_hours: int = 1) -> int:
        """
        Clean up all files older than specified hours.
        
        Args:
            max_age_hours: Maximum age in hours for files to keep
            
        Returns:
            Number of folders cleaned up
        """
        import time
        from datetime import datetime, timedelta
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cleaned_count = 0
        
        if not self.download_dir.exists():
            return 0
            
        for item in self.download_dir.iterdir():
            if item.is_dir():
                try:
                    # Check folder modification time
                    mod_time = datetime.fromtimestamp(item.stat().st_mtime)
                    if mod_time < cutoff_time:
                        shutil.rmtree(item)
                        cleaned_count += 1
                except Exception as e:
                    print(f"Error cleaning {item}: {e}")
                    
        return cleaned_count


# Global download manager instance
download_manager = DownloadManager()
