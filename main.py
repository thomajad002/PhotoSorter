#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
from utils       import choose_folder
from sort_logic  import sort_files, handle_live, strong_sort, find_duplicates, sort_files_copy
from app_ui      import launch_app


def _resolve_dir(raw: str, label: str) -> Path:
    cand = Path(raw).expanduser()
    if not cand.exists() or not cand.is_dir():
        print(f'Provided {label} is not a directory.')
        sys.exit(1)
    return cand


def run_cli(args):
    if args.src_path:
        src = _resolve_dir(args.src_path, '--src')
    else:
        src = choose_folder()

    if not src:
        print('No folder selected, exiting.')
        sys.exit(1)

    if args.dest_path:
        if args.duplicates or args.live:
            print('--dest can only be used with sorting mode.')
            sys.exit(1)
        dest = _resolve_dir(args.dest_path, '--dest')
        sorted_copy = sort_files_copy(src, dest)
        print(f'Done (copied and sorted at: {sorted_copy})')
        return

    if args.duplicates:
        find_duplicates(src)
    elif args.live:
        handle_live(src)
    else:
        sort_files(src)
        if args.strong_sort:
            strong_sort(src)

    print('Done')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PhotoSorter')
    parser.add_argument('--src', '--path', dest='src_path', help='Folder to organize (skip chooser)')
    parser.add_argument('--dest', dest='dest_path', help='Destination root for copy-then-sort mode')
    parser.add_argument('--strong-sort', action='store_true', help='Review after sort')
    parser.add_argument('--duplicates', action='store_true', help='Find and resolve duplicates')
    parser.add_argument('--live', action='store_true', help='Review Live Photos')
    parser.add_argument('--no-gui', action='store_true', help='Force legacy CLI flow')
    args = parser.parse_args()

    cli_requested = any([
        args.no_gui,
        args.src_path,
        args.dest_path,
        args.strong_sort,
        args.duplicates,
        args.live,
    ])

    if cli_requested:
        run_cli(args)
    else:
        launch_app()