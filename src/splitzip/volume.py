"""Volume management for split ZIP archives."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import BinaryIO, Callable

from .exceptions import VolumeTooSmallError

# Minimum volume size: need room for at least a local file header + some data
MIN_VOLUME_SIZE = 64 * 1024  # 64 KB minimum


class VolumeManager:
    """
    Manages split ZIP volume files.

    Handles:
    - Creating and naming volume files (.z01, .z02, ..., .zip)
    - Tracking bytes written per volume
    - Switching to new volumes when capacity reached
    - Writing data that spans volume boundaries
    """

    def __init__(
        self,
        base_path: str | Path,
        split_size: int,
        on_volume_created: Callable[[int, Path], None] | None = None,
    ) -> None:
        """
        Initialize volume manager.

        Args:
            base_path: Base path for the archive (e.g., "backup.zip").
                      Split files will be named backup.z01, backup.z02, ..., backup.zip
            split_size: Maximum size of each volume in bytes.
            on_volume_created: Optional callback called when a new volume is created.
                              Receives (volume_number, volume_path).

        Raises:
            VolumeTooSmallError: If split_size is below minimum.
        """
        if split_size < MIN_VOLUME_SIZE:
            raise VolumeTooSmallError(split_size, MIN_VOLUME_SIZE)

        self.base_path = Path(base_path)
        self.split_size = split_size
        self.on_volume_created = on_volume_created

        self._current_volume: int = 0
        self._current_file: BinaryIO | None = None
        self._bytes_written_to_volume: int = 0
        self._total_bytes_written: int = 0
        self._volume_paths: list[Path] = []
        self._is_final_volume: bool = False
        self._closed: bool = False

    @property
    def current_volume(self) -> int:
        """Current volume number (0-indexed)."""
        return self._current_volume

    @property
    def current_offset(self) -> int:
        """Current byte offset within the current volume."""
        return self._bytes_written_to_volume

    @property
    def total_bytes_written(self) -> int:
        """Total bytes written across all volumes."""
        return self._total_bytes_written

    @property
    def volume_count(self) -> int:
        """Number of volumes created so far."""
        return len(self._volume_paths)

    @property
    def volume_paths(self) -> list[Path]:
        """List of all volume paths created."""
        return self._volume_paths.copy()

    def space_remaining(self) -> int:
        """Bytes remaining in current volume."""
        if self._is_final_volume:
            # Final volume has no size limit
            return sys.maxsize
        return self.split_size - self._bytes_written_to_volume

    def volume_path_for(self, volume_number: int, is_final: bool = False) -> Path:
        """
        Get the path for a specific volume number.

        Args:
            volume_number: 0-indexed volume number.
            is_final: Whether this is the final volume.

        Returns:
            Path for the volume file.

        Volume naming convention:
            Volume 0: archive.z01
            Volume 1: archive.z02
            ...
            Final:    archive.zip
        """
        if is_final:
            return self.base_path

        stem = self.base_path.stem
        parent = self.base_path.parent
        # .z01, .z02, etc. (1-indexed in filename)
        return parent / f"{stem}.z{volume_number + 1:02d}"

    def _open_volume(self, volume_number: int, is_final: bool = False) -> None:
        """Open a new volume file for writing."""
        if self._current_file is not None:
            self._current_file.close()

        path = self.volume_path_for(volume_number, is_final)
        self._current_file = Path(path).open("wb")  # noqa: SIM115
        self._current_volume = volume_number
        self._bytes_written_to_volume = 0
        self._is_final_volume = is_final
        self._volume_paths.append(path)

        if not is_final and volume_number >= 99:
            warnings.warn(
                f"Volume count exceeds 99 ({volume_number + 1} volumes). "
                "Some ZIP tools may not handle 3+ digit extensions.",
                stacklevel=2,
            )

        if self.on_volume_created:
            self.on_volume_created(volume_number, path)

    def _ensure_open(self) -> None:
        """Ensure a volume file is open."""
        if self._current_file is None:
            self._open_volume(0)

    def ensure_space(self, nbytes: int) -> None:
        """Advance to the next volume if current cannot fit *nbytes*.

        This is used to prevent headers from being split across volumes,
        which would make patching CRC/size fields impossible.
        """
        if self._is_final_volume:
            return
        self._ensure_open()
        if self.space_remaining() < nbytes:
            self.next_volume()

    def next_volume(self) -> None:
        """Close current volume and open the next one."""
        if self._is_final_volume:
            raise RuntimeError("Cannot create new volume after final volume started")

        next_num = self._current_volume + 1 if self._current_file else 0
        self._open_volume(next_num)

    def start_final_volume(self) -> None:
        """
        Start the final volume (.zip file).

        The final volume contains the central directory and has no size limit.
        Call this before writing the central directory.

        If all content fits in a single volume, this renames that volume to .zip.
        Otherwise, it opens a new volume for the central directory.
        """
        if self._is_final_volume:
            return

        # If we haven't written anything yet, just open the final volume directly
        if self._current_file is None:
            self._open_volume(0, is_final=True)
            return

        # If we only have one volume so far and it's not full, we can rename it
        # to be the final .zip file instead of creating .z01 + .zip
        if len(self._volume_paths) == 1 and self._bytes_written_to_volume < self.split_size:
            # Close current file
            self._current_file.close()

            # Rename from .z01 to .zip
            old_path = self._volume_paths[0]
            new_path = self.base_path

            if old_path != new_path:
                old_path.rename(new_path)
                self._volume_paths[0] = new_path

            # Reopen in append mode
            self._current_file = new_path.open("ab")  # noqa: SIM115
            self._is_final_volume = True
        else:
            # Need a separate final volume
            self._open_volume(self._current_volume + 1, is_final=True)

    def write(self, data: bytes) -> None:
        """
        Write data to the current volume, potentially spanning volumes.

        If data won't fit in the current volume, this will:
        1. Write what fits to the current volume
        2. Open the next volume
        3. Continue writing

        Args:
            data: Bytes to write.
        """
        if self._closed:
            raise RuntimeError("VolumeManager is closed")

        self._ensure_open()
        assert self._current_file is not None

        remaining = data
        while remaining:
            space = self.space_remaining()

            if space >= len(remaining) or self._is_final_volume:
                # All data fits (or we're in final volume with unlimited space)
                self._current_file.write(remaining)
                self._bytes_written_to_volume += len(remaining)
                self._total_bytes_written += len(remaining)
                break
            elif space > 0:
                # Write what fits
                chunk = remaining[:space]
                self._current_file.write(chunk)
                self._bytes_written_to_volume += len(chunk)
                self._total_bytes_written += len(chunk)
                remaining = remaining[space:]
                # Move to next volume
                self.next_volume()
            else:
                # No space, move to next volume
                self.next_volume()

    def write_at_offset(self, data: bytes, volume: int, offset: int) -> None:
        """
        Write data at a specific location (for patching headers).

        This is used to go back and update headers (e.g., CRC, sizes)
        after the data has been written.

        Args:
            data: Bytes to write.
            volume: Volume number.
            offset: Byte offset within the volume.
        """
        is_final = volume == self._current_volume and self._is_final_volume
        path = self.volume_path_for(volume, is_final=is_final)
        if (
            path not in self._volume_paths
            and not (self._is_final_volume and volume == self._current_volume)
        ):
            raise ValueError(f"Volume {volume} has not been created")

        # Need to flush current file before patching
        if self._current_file:
            self._current_file.flush()

        with open(path, "r+b") as f:
            f.seek(offset)
            f.write(data)

    def close(self) -> list[Path]:
        """
        Close all volumes and return the list of created paths.

        Returns:
            List of paths to all volume files created.
        """
        if self._current_file is not None:
            self._current_file.close()
            self._current_file = None
        self._closed = True
        return self._volume_paths.copy()

    def __enter__(self) -> VolumeManager:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()
