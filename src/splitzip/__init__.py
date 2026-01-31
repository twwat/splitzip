"""
splitzip - Create split ZIP archives compatible with standard tools.

Create multi-part ZIP archives that can be extracted with Windows Explorer,
WinZip, 7-Zip, and other standard tools without requiring special software.

Example:
    >>> import splitzip
    >>>
    >>> # Simple one-liner
    >>> splitzip.create("backup.zip", ["file1.txt", "data/"], split_size="100MB")
    >>>
    >>> # Context manager for more control
    >>> with splitzip.SplitZipWriter("backup.zip", split_size="100MB") as zf:
    ...     zf.write("file1.txt")
    ...     zf.write("data/", recursive=True)
    ...     zf.writestr("hello.txt", b"Hello, world!")

The resulting files will be named:
    backup.z01, backup.z02, ..., backup.zip

The final .zip file contains the central directory and must be present
along with all .zXX files for extraction.
"""

from __future__ import annotations

from pathlib import Path

from .exceptions import (
    CompressionError,
    FileNotFoundInArchiveError,
    IntegrityError,
    SplitZipError,
    UnsafePathError,
    VolumeError,
    VolumeTooSmallError,
)
from .structures import Compression
from .utils import format_size, parse_size
from .writer import SplitZipWriter

__version__ = "0.2.0"
__all__ = [
    # Main classes
    "SplitZipWriter",
    # Convenience functions
    "create",
    # Constants
    "Compression",
    "STORED",
    "DEFLATED",
    # Utilities
    "parse_size",
    "format_size",
    # Exceptions
    "SplitZipError",
    "VolumeError",
    "VolumeTooSmallError",
    "CompressionError",
    "IntegrityError",
    "FileNotFoundInArchiveError",
    "UnsafePathError",
]

# Convenience aliases
STORED = Compression.STORED
DEFLATED = Compression.DEFLATED


def create(
    path: str,
    files: list[str],
    split_size: int | str,
    compression: int = DEFLATED,
    compresslevel: int = 6,
    recursive: bool = True,
) -> list[Path]:
    """
    Create a split ZIP archive from a list of files/directories.

    This is a convenience function for simple use cases. For more control,
    use SplitZipWriter directly.

    Args:
        path: Path for the final .zip file.
        files: List of file/directory paths to include.
        split_size: Maximum size per volume (e.g., "100MB", "700MiB", 104857600).
        compression: Compression method (STORED or DEFLATED).
        compresslevel: DEFLATE compression level 1-9 (default 6).
        recursive: If True, add directory contents recursively.

    Returns:
        List of Path objects to all volume files created.

    Example:
        >>> splitzip.create(
        ...     "backup.zip",
        ...     ["documents/", "photos/", "important.pdf"],
        ...     split_size="650MB"  # CD-ROM size
        ... )
        [Path('backup.z01'), Path('backup.z02'), Path('backup.zip')]
    """
    with SplitZipWriter(
        path,
        split_size=split_size,
        compression=compression,
        compresslevel=compresslevel,
    ) as zf:
        for file_path in files:
            zf.write(file_path, recursive=recursive)

    return zf.volume_paths
