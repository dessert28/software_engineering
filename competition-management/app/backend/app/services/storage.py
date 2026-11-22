"""存储层抽象：本地文件系统实现。

换 MinIO/S3 时只要实现同样的 put/get/delete 三个方法，
业务代码不需要改动 —— 这是目录 README 里承诺的「基础设施可替换」。
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from app.core.config import settings


class LocalStorage:
    backend_name = "local"

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.storage_root
        self.root.mkdir(parents=True, exist_ok=True)

    def _key_to_path(self, storage_key: str) -> Path:
        # 两级分片，避免单目录文件过多
        shard = storage_key[:2]
        p = self.root / shard / storage_key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def put_bytes(self, storage_key: str, data: bytes) -> tuple[str, int]:
        md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()
        path = self._key_to_path(storage_key)
        path.write_bytes(data)
        return md5, len(data)

    def put_fileobj(self, storage_key: str, src, *, max_bytes: int | None = None) -> tuple[str, int]:
        """从文件对象流式写盘，边写边算 md5，永不在内存里攒整个文件。

        超过 max_bytes 立刻抛 ValueError 并删除半成品 —— 否则一个畸形请求
        就能把磁盘写满。
        """
        md5 = hashlib.md5(usedforsecurity=False)
        size = 0
        path = self._key_to_path(storage_key)
        try:
            with path.open("wb") as fdst:
                while chunk := src.read(1024 * 1024):
                    size += len(chunk)
                    if max_bytes is not None and size > max_bytes:
                        raise ValueError(f"文件超过上限 {max_bytes} 字节")
                    md5.update(chunk)
                    fdst.write(chunk)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return md5.hexdigest(), size

    def put_stream(self, storage_key: str, src: Path) -> tuple[str, int]:
        md5 = hashlib.md5(usedforsecurity=False)
        size = 0
        path = self._key_to_path(storage_key)
        with src.open("rb") as fsrc, path.open("wb") as fdst:
            while chunk := fsrc.read(1024 * 1024):
                md5.update(chunk)
                size += len(chunk)
                fdst.write(chunk)
        return md5.hexdigest(), size

    def exists(self, storage_key: str) -> bool:
        return self._key_to_path(storage_key).exists()

    def path_of(self, storage_key: str) -> Path:
        return self._key_to_path(storage_key)

    def delete(self, storage_key: str) -> None:
        p = self._key_to_path(storage_key)
        if p.exists():
            p.unlink()

    def purge_root(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)


def get_storage() -> LocalStorage:
    # 预留分支：STORAGE_BACKEND=s3 时返回 MinIOStorage（待 P1 实现）
    return LocalStorage()
