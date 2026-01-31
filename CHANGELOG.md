# Changelog

## [0.2.0]

### Security
- Fix path traversal (zip slip) in `sanitize_arcname`
- Add ZIP32 overflow guards (4GB file limit, 65535 entry limit)
- Detect and skip symlinks
- Sanitize directory entry arcnames through `sanitize_arcname`

### Added
- CI workflow (lint, type-check, test across Python 3.9–3.13)
- Trusted publisher PyPI publishing via OIDC
- CLI tests, volume boundary tests, overflow guard tests
- API reference and limitations documentation
- Compression parameter validation
- Volume count warning when exceeding 99 volumes
- Streaming compression in `writestr` for large buffers
- CI: p7zip-full for integration tests, 80% coverage threshold

### Fixed
- Local file headers no longer split across volume boundaries
- `close()` is now idempotent (safe on re-entry)
- `__exit__` skips finalization on error instead of writing corrupt archive
- Archive name length validated against 65535-byte ZIP limit
- `space_remaining()` returns `sys.maxsize` instead of `float("inf")`
- CLI returns exit code 1 for unknown subcommands
- README clone URL matches repository URL
- `create()` returns `list[Path]` for consistency with `close()`
- `parse_size` type annotation includes `float`
- Removed placeholder author email from pyproject.toml
- Pinned build tool version in publish workflow

### Removed
- Dead code: `_is_utf8()` method, `SPLIT_ARCHIVE_SIG` constant
- Python 3.14 from classifiers (not yet released)
