"""뉴스 모듈 전반에서 사용하는 인프라 유틸리티를 제공한다."""

from __future__ import annotations

import errno
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def single_writer_lock(database_path: str | Path) -> Iterator[None]:
    """한 데이터베이스에 하나의 CLI 파이프라인만 접근하도록 잠근다."""

    path = Path(database_path).expanduser()
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            raise RuntimeError(
                f"another news pipeline process is using {path}"
            ) from error
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
