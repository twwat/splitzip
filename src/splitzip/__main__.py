"""Command-line interface for splitzip."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import SplitZipWriter, __version__, format_size, parse_size
from .structures import Compression


def progress_callback(filename: str, done: int, total: int) -> None:
    """Print progress for current file."""
    if total > 0:
        pct = (done / total) * 100
        bar_width = 30
        filled = int(bar_width * done / total)
        bar = "█" * filled + "░" * (bar_width - filled)
        print(f"\r  {bar} {pct:5.1f}% {Path(filename).name}", end="", flush=True)
        if done >= total:
            print()


def volume_callback(volume_num: int, path: Path) -> None:
    """Print when a new volume is created."""
    print(f"  Created: {path}")


def cmd_create(args: argparse.Namespace) -> int:
    """Handle the create command."""
    output = Path(args.output)
    files = [Path(f) for f in args.files]

    # Validate inputs
    for f in files:
        if not f.exists():
            print(f"Error: '{f}' does not exist", file=sys.stderr)
            return 1

    try:
        split_size = parse_size(args.split_size)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    compression = Compression.STORED if args.store else Compression.DEFLATED

    print(f"Creating split archive: {output}")
    print(f"  Split size: {format_size(split_size)}")
    print(f"  Compression: {'STORED' if args.store else f'DEFLATE level {args.level}'}")
    print()

    try:
        with SplitZipWriter(
            output,
            split_size=split_size,
            compression=compression,
            compresslevel=args.level,
            on_volume=volume_callback if args.verbose else None,
            on_progress=progress_callback if args.verbose else None,
        ) as zf:
            for file_path in files:
                if args.verbose:
                    print(f"Adding: {file_path}")
                zf.write(file_path, recursive=not args.no_recursive)

        print()
        print(f"Created {len(zf.volume_paths)} volume(s):")
        for p in zf.volume_paths:
            size = p.stat().st_size
            print(f"  {p.name}: {format_size(size)}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog="splitzip",
        description="Create split ZIP archives compatible with standard tools.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create command
    create_parser = subparsers.add_parser(
        "create",
        help="Create a split ZIP archive",
        description="Create a split ZIP archive from files and directories.",
    )
    create_parser.add_argument(
        "-o", "--output",
        required=True,
        help="Output archive path (e.g., backup.zip)",
    )
    create_parser.add_argument(
        "-s", "--split-size",
        required=True,
        help="Maximum size per volume (e.g., 100MB, 700MiB, 4.7GB)",
    )
    create_parser.add_argument(
        "files",
        nargs="+",
        help="Files and directories to add",
    )
    create_parser.add_argument(
        "-0", "--store",
        action="store_true",
        help="Store without compression",
    )
    create_parser.add_argument(
        "-l", "--level",
        type=int,
        default=6,
        choices=range(1, 10),
        metavar="1-9",
        help="Compression level (default: 6)",
    )
    create_parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Don't add directory contents recursively",
    )
    create_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show progress and volume creation",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "create":
        return cmd_create(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
