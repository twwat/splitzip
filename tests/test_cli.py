"""Tests for the CLI interface."""

import pytest

from splitzip.__main__ import main


class TestCLI:
    """Tests for CLI main function."""

    def test_no_args_prints_help(self, capsys):
        result = main([])
        assert result == 0
        captured = capsys.readouterr()
        assert "usage" in captured.out.lower() or "splitzip" in captured.out.lower()

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0

    def test_create_nonexistent_file(self, tmp_path, capsys):
        result = main([
            "create", "-o", str(tmp_path / "out.zip"),
            "-s", "1MB", "nonexistent_file.txt",
        ])
        assert result == 1

    def test_create_basic(self, tmp_path):
        test_file = tmp_path / "hello.txt"
        test_file.write_text("hello")
        result = main([
            "create", "-o", str(tmp_path / "out.zip"),
            "-s", "1MB", str(test_file),
        ])
        assert result == 0
        assert (tmp_path / "out.zip").exists()
