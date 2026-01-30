"""Tests for utility functions."""

import pytest

from splitzip.utils import dos_datetime, format_size, parse_size, sanitize_arcname


class TestParseSize:
    """Tests for parse_size function."""

    def test_integer_passthrough(self):
        assert parse_size(1024) == 1024
        assert parse_size(0) == 0

    def test_decimal_units(self):
        assert parse_size("100KB") == 100_000
        assert parse_size("100MB") == 100_000_000
        assert parse_size("1GB") == 1_000_000_000
        assert parse_size("1TB") == 1_000_000_000_000

    def test_binary_units(self):
        assert parse_size("100KiB") == 100 * 1024
        assert parse_size("100MiB") == 100 * 1024 * 1024
        assert parse_size("1GiB") == 1024 * 1024 * 1024
        assert parse_size("1TiB") == 1024**4

    def test_case_insensitive(self):
        assert parse_size("100mb") == 100_000_000
        assert parse_size("100MB") == 100_000_000
        assert parse_size("100Mb") == 100_000_000

    def test_float_values(self):
        assert parse_size("4.7GB") == 4_700_000_000
        assert parse_size("1.5MiB") == int(1.5 * 1024 * 1024)

    def test_bytes_unit(self):
        assert parse_size("100B") == 100
        assert parse_size("100bytes") == 100
        assert parse_size("100byte") == 100

    def test_no_unit_assumes_bytes(self):
        assert parse_size("1024") == 1024

    def test_whitespace_handling(self):
        assert parse_size("  100 MB  ") == 100_000_000
        assert parse_size("100 MB") == 100_000_000

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid size format"):
            parse_size("not a size")
        with pytest.raises(ValueError, match="Invalid size format"):
            parse_size("")
        with pytest.raises(ValueError, match="Invalid size format"):
            parse_size("MB100")


class TestFormatSize:
    """Tests for format_size function."""

    def test_decimal_format(self):
        assert format_size(0) == "0 B"
        assert format_size(500) == "500 B"
        assert format_size(1500) == "1.50 KB"
        assert format_size(1_500_000) == "1.50 MB"
        assert format_size(1_500_000_000) == "1.50 GB"

    def test_binary_format(self):
        assert format_size(1024, binary=True) == "1 KiB"
        assert format_size(1536, binary=True) == "1.50 KiB"
        assert format_size(1024 * 1024, binary=True) == "1 MiB"


class TestDosDatetime:
    """Tests for DOS datetime conversion."""

    def test_known_timestamp(self):
        # 2024-01-15 10:30:45
        import time
        ts = time.mktime((2024, 1, 15, 10, 30, 45, 0, 0, -1))
        dos_time, dos_date = dos_datetime(ts)

        # Decode and verify
        seconds = (dos_time & 0x1F) * 2
        minutes = (dos_time >> 5) & 0x3F
        hours = (dos_time >> 11) & 0x1F

        day = dos_date & 0x1F
        month = (dos_date >> 5) & 0x0F
        year = ((dos_date >> 9) & 0x7F) + 1980

        assert hours == 10
        assert minutes == 30
        assert seconds == 44  # Rounded down to even
        assert day == 15
        assert month == 1
        assert year == 2024


class TestSanitizeArcname:
    """Tests for archive name sanitization."""

    def test_forward_slashes(self):
        assert sanitize_arcname("dir/file.txt") == "dir/file.txt"

    def test_backslashes_converted(self):
        assert sanitize_arcname("dir\\file.txt") == "dir/file.txt"
        assert sanitize_arcname("dir\\sub\\file.txt") == "dir/sub/file.txt"

    def test_leading_slashes_removed(self):
        assert sanitize_arcname("/dir/file.txt") == "dir/file.txt"
        assert sanitize_arcname("///dir/file.txt") == "dir/file.txt"

    def test_drive_letter_removed(self):
        assert sanitize_arcname("C:/Users/file.txt") == "Users/file.txt"
        assert sanitize_arcname("D:\\Data\\file.txt") == "Data/file.txt"

    def test_double_slashes_normalized(self):
        assert sanitize_arcname("dir//sub//file.txt") == "dir/sub/file.txt"
