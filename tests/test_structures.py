"""Tests for ZIP data structures."""

import pytest

from splitzip.structures import (
    CentralDirectoryHeader,
    Compression,
    DataDescriptor,
    EndOfCentralDirectory,
    LocalFileHeader,
)


class TestLocalFileHeader:
    """Tests for LocalFileHeader."""

    def test_to_bytes_roundtrip(self):
        header = LocalFileHeader(
            version_needed=20,
            flags=0,
            compression=Compression.DEFLATED,
            mod_time=0x1234,
            mod_date=0x5678,
            crc32=0xDEADBEEF,
            compressed_size=1000,
            uncompressed_size=2000,
            filename=b"test.txt",
            extra=b"",
        )

        data = header.to_bytes()
        parsed = LocalFileHeader.from_bytes(data)

        assert parsed.version_needed == header.version_needed
        assert parsed.flags == header.flags
        assert parsed.compression == header.compression
        assert parsed.mod_time == header.mod_time
        assert parsed.mod_date == header.mod_date
        assert parsed.crc32 == header.crc32
        assert parsed.compressed_size == header.compressed_size
        assert parsed.uncompressed_size == header.uncompressed_size
        assert parsed.filename == header.filename
        assert parsed.extra == header.extra

    def test_signature(self):
        header = LocalFileHeader(filename=b"test.txt")
        data = header.to_bytes()
        # Check signature at start (little-endian)
        assert data[0:4] == b"\x50\x4b\x03\x04"

    def test_total_size(self):
        header = LocalFileHeader(filename=b"test.txt", extra=b"extra")
        assert header.total_size == 30 + 8 + 5  # fixed + filename + extra

    def test_invalid_signature(self):
        bad_data = b"\x00\x00\x00\x00" + b"\x00" * 26
        with pytest.raises(ValueError, match="Invalid local file header signature"):
            LocalFileHeader.from_bytes(bad_data)


class TestCentralDirectoryHeader:
    """Tests for CentralDirectoryHeader."""

    def test_to_bytes_roundtrip(self):
        header = CentralDirectoryHeader(
            version_made_by=20,
            version_needed=20,
            flags=0,
            compression=Compression.DEFLATED,
            mod_time=0x1234,
            mod_date=0x5678,
            crc32=0xDEADBEEF,
            compressed_size=1000,
            uncompressed_size=2000,
            disk_number_start=0,
            internal_attr=0,
            external_attr=0o644 << 16,
            local_header_offset=0,
            filename=b"test.txt",
            extra=b"",
            comment=b"A comment",
        )

        data = header.to_bytes()
        parsed = CentralDirectoryHeader.from_bytes(data)

        assert parsed.version_made_by == header.version_made_by
        assert parsed.version_needed == header.version_needed
        assert parsed.crc32 == header.crc32
        assert parsed.filename == header.filename
        assert parsed.comment == header.comment
        assert parsed.external_attr == header.external_attr

    def test_signature(self):
        header = CentralDirectoryHeader(filename=b"test.txt")
        data = header.to_bytes()
        # Check signature at start (little-endian)
        assert data[0:4] == b"\x50\x4b\x01\x02"


class TestEndOfCentralDirectory:
    """Tests for EndOfCentralDirectory."""

    def test_to_bytes_roundtrip(self):
        eocd = EndOfCentralDirectory(
            disk_number=5,
            disk_with_cd_start=3,
            entries_on_disk=10,
            total_entries=100,
            cd_size=5000,
            cd_offset=10000,
            comment=b"Archive comment",
        )

        data = eocd.to_bytes()
        parsed = EndOfCentralDirectory.from_bytes(data)

        assert parsed.disk_number == eocd.disk_number
        assert parsed.disk_with_cd_start == eocd.disk_with_cd_start
        assert parsed.entries_on_disk == eocd.entries_on_disk
        assert parsed.total_entries == eocd.total_entries
        assert parsed.cd_size == eocd.cd_size
        assert parsed.cd_offset == eocd.cd_offset
        assert parsed.comment == eocd.comment

    def test_signature(self):
        eocd = EndOfCentralDirectory()
        data = eocd.to_bytes()
        assert data[0:4] == b"\x50\x4b\x05\x06"


class TestDataDescriptor:
    """Tests for DataDescriptor."""

    def test_to_bytes_with_signature(self):
        dd = DataDescriptor(
            crc32=0xDEADBEEF,
            compressed_size=1000,
            uncompressed_size=2000,
        )

        data = dd.to_bytes(include_signature=True)
        assert len(data) == 16
        assert data[0:4] == b"\x50\x4b\x07\x08"

    def test_to_bytes_without_signature(self):
        dd = DataDescriptor(
            crc32=0xDEADBEEF,
            compressed_size=1000,
            uncompressed_size=2000,
        )

        data = dd.to_bytes(include_signature=False)
        assert len(data) == 12
