"""Integration tests for SplitZipWriter."""

import io
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pytest

from splitzip import SplitZipWriter, create
from splitzip.structures import Compression


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def sample_files(temp_dir):
    """Create sample files for testing."""
    # Create some test files
    files = {}

    # Small text file
    small_file = temp_dir / "small.txt"
    small_file.write_text("Hello, World!")
    files["small"] = small_file

    # Medium file (100KB)
    medium_file = temp_dir / "medium.bin"
    medium_file.write_bytes(os.urandom(100 * 1024))
    files["medium"] = medium_file

    # Large file (1MB)
    large_file = temp_dir / "large.bin"
    large_file.write_bytes(os.urandom(1024 * 1024))
    files["large"] = large_file

    # Directory structure
    subdir = temp_dir / "subdir"
    subdir.mkdir()
    (subdir / "file1.txt").write_text("File 1 content")
    (subdir / "file2.txt").write_text("File 2 content")
    nested = subdir / "nested"
    nested.mkdir()
    (nested / "deep.txt").write_text("Deep file content")
    files["subdir"] = subdir

    return files


class TestSplitZipWriter:
    """Tests for SplitZipWriter."""

    def test_create_single_volume(self, temp_dir, sample_files):
        """Test creating archive that fits in one volume."""
        archive_path = temp_dir / "output" / "single.zip"
        archive_path.parent.mkdir()

        with SplitZipWriter(archive_path, split_size="10MB") as zf:
            zf.write(sample_files["small"])

        # Should only create the .zip file (no splits needed)
        assert archive_path.exists()
        assert len(zf.volume_paths) == 1

        # Verify with standard zipfile
        with zipfile.ZipFile(archive_path) as zf_std:
            names = zf_std.namelist()
            assert "small.txt" in names
            assert zf_std.read("small.txt") == b"Hello, World!"

    def test_create_multiple_volumes(self, temp_dir, sample_files):
        """Test creating archive split across multiple volumes."""
        archive_path = temp_dir / "output" / "multi.zip"
        archive_path.parent.mkdir()

        # Use a small split size to force multiple volumes
        with SplitZipWriter(archive_path, split_size="100KB") as zf:
            zf.write(sample_files["large"])

        # Should create multiple volumes
        assert len(zf.volume_paths) > 1
        assert archive_path.exists()

        # Check that .z01, .z02, etc. exist
        for i, path in enumerate(zf.volume_paths[:-1]):
            assert path.suffix == f".z{i+1:02d}"
        assert zf.volume_paths[-1].suffix == ".zip"

    def test_writestr(self, temp_dir):
        """Test writing string content directly."""
        archive_path = temp_dir / "writestr.zip"

        with SplitZipWriter(archive_path, split_size="1MB") as zf:
            zf.writestr("hello.txt", b"Hello from bytes!")
            zf.writestr("world.txt", "Hello from string!")

        with zipfile.ZipFile(archive_path) as zf_std:
            assert zf_std.read("hello.txt") == b"Hello from bytes!"
            assert zf_std.read("world.txt") == b"Hello from string!"

    def test_write_fileobj(self, temp_dir):
        """Test writing from file-like object."""
        archive_path = temp_dir / "fileobj.zip"
        data = b"Data from file object" * 1000

        with SplitZipWriter(archive_path, split_size="1MB") as zf:
            zf.write_fileobj(io.BytesIO(data), "fromobj.bin")

        with zipfile.ZipFile(archive_path) as zf_std:
            assert zf_std.read("fromobj.bin") == data

    def test_directory_recursive(self, temp_dir, sample_files):
        """Test adding directory recursively."""
        archive_path = temp_dir / "recursive.zip"

        with SplitZipWriter(archive_path, split_size="1MB") as zf:
            zf.write(sample_files["subdir"])

        with zipfile.ZipFile(archive_path) as zf_std:
            names = zf_std.namelist()
            assert "subdir/" in names
            assert "subdir/file1.txt" in names
            assert "subdir/file2.txt" in names
            assert "subdir/nested/" in names
            assert "subdir/nested/deep.txt" in names

    def test_custom_arcname(self, temp_dir, sample_files):
        """Test custom archive names."""
        archive_path = temp_dir / "arcname.zip"

        with SplitZipWriter(archive_path, split_size="1MB") as zf:
            zf.write(sample_files["small"], arcname="renamed/file.txt")

        with zipfile.ZipFile(archive_path) as zf_std:
            assert "renamed/file.txt" in zf_std.namelist()

    def test_stored_compression(self, temp_dir, sample_files):
        """Test STORED (no compression) mode."""
        archive_path = temp_dir / "stored.zip"

        with SplitZipWriter(archive_path, split_size="1MB", compression=Compression.STORED) as zf:
            zf.write(sample_files["small"])

        with zipfile.ZipFile(archive_path) as zf_std:
            info = zf_std.getinfo("small.txt")
            assert info.compress_type == zipfile.ZIP_STORED

    def test_on_volume_callback(self, temp_dir, sample_files):
        """Test volume creation callback."""
        archive_path = temp_dir / "callback.zip"
        volumes_created = []

        def on_volume(num, path):
            volumes_created.append((num, path))

        with SplitZipWriter(archive_path, split_size="100KB", on_volume=on_volume) as zf:
            zf.write(sample_files["large"])

        assert len(volumes_created) == len(zf.volume_paths)

    def test_progress_callback(self, temp_dir, sample_files):
        """Test progress callback."""
        archive_path = temp_dir / "progress.zip"
        progress_calls = []

        def on_progress(filename, done, total):
            progress_calls.append((filename, done, total))

        with SplitZipWriter(archive_path, split_size="1MB", on_progress=on_progress) as zf:
            zf.write(sample_files["medium"])

        assert len(progress_calls) > 0
        # Last call should have done == total (or close to it)
        last_call = progress_calls[-1]
        assert last_call[1] == last_call[2]


class TestCreateFunction:
    """Tests for the create() convenience function."""

    def test_create_simple(self, temp_dir, sample_files):
        """Test simple archive creation."""
        archive_path = temp_dir / "simple.zip"

        paths = create(
            str(archive_path),
            [str(sample_files["small"]), str(sample_files["medium"])],
            split_size="1MB",
        )

        assert len(paths) >= 1
        assert Path(paths[-1]).exists()

        with zipfile.ZipFile(paths[-1]) as zf:
            assert "small.txt" in zf.namelist()
            assert "medium.bin" in zf.namelist()


class TestCompatibility:
    """Tests for compatibility with standard tools."""

    @pytest.mark.skipif(
        subprocess.run(["which", "unzip"], capture_output=True).returncode != 0,
        reason="unzip not available",
    )
    def test_unzip_compatibility(self, temp_dir, sample_files):
        """Test that archives can be extracted with standard unzip."""
        archive_path = temp_dir / "compat.zip"
        extract_dir = temp_dir / "extracted"
        extract_dir.mkdir()

        # Create a single-volume archive for simpler testing
        with SplitZipWriter(archive_path, split_size="10MB") as zf:
            zf.write(sample_files["small"])
            zf.writestr("test.txt", "Test content")

        # Extract with unzip
        result = subprocess.run(
            ["unzip", "-o", str(archive_path), "-d", str(extract_dir)],
            capture_output=True,
        )

        assert result.returncode == 0
        assert (extract_dir / "small.txt").exists()
        assert (extract_dir / "test.txt").exists()
        assert (extract_dir / "small.txt").read_text() == "Hello, World!"
        assert (extract_dir / "test.txt").read_text() == "Test content"

    @pytest.mark.skipif(
        subprocess.run(["which", "7z"], capture_output=True).returncode != 0,
        reason="7z not available",
    )
    def test_7z_split_compatibility(self, temp_dir, sample_files):
        """Test that split archives can be extracted with 7-Zip."""
        archive_path = temp_dir / "split7z.zip"
        extract_dir = temp_dir / "extracted7z"
        extract_dir.mkdir()

        # Create a split archive
        with SplitZipWriter(archive_path, split_size="100KB") as zf:
            zf.write(sample_files["large"])

        # Should have multiple volumes
        assert len(zf.volume_paths) > 1

        # Extract with 7z (use the .zip file, it will find the .z01, .z02, etc.)
        result = subprocess.run(
            ["7z", "x", str(archive_path), f"-o{extract_dir}", "-y"],
            capture_output=True,
        )

        assert result.returncode == 0, f"7z failed: {result.stderr.decode()}"
        assert (extract_dir / "large.bin").exists()

        # Verify content
        original = sample_files["large"].read_bytes()
        extracted = (extract_dir / "large.bin").read_bytes()
        assert original == extracted


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_archive(self, temp_dir):
        """Test creating an empty archive."""
        archive_path = temp_dir / "empty.zip"

        with SplitZipWriter(archive_path, split_size="1MB") as zf:
            pass  # Don't add any files

        assert archive_path.exists()
        with zipfile.ZipFile(archive_path) as zf_std:
            assert len(zf_std.namelist()) == 0

    def test_file_not_found(self, temp_dir):
        """Test handling of non-existent files."""
        archive_path = temp_dir / "notfound.zip"

        with pytest.raises(FileNotFoundError):
            with SplitZipWriter(archive_path, split_size="1MB") as zf:
                zf.write("nonexistent_file.txt")

    def test_context_manager_cleanup_on_error(self, temp_dir, sample_files):
        """Test that files are properly closed on error."""
        archive_path = temp_dir / "error.zip"

        try:
            with SplitZipWriter(archive_path, split_size="1MB") as zf:
                zf.write(sample_files["small"])
                raise RuntimeError("Simulated error")
        except RuntimeError:
            pass

        # File should be closed and accessible
        # (Though archive may be incomplete/invalid)

    def test_unicode_filename(self, temp_dir):
        """Test handling of Unicode filenames."""
        archive_path = temp_dir / "unicode.zip"

        with SplitZipWriter(archive_path, split_size="1MB") as zf:
            zf.writestr("日本語.txt", "Japanese filename")
            zf.writestr("émoji_🎉.txt", "Emoji filename")

        with zipfile.ZipFile(archive_path) as zf_std:
            names = zf_std.namelist()
            assert "日本語.txt" in names
            assert "émoji_🎉.txt" in names

    def test_large_number_of_files(self, temp_dir):
        """Test archive with many files."""
        archive_path = temp_dir / "manyfiles.zip"

        with SplitZipWriter(archive_path, split_size="1MB") as zf:
            for i in range(100):
                zf.writestr(f"file_{i:03d}.txt", f"Content {i}")

        with zipfile.ZipFile(archive_path) as zf_std:
            assert len(zf_std.namelist()) == 100
