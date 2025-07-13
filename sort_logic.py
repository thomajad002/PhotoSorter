import os
import hashlib
import re
import shutil
import tkinter as tk
from tkinter import messagebox, filedialog
from send2trash import send2trash
from pathlib import Path
from datetime import datetime
from utils       import IMAGE_EXTS, VIDEO_EXTS, safe_mkdir, cleanup_empty, get_earliest_timestamp
from detectors  import BACKUP_PATTERN, parse_backup_date, is_screenshot, is_screen_recording
from diologs    import FolderDialog, DecisionDialog, DuplicateDialog, LiveDialog

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
    """Trash every Thumbs.db or .aae anywhere under src."""
    for f in src.rglob('*'):
        if not f.is_file():
            continue
        nl = f.name.lower()
        if nl == 'thumbs.db' or nl.endswith('.aae') or nl.endswith('.modd') or nl.endswith('.moff'):
            send2trash(str(f))
            cleanup_empty(f.parent, src)

def handle_backup_folders(src: Path):
    """
    Only top-level (iterdir) folders matching BACKUP_PATTERN.
    Prune sidecars, move files dated < folder_date, then relocate folder.
    """
    for folder in sorted(src.iterdir()):
        if not folder.is_dir() or not BACKUP_PATTERN.match(folder.name):
            continue

        folder_date = parse_backup_date(folder.name)
        if not folder_date:
            continue

        moved = kept = 0

        # Step 1: inside the backup folder
        for file in folder.rglob('*'):
            if not file.is_file() or file.name.startswith('._'):
                continue

            nl  = file.name.lower()
            ext = file.suffix.lower()

            # only media
            if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
                continue

            # move if strictly older than label
            ts      = get_earliest_timestamp(file)
            file_dt = datetime.fromtimestamp(ts).date()
            if file_dt < folder_date:
                dest = src / str(file_dt.year) / datetime.fromtimestamp(ts).strftime('%m-%B')
                if safe_mkdir(dest):
                    shutil.move(str(file), str(dest / file.name))
                    cleanup_empty(file.parent, folder)
                moved += 1
            else:
                kept += 1

        # Step 2: relocate the (possibly reduced) backup folder
        year_dir = src / str(folder_date.year)
        if safe_mkdir(year_dir):
            shutil.move(str(folder), str(year_dir / folder.name))
            # clean up any empty parent *of* the backup folder (but not the folder itself)
            cleanup_empty(folder.parent, src)

        # Summary
        print(f"→ Backup '{folder.name}': moved {moved}, kept {kept}")

def apply_choice_to_folder(entry: Path, root: Path, choice: str):
    """
    Apply 'sort_inside' or 'sort_into_years' choice to every media file in 'entry'.
    """
    target_root = entry if choice == 'sort_inside' else root
    for file in entry.rglob('*'):
        if not file.is_file() or file.name.startswith('._'):
            continue
        ext = file.suffix.lower()
        if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
            continue

        if is_screenshot(file):
            dest = target_root / 'Screenshots'
        elif is_screen_recording(file):
            dest = target_root / 'ScreenRecordings'
        else:
            ts   = get_earliest_timestamp(file)
            dt   = datetime.fromtimestamp(ts)
            dest = target_root / str(dt.year) / dt.strftime('%m-%B')

        if safe_mkdir(dest):
            shutil.move(str(file), str(dest / file.name))
            cleanup_empty(file.parent, root)

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

    # 2) interactive pass on every non‐generated top‐level folder,
    #    tracking any that the user chooses to “keep as is” (skip entire subtree).
    skipped: set[str] = set()
    for entry in sorted(src.iterdir()):
        if not entry.is_dir() or BACKUP_PATTERN.match(entry.name):
            continue

        # if user chooses to quit, stop altogether
        res = interactive_walk(entry, src)
        if res is False:
            return
        # if res is the string 'skip', remember to leave this subtree alone
        if res == 'skip':
            skipped.add(entry.name)

    # 3) final loose-file sweep (but skip any top‐level folders the user told us to keep)
    for file in src.rglob('*'):
        if not file.is_file():
            continue
        # skip files under any top‐level folder we marked “skip”
        rel = file.relative_to(src)
        if rel.parts and rel.parts[0] in skipped:
            continue
  

        name_l = file.name.lower()
        # global sidecars
        if name_l == 'thumbs.db' or name_l.endswith('.aae'):
            send2trash(str(file))
            cleanup_empty(file.parent, src)
            continue

        if file.name.startswith('._'):
            continue

        # **new**: skip anything under a backup-folder at any depth
        rel_parts = file.relative_to(src).parts
        if any(BACKUP_PATTERN.match(part) for part in rel_parts):
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
            except Exception:
                pass


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

def find_duplicates(src: Path):
    hashes = {}
    for file in src.rglob('*'):
        if not file.is_file() or file.suffix.lower() not in IMAGE_EXTS:
            continue
        if file.name.startswith('._'):
            continue
        h = hashlib.md5(file.read_bytes()).hexdigest()
        hashes.setdefault(h, []).append(file)

    dup_groups = [g for g in hashes.values() if len(g) > 1]
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
            for j, f in enumerate(group):
                if j != idx:
                    send2trash(str(f))
                    cleanup_empty(f.parent, src)
        elif action == 'delete_all':
            for f in group:
                send2trash(str(f))
                cleanup_empty(f.parent, src)
        # keep_all → no action