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
    If *that* also fails (because the parent was already moved/removed),
    fall back to the current time to avoid crashing.
    """
    try:
        stat = path.stat()
    except FileNotFoundError:
        # file has vanished—try parent folder
        try:
            stat = path.parent.stat()
        except FileNotFoundError:
            # both file and parent gone; return "now"
            return datetime.now().timestamp()

    # collect mtime, birthtime/ctime if available
    times = [stat.st_mtime]
    if hasattr(stat, 'st_birthtime'):
        times.append(stat.st_birthtime)
    elif platform.system() == 'Windows':
        times.append(stat.st_ctime)
    return min(times)


def safe_mkdir(path: Path) -> bool:
    """
    Make a directory and swallow read-only errors.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as e:
        if e.errno == 30:  # Read-only filesystem
            print(f"Warning: Cannot create directory {path}: read-only filesystem. Skipping.")
            return False
        raise


def cleanup_empty(path: Path, root: Path):
    """
    Recursively remove any empty directories up to 'root'.
    """
    p = path
    while p != root and p.exists() and p.is_dir() and not any(p.iterdir()):
        try:
            p.rmdir()
        except Exception:
            break
        p = p.parent


def choose_folder(
    title: str = "Select folder to organize",
    parent: tk.Misc | None = None,
    initialdir: str | None = None,
) -> Path | None:
    """
    Prompt the user with an NSOpenPanel/folder dialog and return the Path.
    """
    owns_root = parent is None
    root = parent
    if owns_root:
        root = tk.Tk()

    try:
        if root is not None and owns_root:
            root.withdraw()
            root.update_idletasks()
            root.update()

        kwargs = {
            'title': title,
            'mustexist': True,
        }
        if initialdir:
            kwargs['initialdir'] = initialdir

        if platform.system() == 'Darwin' and owns_root:
            # On newer macOS/Tk builds, passing a withdrawn Tk root as parent can
            # cause the chooser to dismiss immediately on click.
            folder = filedialog.askdirectory(**kwargs)
        else:
            if root is not None and owns_root:
                root.lift()
                root.attributes("-topmost", True)
            if root is not None:
                kwargs['parent'] = root
            folder = filedialog.askdirectory(**kwargs)
    finally:
        if owns_root and root is not None:
            root.destroy()

    return Path(folder) if folder else None
