"""Custom exceptions for splitzip."""


class SplitZipError(Exception):
    """Base exception for all splitzip errors."""


class VolumeError(SplitZipError):
    """Error related to volume management."""


class VolumeTooSmallError(VolumeError):
    """Split size is too small to fit required headers."""

    def __init__(self, split_size: int, min_required: int) -> None:
        self.split_size = split_size
        self.min_required = min_required
        super().__init__(
            f"Split size {split_size} bytes is too small. "
            f"Minimum required: {min_required} bytes"
        )


class CompressionError(SplitZipError):
    """Error during compression."""


class IntegrityError(SplitZipError):
    """CRC mismatch or corrupted data."""

    def __init__(self, expected: int, actual: int, filename: str) -> None:
        self.expected = expected
        self.actual = actual
        self.filename = filename
        super().__init__(
            f"CRC32 mismatch for '{filename}': expected {expected:08x}, got {actual:08x}"
        )


class FileNotFoundInArchiveError(SplitZipError):
    """Requested file not found in archive."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        super().__init__(f"File not found in archive: '{filename}'")
