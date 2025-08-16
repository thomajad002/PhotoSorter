import os
import platform
import shutil
import sys
import time
import re
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
        try:
            stat = path.parent.stat()
        except FileNotFoundError:
            return datetime.now().timestamp()

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


# --- New macOS Cocoa (NSOpenPanel) implementation (more stable on newer macOS betas) ---

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
        try:
            stat = path.parent.stat()
        except FileNotFoundError:
            return datetime.now().timestamp()

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


def _is_tahoe_beta() -> bool:
    if platform.system() != 'Darwin':
        return False
    ver = platform.mac_ver()[0] or "0"
    try:
        major = int(ver.split('.')[0])
        return major >= 26
    except Exception:
        return False

def _choose_folder_cocoa() -> Path | None:
    if platform.system() != 'Darwin':
        return None
    try:
        from AppKit import (NSOpenPanel, NSApplication, NSScreen,
                            NSFloatingWindowLevel)
        from Foundation import NSUserDefaults
    except Exception:
        return None
    try:
        app = NSApplication.sharedApplication()
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(False)
        panel.setCanChooseDirectories_(True)
        panel.setAllowsMultipleSelection_(False)
        panel.setCanCreateDirectories_(True)
        panel.setTitle_("Select folder to organize")

        # Reset any cached off-screen frame position
        try:
            NSUserDefaults.standardUserDefaults().removeObjectForKey_("NSWindow Frame NSOpenPanel")
        except Exception:
            pass

        # Center panel manually (some betas ignore center())
        try:
            screen = NSScreen.mainScreen()
            if screen:
                sf = screen.frame()
                panel.center()
                # Force after short delay (rare race)
        except Exception:
            pass

        # Keep above other windows so it doesn’t vanish when clicked
        try:
            panel.setLevel_(NSFloatingWindowLevel)
        except Exception:
            pass

        result = panel.runModal()
        if result == 1 and panel.URL():
            return Path(panel.URL().path())
    except Exception:
        return None
    return None

def _choose_folder_tk() -> Path | None:
    try:
        root = tk.Tk()
        root.withdraw()
        if platform.system() == 'Darwin':
            try:
                root.call('::tk::unsupported::MacWindowStyle', 'style', root._w, 'plain', 'none')
            except tk.TclError:
                pass
        folder = filedialog.askdirectory(
            parent=root,
            title="Select folder to organize",
            initialdir=str(Path.home()),
            mustexist=True
        )
        root.destroy()
        return Path(folder) if folder else None
    except Exception:
        try:
            root.destroy()
        except Exception:
            pass
        return None

def _choose_folder_basic() -> Path | None:
    """
    Pure Tk directory browser (no native panels). Adds a watchdog to
    pull the window back on-screen if macOS beta moves it.
    """
    root = tk.Tk()
    root.title("Select folder")
    # Initial position (will be re-centered if it drifts)
    root.geometry("720x520+240+140")

    # Keep on top briefly to avoid losing it / drifting off-screen
    try:
        root.attributes('-topmost', True)
        root.after(1500, lambda: root.attributes('-topmost', False))
    except Exception:
        pass

    current = Path.home().resolve()
    chosen: dict[str, Path | None] = {'p': None}

    path_var = tk.StringVar(value=str(current))
    tk.Label(root, textvariable=path_var, anchor='w').pack(fill='x', padx=8, pady=6)

    frame = tk.Frame(root)
    frame.pack(fill='both', expand=True)
    lb = tk.Listbox(frame)
    lb.pack(side='left', fill='both', expand=True)
    sb = tk.Scrollbar(frame, command=lb.yview)
    sb.pack(side='right', fill='y')
    lb.config(yscrollcommand=sb.set, exportselection=False)

    def refresh():
        lb.delete(0, tk.END)
        entries = ['..']
        try:
            with os.scandir(current) as it:
                dirs = [e.name for e in it if e.is_dir()]
            dirs.sort(key=str.lower)
            entries += dirs
        except PermissionError:
            pass
        for n in entries:
            lb.insert(tk.END, n)
        path_var.set(str(current))

    def open_sel(event=None):
        nonlocal current
        idx = lb.curselection()
        if not idx:
            return
        name = lb.get(idx[0])
        if name == '..':
            par = current.parent
            if par != current:
                current = par
                refresh()
            return
        nxt = current / name
        if nxt.is_dir():
            current = nxt.resolve()
            refresh()

    def choose():
        chosen['p'] = current
        root.destroy()

    def cancel():
        root.destroy()

    lb.bind('<Double-1>', open_sel)
    root.bind('<Return>', lambda e: choose())
    root.bind('<Escape>', lambda e: cancel())

    btnf = tk.Frame(root)
    btnf.pack(pady=6)
    tk.Button(btnf, text='Open', command=open_sel).pack(side='left', padx=4)
    tk.Button(btnf, text='Select This Folder', command=choose).pack(side='left', padx=4)
    tk.Button(btnf, text='Cancel', command=cancel).pack(side='left', padx=4)

    refresh()

    # Geometry watchdog (macOS Tahoe beta off-screen fix)
    want_debug = bool(os.environ.get('CHOOSE_FOLDER_DEBUG'))
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()

    def log(msg):
        if want_debug:
            print(f"[chooser] {msg}")

    def watchdog():
        try:
            geo = root.geometry()  # WxH+X+Y
            parts = geo.split('+')
            if len(parts) >= 3:
                wh = parts[0].split('x')
                w = int(wh[0]) if wh and wh[0].isdigit() else 700
                h = int(wh[1]) if len(wh) > 1 and wh[1].isdigit() else 500
                x = int(parts[1])
                y = int(parts[2])
                off = x < -20 or y < -20 or x > sw - 80 or y > sh - 80
                if off:
                    cx = max(20, (sw - w)//2)
                    cy = max(40, (sh - h)//3)
                    root.geometry(f"{w}x{h}+{cx}+{cy}")
                    log(f"Recentered from ({x},{y}) to ({cx},{cy})")
        except Exception as e:
            log(f"watchdog error: {e}")
        finally:
            root.after(350, watchdog)

    root.after(400, watchdog)
    root.mainloop()
    return chosen['p']

def choose_folder() -> Path | None:
    """
    Layered strategy with forced safe fallback.
    Set CHOOSE_FOLDER_BACKEND=basic to skip native dialogs entirely.
    """
    backend = os.environ.get('CHOOSE_FOLDER_BACKEND', '').strip().lower()
    debug = bool(os.environ.get('CHOOSE_FOLDER_DEBUG'))

    def log(msg):
        if debug:
            print(f"[choose_folder] {msg}")

    if backend:
        order = [backend]
    else:
        if platform.system() == 'Darwin':
            order = ['basic'] if _is_tahoe_beta() else ['cocoa', 'basic', 'tk']
        else:
            order = ['tk', 'basic']

    for mode in order:
        log(f"Trying backend {mode}")
        if mode == 'cocoa':
            p = _choose_folder_cocoa()
        elif mode == 'tk':
            p = _choose_folder_tk()
        else:
            p = _choose_folder_basic()
        if p:
            log(f"Selected {p}")
            return p
        log(f"{mode} failed/cancelled")

    try:
        txt = input("Enter path (blank cancel): ").strip()
        if txt:
            p = Path(txt).expanduser()
            if p.exists() and p.is_dir():
                return p
    except EOFError:
        pass
    return None