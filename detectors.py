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

# Backup folders support formats: mm-dd-yy, mm-dd-yyyy, or yyyy-mm-dd
BACKUP_PATTERN = re.compile(r'^(?:\d{1,2}-\d{1,2}-\d{2}(?:\d{2})?|\d{4}-\d{1,2}-\d{1,2})$')

def parse_backup_date(name: str) -> date | None:
    """
    Parse folder name into a date object.
    Returns None if it doesn't form a valid date.
    """
    parts = name.split('-')
    if len(parts) != 3:
        return None

    # yyyy-mm-dd
    if len(parts[0]) == 4:
        year, month, day = map(int, parts)
    else:
        # mm-dd-yy or mm-dd-yyyy
        month, day = map(int, parts[:2])
        year = int(parts[2])
        if year < 100:           # two-digit year
            year += 2000
    try:
        return date(year, month, day)
    except ValueError:
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