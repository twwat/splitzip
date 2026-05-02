"""Tests for volume boundary behavior."""

import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pytest

from splitzip import SplitZipWriter

HAS_7Z = subprocess.run(["which", "7z"], capture_output=True).returncode == 0


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

    def test_central_directory_folds_into_last_data_volume(self, temp_dir):
        """When the last data volume has room, the central directory folds in.

        Regression: a 1368 MiB file split at 1024 MiB used to produce
        three volumes (.z01, .z02, .zip) where the .zip held only the
        central directory and EOCD record (~80 bytes). The orphan .zip
        was wasteful: .z02 ended well below the split size, so the CD
        could have lived there.

        Now the writer pre-computes the CD + EOCD size and passes it to
        VolumeManager.start_final_volume; when it fits in the last data
        volume's free space, that volume is renamed to .zip in place
        rather than spawning a separate metadata-only file.
        """
        archive_path = temp_dir / "output" / "fold.zip"
        archive_path.parent.mkdir()

        # 110 KB file, 96 KiB split → just over one volume. Without the
        # fold we'd get three files: .z01 (full), .z02 (~12 KB data),
        # .zip (~80 B CD/EOCD). With the fold the last data volume
        # absorbs the CD and we get exactly two files.
        data = os.urandom(110_000)
        with SplitZipWriter(archive_path, split_size="96KiB") as zf:
            zf.writestr("video.bin", data)

        assert [p.name for p in zf.volume_paths] == ["fold.z01", "fold.zip"], (
            f"Expected fold to produce 2 volumes; got "
            f"{[p.name for p in zf.volume_paths]}"
        )

        # The renamed .zip carries real file data plus metadata, not
        # ~80 bytes of CD-only.
        assert zf.volume_paths[-1].stat().st_size > 1024

        # Verify content round-trips when extracted by a real split-aware
        # tool. zipfile in stdlib doesn't handle multi-volume archives.
        if HAS_7Z:
            extract_dir = temp_dir / "fold_extracted"
            extract_dir.mkdir()
            result = subprocess.run(
                ["7z", "x", str(archive_path), f"-o{extract_dir}", "-y"],
                capture_output=True,
            )
            assert result.returncode == 0, f"7z extraction failed: {result.stderr.decode()}"
            assert (extract_dir / "video.bin").read_bytes() == data

    def test_central_directory_does_not_fold_when_no_room(self, temp_dir):
        """When the last data volume is full, a separate .zip is still required.

        Sanity check that the fold optimization only triggers when there
        is space; otherwise the writer must fall back to opening a new
        final volume to host the central directory.
        """
        archive_path = temp_dir / "output" / "nofold.zip"
        archive_path.parent.mkdir()

        # Pick data + filename so the last data volume ends within ~50 B
        # of the split boundary — too tight for CD (~67 B for one entry)
        # plus EOCD (22 B) to fit. local file header for "x.bin" = 35 B.
        split = 64 * 1024
        target_total = 3 * split + (split - 60)  # leave only 60 B free
        data = os.urandom(target_total - 35)

        with SplitZipWriter(archive_path, split_size="64KiB") as zf:
            zf.writestr("x.bin", data)

        # Fold must NOT trigger: final .zip is a fresh metadata-only file
        # whose size is dominated by the CD entry (~67 B) + EOCD (22 B).
        assert zf.volume_paths[-1].name == "nofold.zip"
        assert zf.volume_paths[-1].stat().st_size < 1024, (
            f"Expected metadata-only final volume; got "
            f"{zf.volume_paths[-1].stat().st_size} B (fold should have been skipped)"
        )

        # Round-trip integrity still holds across the multi-volume set.
        if HAS_7Z:
            extract_dir = temp_dir / "nofold_extracted"
            extract_dir.mkdir()
            result = subprocess.run(
                ["7z", "x", str(archive_path), f"-o{extract_dir}", "-y"],
                capture_output=True,
            )
            assert result.returncode == 0, f"7z extraction failed: {result.stderr.decode()}"
            assert (extract_dir / "x.bin").read_bytes() == data
