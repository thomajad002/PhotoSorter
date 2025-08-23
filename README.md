# PhotoSorter

I created this program after trying to look through thousands of pictures that were never sorted that well on my parents family photo hard drives. This program was specifically designed to work with how my parents labeled the folders, but I believe this application can still be usefull for organizing your photos and cleaning up duplicates. I hope it can help you too!



## Overview

PhotoSorter organizes a messy folder of mixed photos & videos into a clean hierarchy:
```
YYYY/
  MM-Month/
Screenshots/
ScreenRecordings/
```
It:
- Detects screenshots and screen recordings.
- Handles “backup” dated folders intelligently (various date-name formats).
- Optionally performs an interactive review (“strong sort”) to flag Junk or Memes and rename/move items. (Might be too overwelming if done with too many photos)
- Detects duplicate images and lets you pick which to keep.
- Lets you review iPhone-style Live Photo video companions (`*-Live.mov`).
- Cleans up sidecar/junk metadata files automatically.

Core modules:  
- [main.py](main.py) – CLI entry point  
- [sort_logic.py](sort_logic.py) – main organizing functions: [`sort_files`](sort_logic.py), [`strong_sort`](sort_logic.py), [`find_duplicates`](sort_logic.py), [`handle_live`](sort_logic.py)  
- [detectors.py](detectors.py) – date folder parsing / media type detection: [`BACKUP_PATTERN`](detectors.py), [`parse_backup_date`](detectors.py), `is_screenshot`, `is_screen_recording`  
- [utils.py](utils.py) – helpers: [`choose_folder`](utils.py), `get_earliest_timestamp`, `safe_mkdir`  
- [diologs.py](diologs.py) – Tk dialogs for interactive decisions  

## Features

| Feature | Description |
|--------|-------------|
| Automatic date sorting | Uses filesystem creation / modification timestamp (earliest of both) |
| Backup folder handling | Keeps files in place if folder date matches earliest creation date; otherwise redistributes |
| Screenshot extraction | PNGs and images whose EXIF Software tag contains “screen” go to `Screenshots/` |
| Screen recording extraction | Video metadata / filename heuristics → `ScreenRecordings/` |
| Interactive folder decisions | Prompts for ambiguous / legacy folders |
| Strong review pass | Image-by-image triage: Keep / Junk / Meme / Rename / Move date |
| Duplicate detection | Finds all duplicate folders, and askes which one to keep, default being automaticaly selected based off of being the most likely original |
| Live Photo review | Handle `*-Live.mov` companions |
| Junk sidecar cleanup | Removes `.aae .xmp .ini .lnk .thm .db .modd .moff` |

## 1. Prerequisites

You need Python 3.10+ with Tk support.

### Required Python packages

Mandatory:
- pillow (PIL fork)
- send2trash

Optional (enables extra capability):
- pillow-heif (to open HEIC/HEIF images)
- hachoir (better screen recording detection metadata)

Install (all extras):
```
pip3 install pillow send2trash pillow-heif hachoir
```
If you only want the basics (no HEIC or metadata parsing):
```
pip3 install pillow send2trash
```

### Operating System Notes

#### macOS
1. Install Python (from python.org or `brew install python`).
2. Ensure Tk is bundled (official installer includes it). If using Homebrew and Tk issues arise: `brew install python-tk@3.12` (version may vary).
3. (Optional) HEIF support: `pip3 install pillow-heif`.
4. Run the script (Gatekeeper may prompt for permissions when opening file dialogs).

#### Windows
1. Install Python from python.org (check "Add Python to PATH").
2. Tkinter ships with the standard installer—no extra step.
3. Command Prompt / PowerShell:
   ```
   pip3 install pillow send2trash pillow-heif hachoir
   ```
4. Optional: If HEIC not needed, omit `pillow-heif`.

#### Linux (Ubuntu/Debian example)
1. System packages for Tk & build tools:
   ```
   sudo apt update
   sudo apt install -y python3 python3-pip3 python3-tk build-essential
   ```
2. Install Python deps:
   ```
   pip3 install pillow send2trash pillow-heif hachoir
   ```
   (If `pillow-heif` wheels unavailable, you may need libheif: `sudo apt install libheif1`.)
3. Desktop environment required for Tk dialogs (headless servers need X forwarding).

## 2. Installation

Clone or copy the project directory. (A formal package install isn’t required.)

Optional: Create a virtual environment:
```
python -m venv .venv
source .venv/bin/activate     # macOS/Linux
.\.venv\Scripts\activate      # Windows
pip3 install pillow send2trash pillow-heif hachoir
```

## 3. Running

Basic (sort only):
```
python3 main.py
```

Interactive strong review after auto sort:
```
python3 main.py --strong-sort
```

Duplicate detection only (no sorting):
```
python3 main.py --duplicates
```

Live Photo companion review only:
```
python3 main.py --live
```

You will first be prompted to choose the source folder (`choose_folder` GUI from [`choose_folder`](utils.py)).

## 4. How Sorting Works

1. Sidecar cleanup: unwanted auxiliary files removed first.
2. Top-level loose media files moved into:
   ```
   <root>/<YEAR>/<MM-Month>/
   ```
3. Screenshots → `<root>/Screenshots/`
4. Screen recordings → `<root>/ScreenRecordings/`
5. Backup-style folders (matching [`BACKUP_PATTERN`](detectors.py)) are analyzed:
   - Folder names like: `09-07-21`, `09-07-2021`, `2021-09-07`, `2021-09`, `09-2021`, with `-` or `_`.
   - If a “majority date” ( >50% of files match same actual day inside a month folder) is inferred via [`infer_backup_date`](detectors.py), that date is preserved; otherwise files are redistributed by real timestamp.
   - Remaining backup folder (if date resolved) is moved under its year: `YEAR/<original-backup-folder>`; else deleted if emptied.
6. Remaining subfolders walked depth-first; unknown folders prompt a decision dialog (`FolderDialog`).
7. Optional strong pass (`strong_sort`) displays each image for review (`DecisionDialog`).
8. Live Photo videos (`*-Live.mov`) optionally handled via `--live` (`LiveDialog`).
9. Duplicate detection (`find_duplicates`):
   - Groups by size, then MD5 hash via multiprocessing.
   - Default pick determined by [`choose_default_duplicate`](sort_logic.py) scoring:
     - Original vs addon names (addon patterns: `(n)`, trailing digits, `-Live`)
     - Smaller numeric suffix
     - Earliest timestamp
     - Preferred folder type (date > screenshots/memes > other > backup)

## 5. File & Folder Naming Rules / Expectations

While individual media files are sorted by timestamp (not filename), naming affects:

### a. Backup Folder Recognition
Folder names that match `mm-dd-yy`, `mm-dd-yyyy`, `yyyy-mm-dd`, `yyyy-mm`, or `mm-yyyy` (with `-` or `_`) trigger backup handling. Examples:
```
2021-09-07
09-07-21
2021-09
09-2021
2021_09_07
09_07_2021
```
If you rename legacy dump folders to one of these patterns, PhotoSorter can treat them intelligently.

### b. Live Photos
iOS-style naming: main still plus a `*-Live.mov` video (e.g. `IMG_1234.JPG` + `IMG_1234-Live.mov`).  
When you rename via the Decision dialog, the companion `-Live.mov` is also renamed to stay paired.

### c. Duplicate “Addon” Patterns
Files considered addons (lower priority):
```
photo (1).jpg
photo 1.jpg
photo-Live.mov
```
Minimizing these (by deduplicating at source) improves clarity.

### d. Screenshots / Screen Recordings
Screenshots often:
- PNG extension, or
- EXIF Software tag containing “screen”

Screen recordings detected by:
- QuickTime / AVFoundation metadata (if `hachoir` available), or
- Filename containing `screenrecording` or `screen recording`

### e. Month Folder Format
Date folders are always produced as `YYYY/MM-Month` (e.g. `2023/04-April`). Avoid manually creating conflicting variants.

## 6. Interactive Workflows

### Strong Sort (Visual Triage)
Invoked with `--strong-sort` after baseline sorting. Lets you:
- Mark Junk (sent to system trash via `send2trash`)
- Mark Meme (moves to `Memes/`)
- Rename base filename
- Change date folder (moves image into a different `YYYY/MM-...` path)
- Skip folder
- Quit early

(Underlying code: [`strong_sort`](sort_logic.py) using `DecisionDialog`.)

### Duplicate Handling
Run with:
```
python main.py --duplicates
```
You get a grid of thumbnails (`DuplicateDialog`). Actions:
- Keep This One (trash all others)
- Keep All
- Delete All
- Quit

## 7. Screenshots (Placeholders)

Add your screenshots in a `docs/` folder or similar.

1. Main folder choice dialog  
   ![Folder Choice](docs/images/folder-choice.png)

2. Folder decision dialog  
   ![Folder Dialog](docs/images/folder-dialog.png)

3. Strong sort (image triage)  
   ![Strong Sort](docs/images/strong-sort.png)

4. Duplicate selection dialog  
   ![Duplicate Dialog](docs/images/duplicates.png)

5. Live Photo review  
   ![Live Photo Dialog](docs/images/live-photo.png)

## 8. Optional Components

| Component | Benefit | How to Omit |
|-----------|---------|------------|
| `pillow-heif` | Read HEIC/HEIF | Just don’t install; HEIC files may fail |
| `hachoir` | Better screen recording detection | Skip; falls back to filename heuristics |

## 9. Safety / Reversibility

- Deletions use system trash (`send2trash`) – recoverable.
- Moves occur within the chosen root; keep a backup before large reorganizations.
- If something stops mid-run, you can re-run safely (idempotent for already-sorted files).

## 10. Troubleshooting

| Issue | Fix |
|-------|-----|
| Tk window doesn’t appear (Linux) | Ensure desktop session and `python3-tk` installed |
| HEIC won’t open | Install `pillow-heif` |
| Slow duplicate hashing | Large images: be patient; runs in parallel |
| Wrong date placement | File’s original mtime/ctime may be off – adjust manually via “Change Date Folder” |

## 11. Extending

You can add formats by editing `IMAGE_EXTS` / `VIDEO_EXTS` in [utils.py](utils.py).  
Tune backup recognition by modifying [`BACKUP_PATTERN`](detectors.py).  
Add/remove junk extensions in `remove_sidecars` inside [sort_logic.py](sort_logic.py).

## 13. Disclaimer

Always test on a copy first. No warranty—use at your own risk.