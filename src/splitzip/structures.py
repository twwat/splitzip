"""ZIP file format data structures.

Based on PKWARE's APPNOTE.TXT specification.
https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import ClassVar


class Compression(IntEnum):
    """Compression methods supported by ZIP."""

    STORED = 0  # No compression
    DEFLATED = 8  # DEFLATE compression


class GeneralPurposeFlag(IntEnum):
    """General purpose bit flags."""

    ENCRYPTED = 1 << 0
    # Bits 1-2: compression options (for DEFLATE: 0=normal, 1=max, 2=fast, 3=super fast)
    DATA_DESCRIPTOR = 1 << 3  # CRC and sizes in data descriptor after file data
    ENHANCED_DEFLATE = 1 << 4
    COMPRESSED_PATCHED = 1 << 5
    STRONG_ENCRYPTION = 1 << 6
    UTF8 = 1 << 11  # Filename and comment are UTF-8 encoded
    ENHANCED_COMPRESSION = 1 << 12
    MASKED_HEADERS = 1 << 13


# Signatures
LOCAL_FILE_HEADER_SIG = 0x04034B50
CENTRAL_DIR_HEADER_SIG = 0x02014B50
END_OF_CENTRAL_DIR_SIG = 0x06054B50
DATA_DESCRIPTOR_SIG = 0x08074B50
SPLIT_ARCHIVE_SIG = 0x08074B50  # Same as data descriptor


@dataclass
class LocalFileHeader:
    """Local file header structure (precedes each file's data)."""

    SIGNATURE: ClassVar[int] = LOCAL_FILE_HEADER_SIG
    STRUCT_FORMAT: ClassVar[str] = "<IHHHHHIIIHH"
    FIXED_SIZE: ClassVar[int] = 30  # Size without filename and extra

    version_needed: int = 20  # 2.0 for DEFLATE
    flags: int = 0
    compression: int = Compression.DEFLATED
    mod_time: int = 0
    mod_date: int = 0
    crc32: int = 0
    compressed_size: int = 0
    uncompressed_size: int = 0
    filename: bytes = b""
    extra: bytes = b""

    def to_bytes(self) -> bytes:
        """Serialize to bytes."""
        header = struct.pack(
            self.STRUCT_FORMAT,
            self.SIGNATURE,
            self.version_needed,
            self.flags,
            self.compression,
            self.mod_time,
            self.mod_date,
            self.crc32,
            self.compressed_size,
            self.uncompressed_size,
            len(self.filename),
            len(self.extra),
        )
        return header + self.filename + self.extra

    @classmethod
    def from_bytes(cls, data: bytes) -> "LocalFileHeader":
        """Deserialize from bytes."""
        if len(data) < cls.FIXED_SIZE:
            raise ValueError(f"Data too short for LocalFileHeader: {len(data)} < {cls.FIXED_SIZE}")

        (
            sig,
            version_needed,
            flags,
            compression,
            mod_time,
            mod_date,
            crc32,
            compressed_size,
            uncompressed_size,
            filename_len,
            extra_len,
        ) = struct.unpack(cls.STRUCT_FORMAT, data[: cls.FIXED_SIZE])

        if sig != cls.SIGNATURE:
            raise ValueError(f"Invalid local file header signature: {sig:#010x}")

        filename = data[cls.FIXED_SIZE : cls.FIXED_SIZE + filename_len]
        extra = data[cls.FIXED_SIZE + filename_len : cls.FIXED_SIZE + filename_len + extra_len]

        return cls(
            version_needed=version_needed,
            flags=flags,
            compression=compression,
            mod_time=mod_time,
            mod_date=mod_date,
            crc32=crc32,
            compressed_size=compressed_size,
            uncompressed_size=uncompressed_size,
            filename=filename,
            extra=extra,
        )

    @property
    def total_size(self) -> int:
        """Total size of header including variable fields."""
        return self.FIXED_SIZE + len(self.filename) + len(self.extra)


@dataclass
class DataDescriptor:
    """Optional data descriptor (follows file data when sizes unknown upfront)."""

    SIGNATURE: ClassVar[int] = DATA_DESCRIPTOR_SIG
    STRUCT_FORMAT_WITH_SIG: ClassVar[str] = "<IIII"
    STRUCT_FORMAT_NO_SIG: ClassVar[str] = "<III"
    SIZE_WITH_SIG: ClassVar[int] = 16
    SIZE_NO_SIG: ClassVar[int] = 12

    crc32: int = 0
    compressed_size: int = 0
    uncompressed_size: int = 0

    def to_bytes(self, include_signature: bool = True) -> bytes:
        """Serialize to bytes."""
        if include_signature:
            return struct.pack(
                self.STRUCT_FORMAT_WITH_SIG,
                self.SIGNATURE,
                self.crc32,
                self.compressed_size,
                self.uncompressed_size,
            )
        else:
            return struct.pack(
                self.STRUCT_FORMAT_NO_SIG,
                self.crc32,
                self.compressed_size,
                self.uncompressed_size,
            )


@dataclass
class CentralDirectoryHeader:
    """Central directory file header."""

    SIGNATURE: ClassVar[int] = CENTRAL_DIR_HEADER_SIG
    STRUCT_FORMAT: ClassVar[str] = "<IHHHHHHIIIHHHHHII"
    FIXED_SIZE: ClassVar[int] = 46

    version_made_by: int = 20  # 2.0, MS-DOS compatible
    version_needed: int = 20
    flags: int = 0
    compression: int = Compression.DEFLATED
    mod_time: int = 0
    mod_date: int = 0
    crc32: int = 0
    compressed_size: int = 0
    uncompressed_size: int = 0
    disk_number_start: int = 0  # Disk where file starts
    internal_attr: int = 0
    external_attr: int = 0
    local_header_offset: int = 0  # Offset of local header on starting disk
    filename: bytes = b""
    extra: bytes = b""
    comment: bytes = b""

    def to_bytes(self) -> bytes:
        """Serialize to bytes."""
        header = struct.pack(
            self.STRUCT_FORMAT,
            self.SIGNATURE,
            self.version_made_by,
            self.version_needed,
            self.flags,
            self.compression,
            self.mod_time,
            self.mod_date,
            self.crc32,
            self.compressed_size,
            self.uncompressed_size,
            len(self.filename),
            len(self.extra),
            len(self.comment),
            self.disk_number_start,
            self.internal_attr,
            self.external_attr,
            self.local_header_offset,
        )
        return header + self.filename + self.extra + self.comment

    @classmethod
    def from_bytes(cls, data: bytes) -> "CentralDirectoryHeader":
        """Deserialize from bytes."""
        if len(data) < cls.FIXED_SIZE:
            raise ValueError(
                f"Data too short for CentralDirectoryHeader: {len(data)} < {cls.FIXED_SIZE}"
            )

        (
            sig,
            version_made_by,
            version_needed,
            flags,
            compression,
            mod_time,
            mod_date,
            crc32,
            compressed_size,
            uncompressed_size,
            filename_len,
            extra_len,
            comment_len,
            disk_number_start,
            internal_attr,
            external_attr,
            local_header_offset,
        ) = struct.unpack(cls.STRUCT_FORMAT, data[: cls.FIXED_SIZE])

        if sig != cls.SIGNATURE:
            raise ValueError(f"Invalid central directory header signature: {sig:#010x}")

        offset = cls.FIXED_SIZE
        filename = data[offset : offset + filename_len]
        offset += filename_len
        extra = data[offset : offset + extra_len]
        offset += extra_len
        comment = data[offset : offset + comment_len]

        return cls(
            version_made_by=version_made_by,
            version_needed=version_needed,
            flags=flags,
            compression=compression,
            mod_time=mod_time,
            mod_date=mod_date,
            crc32=crc32,
            compressed_size=compressed_size,
            uncompressed_size=uncompressed_size,
            disk_number_start=disk_number_start,
            internal_attr=internal_attr,
            external_attr=external_attr,
            local_header_offset=local_header_offset,
            filename=filename,
            extra=extra,
            comment=comment,
        )

    @property
    def total_size(self) -> int:
        """Total size of header including variable fields."""
        return self.FIXED_SIZE + len(self.filename) + len(self.extra) + len(self.comment)


@dataclass
class EndOfCentralDirectory:
    """End of central directory record."""

    SIGNATURE: ClassVar[int] = END_OF_CENTRAL_DIR_SIG
    STRUCT_FORMAT: ClassVar[str] = "<IHHHHIIH"
    FIXED_SIZE: ClassVar[int] = 22

    disk_number: int = 0  # Number of this disk
    disk_with_cd_start: int = 0  # Disk where central directory starts
    entries_on_disk: int = 0  # Entries in central directory on this disk
    total_entries: int = 0  # Total entries in central directory
    cd_size: int = 0  # Size of central directory
    cd_offset: int = 0  # Offset of central directory on starting disk
    comment: bytes = b""

    def to_bytes(self) -> bytes:
        """Serialize to bytes."""
        return struct.pack(
            self.STRUCT_FORMAT,
            self.SIGNATURE,
            self.disk_number,
            self.disk_with_cd_start,
            self.entries_on_disk,
            self.total_entries,
            self.cd_size,
            self.cd_offset,
            len(self.comment),
        ) + self.comment

    @classmethod
    def from_bytes(cls, data: bytes) -> "EndOfCentralDirectory":
        """Deserialize from bytes."""
        if len(data) < cls.FIXED_SIZE:
            raise ValueError(
                f"Data too short for EndOfCentralDirectory: {len(data)} < {cls.FIXED_SIZE}"
            )

        (
            sig,
            disk_number,
            disk_with_cd_start,
            entries_on_disk,
            total_entries,
            cd_size,
            cd_offset,
            comment_len,
        ) = struct.unpack(cls.STRUCT_FORMAT, data[: cls.FIXED_SIZE])

        if sig != cls.SIGNATURE:
            raise ValueError(f"Invalid end of central directory signature: {sig:#010x}")

        comment = data[cls.FIXED_SIZE : cls.FIXED_SIZE + comment_len]

        return cls(
            disk_number=disk_number,
            disk_with_cd_start=disk_with_cd_start,
            entries_on_disk=entries_on_disk,
            total_entries=total_entries,
            cd_size=cd_size,
            cd_offset=cd_offset,
            comment=comment,
        )

    @property
    def total_size(self) -> int:
        """Total size of record including comment."""
        return self.FIXED_SIZE + len(self.comment)


@dataclass
class ZipEntry:
    """Internal tracking of an entry being written."""

    filename: str
    arcname: bytes
    compression: int
    mod_time: int
    mod_date: int
    crc32: int = 0
    compressed_size: int = 0
    uncompressed_size: int = 0
    disk_number_start: int = 0
    local_header_offset: int = 0
    external_attr: int = 0
    extra: bytes = b""
    comment: bytes = b""

    def to_central_directory_header(self) -> CentralDirectoryHeader:
        """Convert to a CentralDirectoryHeader."""
        return CentralDirectoryHeader(
            version_made_by=20,
            version_needed=20,
            flags=GeneralPurposeFlag.UTF8,
            compression=self.compression,
            mod_time=self.mod_time,
            mod_date=self.mod_date,
            crc32=self.crc32,
            compressed_size=self.compressed_size,
            uncompressed_size=self.uncompressed_size,
            disk_number_start=self.disk_number_start,
            internal_attr=0,
            external_attr=self.external_attr,
            local_header_offset=self.local_header_offset,
            filename=self.arcname,
            extra=self.extra,
            comment=self.comment,
        )

    def _is_utf8(self) -> bool:
        """Check if filename requires UTF-8 flag."""
        try:
            self.arcname.decode("ascii")
            return False
        except UnicodeDecodeError:
            return True
