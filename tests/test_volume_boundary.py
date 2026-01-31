"""Tests for volume boundary behavior."""

import os
import tempfile
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
