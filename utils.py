import os
import platform
import shutil
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from datetime import datetime
from PIL import ExifTags

# Supported extensions, including GoPro low-res preview files (.lrv)
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.heic', '.heif', '.tiff'}
VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.lrv', '.3gp', '.m2ts', '.webm', '.wmv'}
ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS | {'.aae'}

# ExifTags lookup for screenshots
SOFTWARE_TAG = next((k for k, v in ExifTags.TAGS.items() if v == 'Software'), None)


def get_earliest_timestamp(path: Path) -> float:
    """
    Return the older of (modified time) vs. (creation time).
    If the file has already vanished (e.g. a phantom ._ metadata file),
    fall back to the parent directory's mtime.
    """
    try:
        stat = path.stat()
    except FileNotFoundError:
        # most likely an Apple resource‐fork ._ file that no longer exists
        stat = path.parent.stat()

    times = [stat.st_mtime]
    if hasattr(stat, 'st_birthtime'):
        times.append(stat.st_birthtime)
    elif platform.system() == 'Windows':
        times.append(stat.st_ctime)
    return min(times)


def safe_mkdir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        if e.errno == 30:  # Read-only filesystem
            print(f"Warning: Cannot create directory {path}: read-only filesystem. Skipping.")
            return False
        raise


def cleanup_empty(path: Path, root: Path):
    p = path
    while p != root and p.exists() and p.is_dir() and not any(p.iterdir()):
        try:
            p.rmdir()
        except Exception:
            break
        p = p.parent


def choose_folder() -> Path | None:
    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.attributes("-topmost", True)
    folder = filedialog.askdirectory(title="Select folder to organize", parent=root)
    root.destroy()
    return Path(folder) if folder else None