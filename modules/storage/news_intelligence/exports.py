"""Safe deterministic file-export and reconciliation primitives."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


class UnsafeExportPathError(ValueError):
    pass


class ExportArtifactConflictError(RuntimeError):
    pass


def resolve_export_path(root: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise UnsafeExportPathError("export path must be non-empty and relative")
    root_resolved = root.resolve()
    target = (root_resolved / relative_path).resolve(strict=False)
    if target == root_resolved or root_resolved not in target.parents:
        raise UnsafeExportPathError("export path escapes configured root")
    parent = target.parent
    while parent != root_resolved:
        if parent.exists() and parent.is_symlink():
            raise UnsafeExportPathError("export path crosses a symlink")
        parent = parent.parent
    return target


def write_or_reconcile(
    *,
    root: Path,
    relative_path: str,
    content: bytes,
) -> tuple[Path, str, bool]:
    target = resolve_export_path(root, relative_path)
    expected_checksum = hashlib.sha256(content).hexdigest()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        actual_checksum = _file_checksum(target)
        if actual_checksum != expected_checksum:
            raise ExportArtifactConflictError("existing export checksum mismatch")
        return target, expected_checksum, True

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory_descriptor = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)
    return target, expected_checksum, False


def _file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
