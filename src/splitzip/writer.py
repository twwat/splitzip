"""Split ZIP archive writer."""

from __future__ import annotations

import warnings
import zlib
from pathlib import Path
from typing import BinaryIO, Callable

from .exceptions import SplitZipError
from .structures import (
    Compression,
    EndOfCentralDirectory,
    GeneralPurposeFlag,
    LocalFileHeader,
    ZipEntry,
)
from .utils import dos_datetime, parse_size, sanitize_arcname
from .volume import VolumeManager

# Default chunk size for reading files
CHUNK_SIZE = 64 * 1024  # 64 KB

# ZIP32 limits
_MAX_32 = 0xFFFFFFFF  # 4,294,967,295 bytes
_MAX_ENTRIES = 0xFFFF  # 65,535 entries


class SplitZipWriter:
    """
    Create split ZIP archives compatible with standard tools.

    Split archives are created with the naming convention:
        archive.z01, archive.z02, ..., archive.zip

    The final .zip file contains the central directory.

    Example:
        >>> with SplitZipWriter("backup.zip", split_size="100MB") as zf:
        ...     zf.write("file1.txt")
        ...     zf.write("data/", recursive=True)
        ...     zf.writestr("hello.txt", b"Hello, world!")

    Attributes:
        split_size: Maximum size of each volume in bytes.
        compression: Default compression method.
        compresslevel: Compression level (1-9 for DEFLATE).
    """

    def __init__(
        self,
        path: str | Path,
        split_size: int | str,
        compression: int = Compression.DEFLATED,
        compresslevel: int = 6,
        on_volume: Callable[[int, Path], None] | None = None,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> None:
        """
        Initialize a split ZIP writer.

        Args:
            path: Path for the final .zip file.
            split_size: Maximum size per volume. Can be:
                - Integer: bytes
                - String: human-readable (e.g., "100MB", "700MiB", "4.7GB")
            compression: Compression method (Compression.STORED or Compression.DEFLATED).
            compresslevel: DEFLATE compression level 1-9 (default 6).
            on_volume: Callback when a volume is created. Receives (volume_number, path).
            on_progress: Callback for progress updates.
                Receives (filename, bytes_done, total_bytes).
        """
        if compression not in (Compression.STORED, Compression.DEFLATED):
            raise ValueError(
                f"Unsupported compression method: {compression}. "
                "Use Compression.STORED or Compression.DEFLATED."
            )

        self.path = Path(path)
        self.split_size = parse_size(split_size)
        self.compression = compression
        self.compresslevel = compresslevel
        self.on_progress = on_progress

        self._volume_mgr = VolumeManager(
            self.path,
            self.split_size,
            on_volume_created=on_volume,
        )
        self._entries: list[ZipEntry] = []
        self._closed = False
        self._closing = False

    @property
    def volume_paths(self) -> list[Path]:
        """List of all volume paths created so far."""
        return self._volume_mgr.volume_paths

    def write(
        self,
        path: str | Path,
        arcname: str | None = None,
        recursive: bool = True,
        compression: int | None = None,
        compresslevel: int | None = None,
    ) -> None:
        """
        Add a file or directory to the archive.

        Args:
            path: Path to file or directory to add.
            arcname: Name in archive. If None, uses the original path.
            recursive: If True and path is a directory, add contents recursively.
            compression: Override compression method for this entry.
            compresslevel: Override compression level for this entry.

        Raises:
            FileNotFoundError: If path does not exist.
            IsADirectoryError: If path is a directory and recursive=False.
        """
        self._check_closed()
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"No such file or directory: '{path}'")

        if path.is_symlink():
            warnings.warn(f"Skipping symlink: '{path}'", stacklevel=2)
            return

        if path.is_dir():
            self._write_directory(path, arcname, recursive, compression, compresslevel)
        else:
            self._write_file(path, arcname, compression, compresslevel)

    def _write_directory(
        self,
        path: Path,
        arcname: str | None,
        recursive: bool,
        compression: int | None,
        compresslevel: int | None,
    ) -> None:
        """Add a directory to the archive."""
        base_arcname = arcname if arcname else path.name
        base_arcname = sanitize_arcname(base_arcname)

        # Add the directory entry itself
        dir_arcname = base_arcname.rstrip("/") + "/"
        self._write_directory_entry(dir_arcname, path)

        if not recursive:
            return

        # Add contents
        for item in sorted(path.iterdir()):
            if item.is_symlink():
                warnings.warn(f"Skipping symlink: '{item}'", stacklevel=2)
                continue
            item_arcname = f"{base_arcname.rstrip('/')}/{item.name}"
            if item.is_dir():
                self._write_directory(item, item_arcname, True, compression, compresslevel)
            else:
                self._write_file(item, item_arcname, compression, compresslevel)

    def _write_directory_entry(self, arcname: str, path: Path) -> None:
        """Write a directory entry (no data, just metadata)."""
        self._check_entry_limit()
        arcname_bytes = arcname.encode("utf-8")
        stat = path.stat()
        mod_time, mod_date = dos_datetime(stat.st_mtime)

        # Directory entry uses STORED, no data
        header = LocalFileHeader(
            version_needed=20,
            flags=GeneralPurposeFlag.UTF8,
            compression=Compression.STORED,
            mod_time=mod_time,
            mod_date=mod_date,
            crc32=0,
            compressed_size=0,
            uncompressed_size=0,
            filename=arcname_bytes,
        )
        header_bytes = header.to_bytes()

        self._volume_mgr.ensure_space(len(header_bytes))
        disk_start = self._volume_mgr.current_volume
        offset = self._volume_mgr.current_offset

        self._volume_mgr.write(header_bytes)

        # Track entry for central directory
        # External attr: directory flag (bit 4) + Unix permissions
        external_attr = (0o40755 << 16) | 0x10  # Unix dir + DOS dir flag
        entry = ZipEntry(
            filename=arcname,
            arcname=arcname_bytes,
            compression=Compression.STORED,
            mod_time=mod_time,
            mod_date=mod_date,
            crc32=0,
            compressed_size=0,
            uncompressed_size=0,
            disk_number_start=disk_start,
            local_header_offset=offset,
            external_attr=external_attr,
        )
        self._entries.append(entry)

    def _write_file(
        self,
        path: Path,
        arcname: str | None,
        compression: int | None,
        compresslevel: int | None,
    ) -> None:
        """Write a single file to the archive."""
        if path.is_symlink():
            warnings.warn(f"Skipping symlink: '{path}'", stacklevel=2)
            return

        self._check_entry_limit()

        arcname = arcname if arcname else path.name
        arcname = sanitize_arcname(arcname)
        arcname_bytes = arcname.encode("utf-8")

        stat = path.stat()
        mod_time, mod_date = dos_datetime(stat.st_mtime)
        file_size = stat.st_size

        if file_size > _MAX_32:
            raise SplitZipError(
                f"File '{path}' is {file_size} bytes; exceeds 4GB ZIP32 limit. "
                "ZIP64 not supported."
            )

        comp = compression if compression is not None else self.compression
        level = compresslevel if compresslevel is not None else self.compresslevel

        # Write header with placeholder values (will patch after data is written)
        flags = GeneralPurposeFlag.UTF8
        header = LocalFileHeader(
            version_needed=20,
            flags=flags,
            compression=comp,
            mod_time=mod_time,
            mod_date=mod_date,
            crc32=0,  # Will be updated
            compressed_size=0,  # Will be updated
            uncompressed_size=file_size,
            filename=arcname_bytes,
        )
        header_bytes = header.to_bytes()

        # Ensure header doesn't split across volumes (patching requires single volume)
        self._volume_mgr.ensure_space(len(header_bytes))
        disk_start = self._volume_mgr.current_volume
        header_offset = self._volume_mgr.current_offset
        self._volume_mgr.write(header_bytes)

        # Compress and write data
        crc, compressed_size, uncompressed_size = self._write_file_data(
            path, comp, level, file_size
        )

        # Patch the header with actual values
        self._patch_local_header(
            disk_start, header_offset, crc, compressed_size, uncompressed_size
        )

        # External attr: Unix permissions
        external_attr = (stat.st_mode & 0o777) << 16

        # Track entry
        entry = ZipEntry(
            filename=arcname,
            arcname=arcname_bytes,
            compression=comp,
            mod_time=mod_time,
            mod_date=mod_date,
            crc32=crc,
            compressed_size=compressed_size,
            uncompressed_size=uncompressed_size,
            disk_number_start=disk_start,
            local_header_offset=header_offset,
            external_attr=external_attr,
        )
        self._entries.append(entry)

    def _write_file_data(
        self,
        path: Path,
        compression: int,
        compresslevel: int,
        total_size: int,
    ) -> tuple[int, int, int]:
        """
        Compress and write file data.

        Returns:
            Tuple of (crc32, compressed_size, uncompressed_size).
        """
        crc = 0
        uncompressed_size = 0
        compressed_size = 0

        if compression == Compression.DEFLATED:
            compressor = zlib.compressobj(compresslevel, zlib.DEFLATED, -zlib.MAX_WBITS)
        else:
            compressor = None

        with open(path, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break

                crc = zlib.crc32(chunk, crc)
                uncompressed_size += len(chunk)

                if compressor:
                    compressed_chunk = compressor.compress(chunk)
                    if compressed_chunk:
                        self._volume_mgr.write(compressed_chunk)
                        compressed_size += len(compressed_chunk)
                else:
                    self._volume_mgr.write(chunk)
                    compressed_size += len(chunk)

                if self.on_progress:
                    self.on_progress(str(path), uncompressed_size, total_size)

            # Flush compressor
            if compressor:
                remaining = compressor.flush()
                if remaining:
                    self._volume_mgr.write(remaining)
                    compressed_size += len(remaining)

        if compressed_size > _MAX_32 or uncompressed_size > _MAX_32:
            raise SplitZipError(
                f"File data exceeds 4GB ZIP32 limit (compressed={compressed_size}, "
                f"uncompressed={uncompressed_size}). ZIP64 not supported."
            )

        return crc & 0xFFFFFFFF, compressed_size, uncompressed_size

    def _patch_local_header(
        self,
        disk: int,
        offset: int,
        crc: int,
        compressed_size: int,
        uncompressed_size: int,
    ) -> None:
        """Patch the local file header with actual CRC and sizes."""
        import struct

        # CRC, compressed size, uncompressed size are at offset 14 in the header
        patch_offset = offset + 14
        patch_data = struct.pack("<III", crc, compressed_size, uncompressed_size)
        self._volume_mgr.write_at_offset(patch_data, disk, patch_offset)

    def writestr(
        self,
        arcname: str,
        data: bytes | str,
        compression: int | None = None,
        compresslevel: int | None = None,
    ) -> None:
        """
        Write data directly to the archive with a given filename.

        Args:
            arcname: Name of file in archive.
            data: File contents (bytes or str).
            compression: Override compression method.
            compresslevel: Override compression level.
        """
        self._check_closed()
        self._check_entry_limit()

        if isinstance(data, str):
            data = data.encode("utf-8")

        if len(data) > _MAX_32:
            raise SplitZipError(
                f"Data size {len(data)} bytes exceeds 4GB ZIP32 limit. ZIP64 not supported."
            )

        arcname = sanitize_arcname(arcname)
        arcname_bytes = arcname.encode("utf-8")
        mod_time, mod_date = dos_datetime()

        comp = compression if compression is not None else self.compression
        level = compresslevel if compresslevel is not None else self.compresslevel

        crc = zlib.crc32(data) & 0xFFFFFFFF
        uncompressed_size = len(data)

        if comp == Compression.DEFLATED and len(data) > CHUNK_SIZE:
            # Stream compress large buffers to avoid doubling memory
            header = LocalFileHeader(
                version_needed=20,
                flags=GeneralPurposeFlag.UTF8,
                compression=comp,
                mod_time=mod_time,
                mod_date=mod_date,
                crc32=crc,
                compressed_size=0,  # Will be patched
                uncompressed_size=uncompressed_size,
                filename=arcname_bytes,
            )
            header_bytes = header.to_bytes()

            self._volume_mgr.ensure_space(len(header_bytes))
            disk_start = self._volume_mgr.current_volume
            header_offset = self._volume_mgr.current_offset
            self._volume_mgr.write(header_bytes)

            compressor = zlib.compressobj(level, zlib.DEFLATED, -zlib.MAX_WBITS)
            compressed_size = 0
            for i in range(0, len(data), CHUNK_SIZE):
                chunk = compressor.compress(data[i : i + CHUNK_SIZE])
                if chunk:
                    self._volume_mgr.write(chunk)
                    compressed_size += len(chunk)
            remaining = compressor.flush()
            if remaining:
                self._volume_mgr.write(remaining)
                compressed_size += len(remaining)

            self._patch_local_header(
                disk_start, header_offset, crc, compressed_size, uncompressed_size
            )
        else:
            # Small data or STORED: compress upfront
            if comp == Compression.DEFLATED:
                compressor = zlib.compressobj(level, zlib.DEFLATED, -zlib.MAX_WBITS)
                compressed = compressor.compress(data) + compressor.flush()
            else:
                compressed = data

            compressed_size = len(compressed)

            header = LocalFileHeader(
                version_needed=20,
                flags=GeneralPurposeFlag.UTF8,
                compression=comp,
                mod_time=mod_time,
                mod_date=mod_date,
                crc32=crc,
                compressed_size=compressed_size,
                uncompressed_size=uncompressed_size,
                filename=arcname_bytes,
            )
            header_bytes = header.to_bytes()

            self._volume_mgr.ensure_space(len(header_bytes))
            disk_start = self._volume_mgr.current_volume
            header_offset = self._volume_mgr.current_offset
            self._volume_mgr.write(header_bytes)
            self._volume_mgr.write(compressed)

        # Track entry
        entry = ZipEntry(
            filename=arcname,
            arcname=arcname_bytes,
            compression=comp,
            mod_time=mod_time,
            mod_date=mod_date,
            crc32=crc,
            compressed_size=compressed_size,
            uncompressed_size=uncompressed_size,
            disk_number_start=disk_start,
            local_header_offset=header_offset,
            external_attr=0o644 << 16,  # Default file permissions
        )
        self._entries.append(entry)

    def write_fileobj(
        self,
        fileobj: BinaryIO,
        arcname: str,
        size: int | None = None,
        compression: int | None = None,
        compresslevel: int | None = None,
    ) -> None:
        """
        Write data from a file-like object to the archive.

        Args:
            fileobj: File-like object with read() method.
            arcname: Name of file in archive.
            size: Total size if known (for progress callback).
            compression: Override compression method.
            compresslevel: Override compression level.
        """
        self._check_closed()
        self._check_entry_limit()

        arcname = sanitize_arcname(arcname)
        arcname_bytes = arcname.encode("utf-8")
        mod_time, mod_date = dos_datetime()

        comp = compression if compression is not None else self.compression
        level = compresslevel if compresslevel is not None else self.compresslevel

        # Write header with placeholders
        header = LocalFileHeader(
            version_needed=20,
            flags=GeneralPurposeFlag.UTF8,
            compression=comp,
            mod_time=mod_time,
            mod_date=mod_date,
            crc32=0,
            compressed_size=0,
            uncompressed_size=0,
            filename=arcname_bytes,
        )
        header_bytes = header.to_bytes()

        self._volume_mgr.ensure_space(len(header_bytes))
        disk_start = self._volume_mgr.current_volume
        header_offset = self._volume_mgr.current_offset
        self._volume_mgr.write(header_bytes)

        # Stream and compress
        crc = 0
        uncompressed_size = 0
        compressed_size = 0

        if comp == Compression.DEFLATED:
            compressor = zlib.compressobj(level, zlib.DEFLATED, -zlib.MAX_WBITS)
        else:
            compressor = None

        while True:
            chunk = fileobj.read(CHUNK_SIZE)
            if not chunk:
                break

            crc = zlib.crc32(chunk, crc)
            uncompressed_size += len(chunk)

            if compressor:
                compressed_chunk = compressor.compress(chunk)
                if compressed_chunk:
                    self._volume_mgr.write(compressed_chunk)
                    compressed_size += len(compressed_chunk)
            else:
                self._volume_mgr.write(chunk)
                compressed_size += len(chunk)

            if self.on_progress and size:
                self.on_progress(arcname, uncompressed_size, size)

        # Flush compressor
        if compressor:
            remaining = compressor.flush()
            if remaining:
                self._volume_mgr.write(remaining)
                compressed_size += len(remaining)

        crc = crc & 0xFFFFFFFF

        if compressed_size > _MAX_32 or uncompressed_size > _MAX_32:
            raise SplitZipError(
                f"Streamed data exceeds 4GB ZIP32 limit (compressed={compressed_size}, "
                f"uncompressed={uncompressed_size}). ZIP64 not supported."
            )

        # Patch header
        self._patch_local_header(disk_start, header_offset, crc, compressed_size, uncompressed_size)

        # Track entry
        entry = ZipEntry(
            filename=arcname,
            arcname=arcname_bytes,
            compression=comp,
            mod_time=mod_time,
            mod_date=mod_date,
            crc32=crc,
            compressed_size=compressed_size,
            uncompressed_size=uncompressed_size,
            disk_number_start=disk_start,
            local_header_offset=header_offset,
            external_attr=0o644 << 16,
        )
        self._entries.append(entry)

    def close(self) -> list[Path]:
        """
        Finalize and close the archive.

        Writes the central directory to the final volume and closes all files.

        Returns:
            List of paths to all volume files created.
        """
        if self._closed:
            return self._volume_mgr.volume_paths
        if self._closing:
            return self._volume_mgr.volume_paths
        self._closing = True

        # Start final volume for central directory
        self._volume_mgr.start_final_volume()

        # Write central directory
        cd_start_disk = self._volume_mgr.current_volume
        cd_start_offset = self._volume_mgr.current_offset
        cd_size = 0

        for entry in self._entries:
            cd_header = entry.to_central_directory_header()
            cd_bytes = cd_header.to_bytes()
            self._volume_mgr.write(cd_bytes)
            cd_size += len(cd_bytes)

        # Write end of central directory
        eocd = EndOfCentralDirectory(
            disk_number=self._volume_mgr.current_volume,
            disk_with_cd_start=cd_start_disk,
            entries_on_disk=len(self._entries),  # All entries on final disk for now
            total_entries=len(self._entries),
            cd_size=cd_size,
            cd_offset=cd_start_offset,
        )
        self._volume_mgr.write(eocd.to_bytes())

        self._closed = True
        return self._volume_mgr.close()

    def _check_closed(self) -> None:
        """Raise if writer is closed."""
        if self._closed:
            raise RuntimeError("SplitZipWriter is closed")

    def _check_entry_limit(self) -> None:
        """Raise if entry count exceeds ZIP32 limit."""
        if len(self._entries) >= _MAX_ENTRIES:
            raise SplitZipError(f"Entry count exceeds ZIP32 limit of {_MAX_ENTRIES}")

    def __enter__(self) -> SplitZipWriter:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if exc_type is not None:
            # Error path: release file handles without writing central directory
            self._closed = True
            self._volume_mgr.close()
        else:
            self.close()
