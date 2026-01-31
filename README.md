[![PyPI version](https://img.shields.io/pypi/v/splitzip)](https://pypi.org/project/splitzip/) [![Python versions](https://img.shields.io/pypi/pyversions/splitzip?v=1)](https://pypi.org/project/splitzip/) [![License](https://img.shields.io/pypi/l/splitzip?v=1)](https://opensource.org/licenses/MIT)

# splitzip

Create split ZIP archives compatible with standard tools.

**No 7-Zip required.** Archives created with splitzip can be extracted using Windows Explorer, WinZip, macOS Archive Utility, and standard `unzip` on Linux.

## Features

- Pure Python, no external dependencies
- Compatible with standard ZIP tools (no proprietary formats)
- Human-friendly size specifications (`"100MB"`, `"700MiB"`, `"4.7GB"`)
- Progress callbacks for large files
- Context manager support
- CLI tool included

## Installation

```bash
pip install splitzip
```

## Quick Start

### Simple Usage

```python
import splitzip

# Create a split archive from files
splitzip.create(
    "backup.zip",
    ["documents/", "photos/", "important.pdf"],
    split_size="650MB"
)
```

Output files: `backup.z01`, `backup.z02`, ..., `backup.zip`

### Context Manager

```python
from splitzip import SplitZipWriter

with SplitZipWriter("backup.zip", split_size="100MB") as zf:
    # Add files
    zf.write("document.pdf")
    zf.write("photos/", recursive=True)
    
    # Add with custom name
    zf.write("secret.txt", arcname="data/renamed.txt")
    
    # Add content directly
    zf.writestr("hello.txt", b"Hello, World!")
    zf.writestr("config.json", '{"key": "value"}')
```

### Advanced Options

```python
from splitzip import SplitZipWriter, STORED, DEFLATED

def on_progress(filename, bytes_done, total_bytes):
    pct = (bytes_done / total_bytes) * 100
    print(f"\r{filename}: {pct:.1f}%", end="")

def on_volume(volume_num, path):
    print(f"Created volume: {path}")

with SplitZipWriter(
    "backup.zip",
    split_size="700MiB",          # DVD size
    compression=DEFLATED,          # or STORED for no compression
    compresslevel=9,               # 1-9 (default: 6)
    on_volume=on_volume,           # Volume creation callback
    on_progress=on_progress,       # Progress callback
) as zf:
    zf.write("large_file.bin")
```

### Streaming from File Objects

```python
import io
from splitzip import SplitZipWriter

data = get_data_from_somewhere()

with SplitZipWriter("archive.zip", split_size="100MB") as zf:
    zf.write_fileobj(
        io.BytesIO(data),
        arcname="streamed.bin",
        size=len(data)  # Optional, enables progress callback
    )
```

## Size Specifications

splitzip accepts sizes in multiple formats:

| Format | Example | Bytes |
|--------|---------|-------|
| Integer | `104857600` | 104,857,600 |
| Bytes | `"100B"` | 100 |
| Kilobytes (decimal) | `"100KB"` | 100,000 |
| Megabytes (decimal) | `"100MB"` | 100,000,000 |
| Gigabytes (decimal) | `"1GB"` | 1,000,000,000 |
| Kibibytes (binary) | `"100KiB"` | 102,400 |
| Mebibytes (binary) | `"700MiB"` | 734,003,200 |
| Gibibytes (binary) | `"1GiB"` | 1,073,741,824 |

Common split sizes:
- CD-ROM: `"650MB"` or `"700MB"`
- FAT32 limit: `"4GiB"` (minus 1 byte)
- Email attachment: `"25MB"`

## Command Line Interface

```bash
# Create a split archive
splitzip create -o backup.zip -s 100MB file1.txt directory/

# With options
splitzip create -o backup.zip -s 700MiB \
    --level 9 \           # Max compression
    --verbose \           # Show progress
    documents/ photos/

# Store without compression
splitzip create -o backup.zip -s 100MB --store largefile.bin
```

## Output File Naming

splitzip follows the standard ZIP split archive convention:

```
backup.z01  (first volume)
backup.z02  (second volume)
backup.z03  (third volume)
...
backup.zip  (final volume, contains central directory)
```

**All files must be present in the same directory for extraction.**

## Compatibility

| Tool | Single Volume | Split Archive |
|------|:-------------:|:-------------:|
| Windows Explorer | ✅ | ✅ |
| WinZip | ✅ | ✅ |
| 7-Zip | ✅ | ✅ |
| macOS Archive Utility | ✅ | ✅* |
| Linux `unzip` | ✅ | ✅** |
| Python `zipfile` | ✅ | ❌ |

\* May require all files to be selected and opened together  
\*\* May require `unzip -F` flag for split archives

## API Reference

### `SplitZipWriter(path, split_size, compression=DEFLATED, compresslevel=6, on_volume=None, on_progress=None)`

- **path** (`str | Path`): Path for the final `.zip` file.
- **split_size** (`int | str`): Maximum size per volume (bytes or human-readable string).
- **compression** (`int`): `DEFLATED` (default) or `STORED`.
- **compresslevel** (`int`): DEFLATE level 1–9 (default 6).
- **on_volume** (`(int, Path) -> None | None`): Called when a volume is created.
- **on_progress** (`(str, int, int) -> None | None`): Called with `(filename, bytes_done, total_bytes)`.

#### Methods

- **`write(path, arcname=None, recursive=True, compression=None, compresslevel=None)`** — Add a file or directory. Set `recursive=False` to add only the directory entry without contents. Symlinks are skipped.
- **`writestr(arcname, data, compression=None, compresslevel=None)`** — Write bytes/str directly.
- **`write_fileobj(fileobj, arcname, size=None, compression=None, compresslevel=None)`** — Write from a file-like object.
- **`close()`** — Finalize the archive. Returns list of volume paths.

### Exceptions

| Exception | When raised |
|-----------|------------|
| `SplitZipError` | Base exception for all splitzip errors |
| `VolumeError` | Volume management errors |
| `VolumeTooSmallError` | Split size too small for headers |
| `UnsafePathError` | Path traversal detected (zip slip) |
| `CompressionError` | Compression failure |
| `IntegrityError` | CRC mismatch |

## Limitations

- **Minimum volume size**: 64KB
- **No ZIP64 support**: Individual files must be under 4GB, total entries under 65,535
- **No encryption**: Use filesystem encryption for sensitive data
- **No reading/extraction**: This is a write-only library (use standard tools to extract)
- **No ZSTD/LZMA**: Only DEFLATE and STORED compression (for compatibility)
- **Symlinks are skipped**: Symbolic links are ignored with a warning

## Development

```bash
# Clone and install in development mode
git clone https://github.com/twwat/splitzip
cd splitzip
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=splitzip

# Type checking
mypy src/splitzip

# Linting
ruff check src/splitzip
```

## License

MIT License. See [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please open an issue to discuss major changes before submitting a PR.
