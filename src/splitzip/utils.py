"""Utility functions for splitzip."""

from __future__ import annotations

import posixpath
import re
import time

from .exceptions import UnsafePathError

# Size parsing patterns
_SIZE_PATTERN = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(b|kb|mb|gb|tb|kib|mib|gib|tib|bytes?)?\s*$",
    re.IGNORECASE,
)

# Multipliers for size units
_SIZE_MULTIPLIERS: dict[str, int] = {
    "b": 1,
    "byte": 1,
    "bytes": 1,
    # Decimal (SI) units
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
    "tb": 1000**4,
    # Binary (IEC) units
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
}


def parse_size(size: int | float | str) -> int:
    """
    Parse a size specification into bytes.

    Accepts:
        - Integers: returned as-is
        - Strings: parsed with optional unit suffix

    Supported units:
        - B, byte, bytes: bytes
        - KB: kilobytes (1000 bytes)
        - MB: megabytes (1000^2 bytes)
        - GB: gigabytes (1000^3 bytes)
        - TB: terabytes (1000^4 bytes)
        - KiB: kibibytes (1024 bytes)
        - MiB: mebibytes (1024^2 bytes)
        - GiB: gibibytes (1024^3 bytes)
        - TiB: tebibytes (1024^4 bytes)

    Args:
        size: Size as integer (bytes) or string with optional unit.

    Returns:
        Size in bytes as integer.

    Raises:
        ValueError: If the size string cannot be parsed.

    Examples:
        >>> parse_size(1024)
        1024
        >>> parse_size("100MB")
        100000000
        >>> parse_size("700MiB")
        734003200
        >>> parse_size("4.7GB")
        4700000000
    """
    if isinstance(size, int):
        return size

    if isinstance(size, float):
        return int(size)

    match = _SIZE_PATTERN.match(size)
    if not match:
        raise ValueError(
            f"Invalid size format: '{size}'. "
            "Expected format: <number>[unit] (e.g., '100MB', '700MiB', '4.7GB')"
        )

    value_str, unit = match.groups()
    value = float(value_str)

    if unit is None:
        # No unit specified, assume bytes
        return int(value)

    unit_lower = unit.lower()
    if unit_lower not in _SIZE_MULTIPLIERS:
        raise ValueError(f"Unknown size unit: '{unit}'")

    return int(value * _SIZE_MULTIPLIERS[unit_lower])


def format_size(size: int, binary: bool = False) -> str:
    """
    Format a size in bytes to a human-readable string.

    Args:
        size: Size in bytes.
        binary: If True, use binary units (KiB, MiB). If False, use decimal (KB, MB).

    Returns:
        Human-readable size string.

    Examples:
        >>> format_size(1500000)
        '1.50 MB'
        >>> format_size(1572864, binary=True)
        '1.50 MiB'
    """
    if binary:
        units = ["B", "KiB", "MiB", "GiB", "TiB"]
        divisor = 1024.0
    else:
        units = ["B", "KB", "MB", "GB", "TB"]
        divisor = 1000.0

    value = float(size)
    for unit in units[:-1]:
        if abs(value) < divisor:
            return f"{value:.2f} {unit}" if value != int(value) else f"{int(value)} {unit}"
        value /= divisor

    return f"{value:.2f} {units[-1]}"


def dos_datetime(timestamp: float | None = None) -> tuple[int, int]:
    """
    Convert a Unix timestamp to DOS date and time format.

    Args:
        timestamp: Unix timestamp. If None, uses current time.

    Returns:
        Tuple of (dos_time, dos_date) as 16-bit integers.
    """
    if timestamp is None:
        timestamp = time.time()

    t = time.localtime(timestamp)

    # DOS time: bits 0-4 = seconds/2, bits 5-10 = minute, bits 11-15 = hour
    dos_time = (t.tm_sec // 2) | (t.tm_min << 5) | (t.tm_hour << 11)

    # DOS date: bits 0-4 = day, bits 5-8 = month, bits 9-15 = year - 1980
    dos_date = t.tm_mday | (t.tm_mon << 5) | ((t.tm_year - 1980) << 9)

    return dos_time, dos_date


def sanitize_arcname(path: str) -> str:
    """
    Sanitize a path for use as an archive member name.

    - Converts backslashes to forward slashes
    - Removes leading slashes and drive letters
    - Normalizes multiple slashes

    Args:
        path: Original path string.

    Returns:
        Sanitized archive name.
    """
    # Reject null bytes
    if "\x00" in path:
        raise UnsafePathError(path)

    # Convert backslashes to forward slashes
    name = path.replace("\\", "/")

    # Remove drive letter (e.g., "C:/")
    if len(name) >= 2 and name[1] == ":":
        name = name[2:]

    # Remove leading slashes
    name = name.lstrip("/")

    # Normalize multiple slashes
    while "//" in name:
        name = name.replace("//", "/")

    # Collapse .. segments
    name = posixpath.normpath(name)

    # Strip leading /
    name = name.lstrip("/")

    # Reject if it escapes root
    if name == ".." or name.startswith("../"):
        raise UnsafePathError(path)

    # normpath of empty string is "."
    if name == ".":
        name = ""

    # Validate archive name length (ZIP format limit)
    if len(name.encode("utf-8")) > 65535:
        raise ValueError(
            f"Archive name too long ({len(name.encode('utf-8'))} bytes, max 65535)"
        )

    return name
