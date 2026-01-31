# Changelog

## [0.2.0]

### Security
- Fix path traversal (zip slip) in `sanitize_arcname`
- Add ZIP32 overflow guards (4GB file limit, 65535 entry limit)
- Detect and skip symlinks

### Added
- CI workflow (lint, type-check, test across Python 3.9–3.13)
- Trusted publisher PyPI publishing via OIDC
- CLI tests, volume boundary tests, overflow guard tests
- API reference and limitations documentation

### Fixed
- `close()` is now idempotent (safe on re-entry)
- Archive name length validated against 65535-byte ZIP limit
- Removed placeholder author email from pyproject.toml
