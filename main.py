#!/usr/bin/env python3
import sys
import argparse
from utils       import choose_folder
from sort_logic  import sort_files, handle_live, strong_sort, find_duplicates

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PhotoSorter')
    parser.add_argument('--strong-sort', action='store_true', help='Review after sort')
    parser.add_argument('--duplicates', action='store_true', help='Find and resolve duplicates')
    parser.add_argument('--live', action='store_true', help='Review Live Photos')
    args = parser.parse_args()

    src = choose_folder()
    if not src:
        print('No folder selected, exiting.')
        sys.exit(1)

    if args.duplicates:
        find_duplicates(src)
    elif args.live:
        handle_live(src)
    else:
        sort_files(src)
        if args.strong_sort:
            strong_sort(src)

    print('Done')