import os
import sys
import hashlib
import re
import shutil
import tkinter as tk
from tkinter import messagebox, filedialog
from send2trash import send2trash
from pathlib import Path
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor

from utils       import IMAGE_EXTS, VIDEO_EXTS, safe_mkdir, cleanup_empty, get_earliest_timestamp
from detectors   import BACKUP_PATTERN, parse_backup_date, is_screenshot, is_screen_recording
from diologs     import FolderDialog, DecisionDialog, DuplicateDialog, LiveDialog

# Folders we generate ourselves—never ask on these, but do descend into them.
GENERATED_FOLDERS = {'Screenshots', 'ScreenRecordings', 'Memes'}
YEAR_PATTERN      = re.compile(r'^\d{4}$')
MONTH_PATTERN     = re.compile(r'^\d{2}-[A-Za-z]+$')   # e.g. "04-April", "11-November"

def is_generated_folder(name: str) -> bool:
    return (
        name in GENERATED_FOLDERS
        or YEAR_PATTERN.match(name) is not None
        or MONTH_PATTERN.match(name) is not None
        or BACKUP_PATTERN.match(name) is not None
    )

## When we hit an “unrecognized” folder, ask where to move it
def prompt_and_move(folder_path: str):
    root = tk.Tk()
    root.withdraw()
    target = filedialog.askdirectory(
        title=f'Where do you want to move "{os.path.basename(folder_path)}"?',
        initialdir=os.path.dirname(folder_path)
    )
    root.destroy()
    if target:
        shutil.move(folder_path, os.path.join(target, os.path.basename(folder_path)))

def remove_sidecars(src: Path):
    """Trash every sidecar files anywhere under src."""
    sidecar_exts = {'.aae', '.xmp', '.ini', '.lnk', '.thm', '.db', '.modd', '.moff'}  # Add any more junk files here so they get auto deleted

    for file in src.rglob('*'):
        if not file.is_file():
            continue
        if file.suffix.lower() in sidecar_exts:
            print(f"→ Removing junk file: {file.relative_to(src)}")
            send2trash(str(file))
            cleanup_empty(file.parent, src)

def handle_backup_folders(src: Path):
    """
    Depth-first, find any folders whose name matches BACKUP_PATTERN,
    auto-sort their contents into the main year/month tree,
    then remove the now-empty backup folder.
    """
    # collect all matching folders
    backups = []
    for dirpath, dirnames, _ in os.walk(src):
        folder = Path(dirpath)
        if folder == src:
            continue
        if BACKUP_PATTERN.match(folder.name):
            backups.append(folder)
    # sort deepest first
    backups.sort(key=lambda p: len(p.parts), reverse=True)

    for folder in backups:
        # move everything under this folder into YYYY/MM-Month under src
        apply_choice_to_folder(folder, src, 'sort_into_years')
        # clean up if empty
        cleanup_empty(folder, src)
        print(f"→ Auto‐sorted backup folder: {folder.relative_to(src)}")

def apply_choice_to_folder(entry: Path, root: Path, choice: str):
    """
    Move every image/video under `entry`:
      - 'sort_inside'    → into subfolders under `entry` itself
      - 'sort_into_years'→ into year/month under `root`
    """
    target = entry if choice == 'sort_inside' else root

    for file in entry.rglob('*'):
        if not file.is_file() or file.name.startswith('._'):
            continue
        ext = file.suffix.lower()
        if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
            continue

        # --- SPECIAL-CASE generated folders so they NEVER nest ---
        if choice == 'sort_inside' and entry.name in GENERATED_FOLDERS:
            dest = entry

        # --- otherwise, your usual destination logic ---
        else:
            if is_screenshot(file):
                dest = target / 'Screenshots'
            elif is_screen_recording(file):
                dest = target / 'ScreenRecordings'
            else:
                ts   = get_earliest_timestamp(file)
                dt   = datetime.fromtimestamp(ts)
                dest = target / str(dt.year) / dt.strftime('%m-%B')

        if safe_mkdir(dest):
            try:
                shutil.move(str(file), str(dest / file.name))
                cleanup_empty(file.parent, root)
            except OSError:
                # skip I/O errors
                continue

def interactive_walk(path: Path, root: Path) -> bool | str:
    """
    Depth-first walk.  For any folder NOT in GENERATED_FOLDERS,
    not a pure YYYY folder, not a MM-Month folder, and not a backup:
      1) recurse into it
      2) then pop up a FOLDER dialog so you choose where to move it
      3) move it wholesale and return 'skip' (to ignore its old subtree)
    """

    for entry in sorted(path.iterdir()):
        if not entry.is_dir():
            continue

        name = entry.name

        # recognized: never prompt, just recurse
        if (
            name in GENERATED_FOLDERS
            or re.fullmatch(r'\d{4}', name)         # pure 4-digit year
            or re.fullmatch(r'\d{2}-[A-Za-z]+', name)  # MM-Month
            or BACKUP_PATTERN.match(name)
        ):
            # keep diving in
            result = interactive_walk(entry, root)
            if result is False:
                return False
            continue

        # unrecognized folder ⇒ first recurse
        result = interactive_walk(entry, root)
        if result is False:
            return False

        # then prompt with a FOLDER dialog
        tk_root = tk.Tk()
        tk_root.withdraw()
        dest = filedialog.askdirectory(
            title=f"Choose destination for folder '{name}'",
            initialdir=str(root)
        )
        tk_root.destroy()

        if not dest:
            # user cancelled → abort entire sort
            return False

        # move the entire folder
        shutil.move(str(entry), dest)
        print(f"Moved folder '{name}' → '{dest}'")

        # skip any further processing under this entry
        return 'skip'

    return True

def sort_files(src: Path):
    # 0) global sidecar purge
    remove_sidecars(src)

    # 1) fix up any top-level backup folders
    handle_backup_folders(src)

    skipped_roots: set[str] = set()

    # 2) Depth-first walk of subfolders only
    for dirpath, _, filenames in os.walk(src, topdown=False):
        folder = Path(dirpath)

        # never prompt on the root itself
        if folder == src:
            continue

        rel = folder.relative_to(src)

        # a) skip backup-pattern dirs (already handled)
        if BACKUP_PATTERN.match(folder.name):
            cleanup_empty(folder, src)
            continue

        # b) auto-sort generated folders without prompting
        if folder.name in GENERATED_FOLDERS:
            apply_choice_to_folder(folder, src, 'sort_inside')
            continue

        # c) skip already-structured year/month dirs
        if YEAR_PATTERN.match(folder.name) or MONTH_PATTERN.match(folder.name):
            continue

        # d) skip subtree if root was “skip”ped
        if rel.parts and rel.parts[0] in skipped_roots:
            continue

        # e) skip and delete if no media files here
        has_media = any(
            (folder / f).suffix.lower() in IMAGE_EXTS | VIDEO_EXTS
            for f in filenames
        )
        if not has_media:
            cleanup_empty(folder, src)
            continue

        # f) prompt the user for this folder
        choice = FolderDialog(folder).run()
        if choice == 'quit':
            sys.exit(0)
        if choice is False or choice == 'keep':
            continue
        if choice == 'skip':
            skipped_roots.add(rel.parts[0])
            continue

        # g) apply user’s choice
        if choice in ('sort_inside', 'sort_into_years'):
            apply_choice_to_folder(folder, src, choice)

        # h) finally, move any loose files in this exact folder
        for fname in filenames:
            file = folder / fname
            if not file.is_file() or file.name.startswith('._'):
                continue
            if any(BACKUP_PATTERN.match(p) for p in file.relative_to(src).parts):
                continue
            ext = file.suffix.lower()
            if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
                continue

            if is_screenshot(file):
                dest = src / 'Screenshots'
            elif is_screen_recording(file):
                dest = src / 'ScreenRecordings'
            else:
                ts = get_earliest_timestamp(file)
                dt = datetime.fromtimestamp(ts)
                dest = src / str(dt.year) / dt.strftime('%m-%B')

            if safe_mkdir(dest):
                try:
                    shutil.move(str(file), str(dest / file.name))
                    cleanup_empty(file.parent, src)
                except OSError:
                    continue



def handle_live(src: Path):
    for file in src.rglob('*-Live.mov'):
        dlg = LiveDialog(file, src)
        choice = dlg.run()
        if choice == 'quit':
            return
        elif choice == 'delete':
            send2trash(str(file))
            cleanup_empty(file.parent, src)
        # keep: do nothing and continue


def strong_sort(src: Path):
    folders = sorted({f.parent for f in src.rglob('*') if f.suffix.lower() in IMAGE_EXTS})
    for folder in folders:
        for file in sorted(folder.iterdir()):
            if not file.is_file() or file.suffix.lower() not in IMAGE_EXTS:
                continue
            dlg = DecisionDialog(file, src)
            choice = dlg.run()
            if choice == 'quit':
                return
            if choice == 'skip_folder':
                break
            orig_dir = file.parent
            if choice == 'junk':
                send2trash(str(file))
                cleanup_empty(orig_dir, src)
            elif choice == 'meme':
                memes_dir = src / 'Memes'
                memes_dir.mkdir(parents=True, exist_ok=True)
                try:
                    newp = memes_dir / file.name
                    file.rename(newp)
                    cleanup_empty(orig_dir, src)
                except Exception as e:
                    print(f"Error moving meme {file}: {e}")

def choose_default_duplicate(group: list[Path], src: Path) -> int:
    """
    Score each file on:
      1) has_addon (False preferred),
      2) numeric suffix (smaller preferred),
      3) earliest timestamp (smaller preferred),
      4) folder priority (0=year/month,1=Screenshots,2=others,3=backups).
    """
    entries = []
    for f in group:
        stem = f.stem

        # 1) detect addon
        is_addon = bool(
            re.search(r'\(\d+\)$', stem) or     # (n)
            re.search(r'\s+\d+$', stem) or      # space+digits
            stem.lower().endswith('-live')      # -Live
        )

        # 2) numeric suffix
        m = re.search(r'(\d+)$', stem)
        num = int(m.group(1)) if m else float('inf')

        # 3) timestamp
        ts = get_earliest_timestamp(f)

        # 4) folder type
        parts = f.relative_to(src).parts
        if (
            len(parts) >= 2
            and re.match(r'^\d{4}$', parts[0])
            and re.match(r'^\d{2}-[A-Za-z]+$', parts[1])
        ):
            ftype = 'date'
        elif parts[0] in ('Screenshots','Memes','ScreenRecordings'):
            ftype = 'screenshot'
        elif BACKUP_PATTERN.match(parts[0]):
            ftype = 'backup'
        else:
            ftype = 'other'

        entries.append({
            'file': f,
            'is_addon': is_addon,
            'num': num,
            'ts': ts,
            'ftype': ftype
        })

    # STEP 1: originals only
    originals = [e for e in entries if not e['is_addon']]
    candidates = originals if originals else entries

    # STEP 2: smallest numeric suffix
    min_num = min(e['num'] for e in candidates)
    candidates = [e for e in candidates if e['num'] == min_num]

    # STEP 3: proper date‐folder wins
    date_ents = [e for e in candidates if e['ftype']=='date']
    if date_ents:
        chosen = min(date_ents, key=lambda e: e['ts'])['file']
        return group.index(chosen)

    # STEP 4: screenshots wins
    shot_ents = [e for e in candidates if e['ftype']=='screenshot']
    if shot_ents:
        chosen = min(shot_ents, key=lambda e: e['ts'])['file']
        return group.index(chosen)

    # STEP 5: earliest timestamp
    min_ts = min(e['ts'] for e in candidates)
    ts_ents = [e for e in candidates if e['ts']==min_ts]
    if len(ts_ents)==1:
        return group.index(ts_ents[0]['file'])

    # STEP 6: folder priority as tie‐breaker
    prio_order = {'date':0,'screenshot':1,'other':2,'backup':3}
    min_pr = min(prio_order[e['ftype']] for e in ts_ents)
    final = [e for e in ts_ents if prio_order[e['ftype']]==min_pr]
    return group.index(final[0]['file'])

def file_hash(path: Path) -> tuple[Path, str]:
    """
    Top-level function so multiprocessing can pickle it.
    Returns (path, md5hex).
    """
    h = hashlib.md5()
    with open(path, 'rb') as fp:
        for chunk in iter(lambda: fp.read(8192), b''):
            h.update(chunk)
    return path, h.hexdigest()

def find_duplicates(src: Path):
    # 1) Bucket by size
    size_map: dict[int, list[Path]] = {}
    scanned = 0
    for f in src.rglob('*'):
        if not f.is_file() or f.suffix.lower() not in IMAGE_EXTS or f.name.startswith('._'):
            continue
        size_map.setdefault(f.stat().st_size, []).append(f)
        scanned += 1

    # 2) Gather only the “collisions”
    candidates = [p for paths in size_map.values() if len(paths) > 1 for p in paths]
    if not candidates:
        messagebox.showinfo('Duplicates', 'No duplicates found.')
        return

    # 3) Parallel hash
    hash_map: dict[tuple[int,str], list[Path]] = {}
    total = len(candidates)
    hashed = 0
    with ProcessPoolExecutor() as pool:
        for path, hval in pool.map(file_hash, candidates):
            key = (path.stat().st_size, hval)
            hash_map.setdefault(key, []).append(path)
            hashed += 1
    # 4) Prompt on each real duplicate group
    dup_groups = [grp for grp in hash_map.values() if len(grp) > 1]
    if not dup_groups:
        messagebox.showinfo('Duplicates', 'No duplicates found.')
        return

    for group in dup_groups:
        default_idx = choose_default_duplicate(group, src)
        dlg = DuplicateDialog(group, default_idx)
        action = dlg.run()
        if action == 'quit':
            return
        # keep only chosen one
        if action.startswith('keep') and action != 'keep_all':
            idx = int(action.replace('keep', ''))
            for i, f in enumerate(group):
                if i != idx:
                    send2trash(str(f))
                    cleanup_empty(f.parent, src)
        elif action == 'delete_all':
            for f in group:
                send2trash(str(f))
                cleanup_empty(f.parent, src)
        # keep_all → do nothing