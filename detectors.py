import warnings
from PIL import Image

# Disable PIL's "decompression bomb" protection for very large images,
# and suppress its warning. Adjust or remove if you ever really need that safety check.
warnings.simplefilter('ignore', Image.DecompressionBombWarning)
Image.MAX_IMAGE_PIXELS = None

from PIL import Image, ImageTk
import subprocess
import re
import os
import platform
from pathlib import Path
from datetime import datetime, date
from utils import IMAGE_EXTS, VIDEO_EXTS, ALL_EXTS, get_earliest_timestamp, safe_mkdir, cleanup_empty, SOFTWARE_TAG

try:
    from hachoir.parser import createParser
    from hachoir.metadata import extractMetadata
except ImportError:
    createParser = None

# Supports the following backup folder date formats:
#  • mm-dd-yy    mm_dd_yy
#  • mm-dd-yyyy  mm_dd_yyyy
#  • yyyy-mm-dd  yyyy_mm_dd
#  • yyyy-mm     yyyy_mm
#  • mm-yyyy     mm_yyyy
BACKUP_PATTERN = re.compile(
    r'^(?:'
      r'\d{1,2}[-_]\d{1,2}[-_]\d{2}(?:\d{2})?'  # mm[-_]dd[-_]yy or mm[-_]dd[-_]yyyy
    r'|'
      r'\d{4}[-_]\d{1,2}[-_]\d{1,2}'           # yyyy[-_]mm[-_]dd
    r'|'
      r'\d{4}[-_]\d{1,2}'                     # yyyy[-_]mm
    r'|'
      r'\d{1,2}[-_]\d{4}'                     # mm[-_]yyyy
    r')$'
)

def parse_backup_date(name: str) -> date | None:
    """
    Parse a backup‐folder name into a date:
      • Day‐based → exact date (09-07-21 → 2021-09-07)  
      • Month‐based → first of month  (2019-09 → 2019-09-01)  
      • Month‐Year  → first of month  (09-2019 → 2019-09-01)  
    Returns None if invalid.
    """
    parts = re.split(r'[-_]', name)
    # Day‐based
    if len(parts) == 3:
        try:
            if len(parts[0]) == 4:
                y, m, d = map(int, parts)
            else:
                m, d = map(int, parts[:2]); y = int(parts[2])
                if y < 100: y += 2000
            return date(y, m, d)
        except ValueError:
            return None
    # Two‐part cases
    if len(parts) == 2:
        p0, p1 = parts
        # YYYY‐MM
        if len(p0) == 4 and p1.isdigit():
            try:
                y, m = int(p0), int(p1)
                if 1 <= m <= 12: return date(y, m, 1)
            except ValueError:
                return None
        # MM‐YYYY
        if len(p1) == 4 and p0.isdigit():
            try:
                m, y = int(p0), int(p1)
                if 1 <= m <= 12: return date(y, m, 1)
            except ValueError:
                return None
    return None


def infer_backup_date(folder: Path) -> date | None:
    """
    Better-than‐fallback date for 'folder':
      1) If parse_backup_date gives day>1, return it.
      2) If day==1 (month‐only), tally each file’s actual date; if one date >50%,
         return that “majority” date.
      3) Otherwise (no majority), return None → sort *all* files.
    """
    base = parse_backup_date(folder.name)
    if base is None:
        return None
    # day‐based → keep exact
    if base.day != 1:
        return base

    # month‐only → tally
    counts: dict[date,int] = {}
    total = 0
    for f in folder.iterdir():
        if not f.is_file(): continue
        ext = f.suffix.lower()
        if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
            continue
        dt = datetime.fromtimestamp(get_earliest_timestamp(f)).date()
        if dt.year == base.year and dt.month == base.month:
            counts[dt] = counts.get(dt, 0) + 1
            total += 1

    if not counts:
        return None

    best_dt, best_ct = max(counts.items(), key=lambda x: x[1])
    if best_ct > total / 2:
        return best_dt

    # NO majority → return None so EVERYTHING gets sorted
    return None


def is_screenshot(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext == '.png':
        return True
    if ext not in IMAGE_EXTS:
        return False
    try:
        img = Image.open(path)
        exif = img.getexif() or {}
        if SOFTWARE_TAG and SOFTWARE_TAG in exif and 'screen' in exif.get(SOFTWARE_TAG, '').lower():
            return True
    except Exception:
        pass
    return False


def is_screen_recording(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext not in VIDEO_EXTS:
        return False
    if createParser:
        try:
            parser = createParser(str(path))
            metadata = extractMetadata(parser) if parser else None
            if metadata and metadata.has('com.apple.quicktime.software'):
                software = metadata.get('com.apple.quicktime.software').value.lower()
                if any(x in software for x in ('avfoundation','quicktime player','screen')):
                    return True
        except Exception:
            pass
    return 'screenrecording' in path.stem.lower() or 'screen recording' in path.stem.lower()


def get_file_dest(file: Path, root: Path) -> Path:
    ts = get_earliest_timestamp(file)
    dt = datetime.fromtimestamp(ts)
    return root / str(dt.year) / f"{dt.strftime('%m')}-{dt.strftime('%B')}"