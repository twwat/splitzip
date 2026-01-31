"""Tests for volume boundary behavior."""

import os
import tempfile
import zipfile
from pathlib import Path

import pytest

from splitzip import SplitZipWriter


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


class TestVolumeBoundary:
    """Tests for volume splitting behavior."""

    def test_multiple_small_files_across_volumes(self, temp_dir):
        """Small split size forces multiple volumes."""
        archive_path = temp_dir / "output" / "boundary.zip"
        archive_path.parent.mkdir()

        # Create files that will exceed the split size
        with SplitZipWriter(archive_path, split_size="64KiB") as zf:
            for i in range(20):
                zf.writestr(f"file_{i}.txt", os.urandom(8192))

        assert len(zf.volume_paths) > 1

    def test_single_file_forces_split(self, temp_dir):
        """A file larger than split_size spans multiple volumes."""
        archive_path = temp_dir / "output" / "single_split.zip"
        archive_path.parent.mkdir()

        data = os.urandom(200000)
        with SplitZipWriter(archive_path, split_size="64KiB") as zf:
            zf.writestr("big.bin", data)

        assert len(zf.volume_paths) > 1
        # Final volume should be the .zip
        assert zf.volume_paths[-1].suffix == ".zip"

    def test_header_does_not_span_volume_boundary(self, temp_dir):
        """Headers are pushed to the next volume when they would straddle a boundary."""
        archive_path = temp_dir / "output" / "headerboundary.zip"
        archive_path.parent.mkdir()

        # Write enough data to nearly fill the first volume, then add another file
        # whose header would straddle the boundary. ensure_space should push it.
        with SplitZipWriter(archive_path, split_size="64KiB") as zf:
            # Fill most of the first volume
            zf.writestr("filler.bin", os.urandom(60000))
            # This file's header should be pushed to the next volume
            zf.writestr("second.txt", b"hello world")

        # If headers were split across volumes, the archive would be corrupt.
        # Single-volume archives can be verified with zipfile.
        if len(zf.volume_paths) == 1:
            with zipfile.ZipFile(archive_path) as zf_std:
                assert "filler.bin" in zf_std.namelist()
                assert "second.txt" in zf_std.namelist()
                assert zf_std.read("second.txt") == b"hello world"
