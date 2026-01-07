"""
Utility functions for file management and cleanup.
"""
import os
import time
import asyncio
from pathlib import Path
from typing import Optional
import shutil


def ensure_directory(path: str) -> bool:
    """
    Ensure a directory exists.
    
    Args:
        path: Directory path to create
        
    Returns:
        True if directory exists or was created, False on error
    """
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False


def get_file_info(file_path: str) -> Optional[dict]:
    """
    Get information about a file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Dictionary with file information or None if error
    """
    try:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return None
            
        stat = path.stat()
        return {
            "name": path.name,
            "size": stat.st_size,
            "size_human": format_file_size(stat.st_size),
            "extension": path.suffix.lower(),
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "path": str(path.absolute())
        }
    except Exception:
        return None


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in bytes to human readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to remove unsafe characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove or replace unsafe characters
    unsafe_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', '\0']
    result = filename
    for char in unsafe_chars:
        result = result.replace(char, '_')
    
    # Limit length
    if len(result) > 200:
        name, ext = os.path.splitext(result)
        result = name[:200 - len(ext)] + ext
    
    return result.strip()


def remove_file_safely(file_path: str) -> bool:
    """
    Safely remove a file, handling common errors.
    
    Args:
        file_path: Path to file to remove
        
    Returns:
        True if successful, False otherwise
    """
    try:
        path = Path(file_path)
        if path.exists() and path.is_file():
            path.unlink()
        return True
    except Exception:
        return False


def remove_directory_contents(folder_path: str, remove_folder: bool = True) -> bool:
    """
    Remove all contents of a directory.
    
    Args:
        folder_path: Path to directory
        remove_folder: Whether to remove the folder itself
        
    Returns:
        True if successful, False otherwise
    """
    try:
        path = Path(folder_path)
        if not path.exists():
            return True
            
        for item in path.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception:
                pass
                
        if remove_folder:
            path.rmdir()
            
        return True
    except Exception:
        return False


async def async_remove_file(file_path: str) -> bool:
    """
    Asynchronously remove a file.
    
    Args:
        file_path: Path to file to remove
        
    Returns:
        True if successful, False otherwise
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, remove_file_safely, file_path)


def get_directory_size(folder_path: str) -> int:
    """
    Get total size of a directory in bytes.
    
    Args:
        folder_path: Path to directory
        
    Returns:
        Total size in bytes
    """
    try:
        path = Path(folder_path)
        total = 0
        for item in path.rglob('*'):
            if item.is_file():
                total += item.stat().st_size
        return total
    except Exception:
        return 0


def list_files_recursive(folder_path: str, extensions: Optional[list] = None) -> list:
    """
    List all files in a directory recursively, optionally filtered by extension.
    
    Args:
        folder_path: Path to directory
        extensions: List of extensions to filter (e.g., ['.mp3', '.mp4'])
        
    Returns:
        List of file paths
    """
    try:
        path = Path(folder_path)
        if not path.exists():
            return []
            
        files = []
        for item in path.rglob('*'):
            if item.is_file():
                if extensions is None or item.suffix.lower() in extensions:
                    files.append(str(item))
        return files
    except Exception:
        return []


class CleanupScheduler:
    """Scheduler for periodic cleanup of temporary files."""
    
    def __init__(self, download_dir: str, max_age_hours: int = 1, check_interval: int = 300):
        """
        Initialize cleanup scheduler.
        
        Args:
            download_dir: Directory to clean
            max_age_hours: Maximum age in hours before deletion
            check_interval: Interval in seconds between checks
        """
        self.download_dir = Path(download_dir)
        self.max_age_hours = max_age_hours
        self.check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def _cleanup_loop(self) -> None:
        """Main cleanup loop."""
        while self._running:
            try:
                await self.perform_cleanup()
            except Exception as e:
                print(f"Cleanup error: {e}")
            
            await asyncio.sleep(self.check_interval)
    
    async def perform_cleanup(self) -> int:
        """
        Perform cleanup of old files.
        
        Returns:
            Number of items cleaned up
        """
        if not self.download_dir.exists():
            return 0
            
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(hours=self.max_age_hours)
        cleaned = 0
        
        for item in self.download_dir.iterdir():
            if item.is_dir():
                try:
                    mtime = datetime.fromtimestamp(item.stat().st_mtime)
                    if mtime < cutoff:
                        shutil.rmtree(item)
                        cleaned += 1
                except Exception:
                    pass
                    
        return cleaned
    
    def start(self) -> None:
        """Start the cleanup scheduler."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._cleanup_loop())
    
    def stop(self) -> None:
        """Stop the cleanup scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                asyncio.wait([self._task])
            except Exception:
                pass
