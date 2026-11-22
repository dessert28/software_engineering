"""存储层与上传边界测试。

重点验证两件容易被忽略的事：
1. 超限文件不能把磁盘写满 —— 半成品必须清理掉；
2. md5 秒传的 blob 复用逻辑，不能让磁盘上出现两份相同内容。
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from app.services.storage import LocalStorage


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(root=tmp_path / "blobs")


class TestStorageBasics:
    def test_put_and_read_roundtrip(self, storage: LocalStorage):
        md5, size = storage.put_bytes("abcdef123", b"hello world")
        assert size == 11
        assert storage.exists("abcdef123")
        assert storage.path_of("abcdef123").read_bytes() == b"hello world"
        assert len(md5) == 32

    def test_two_level_sharding(self, storage: LocalStorage):
        storage.put_bytes("abc123def", b"x")
        p = storage.path_of("abc123def")
        assert p.parent.name == "ab"
        assert p.name == "abc123def"

    def test_same_content_same_md5(self, storage: LocalStorage):
        m1, _ = storage.put_bytes("key1xxxxxx", b"same-content")
        m2, _ = storage.put_bytes("key2xxxxxx", b"same-content")
        assert m1 == m2

    def test_delete_is_idempotent(self, storage: LocalStorage):
        storage.put_bytes("gone123456", b"data")
        storage.delete("gone123456")
        storage.delete("gone123456")  # 再删一次不该炸


class TestStreamingUpload:
    def test_streaming_matches_bytes_api(self, storage: LocalStorage):
        payload = b"A" * (3 * 1024 * 1024)
        m1, s1 = storage.put_bytes("streambytes1", payload)
        m2, s2 = storage.put_fileobj("streamfileobj", io.BytesIO(payload))
        assert (m1, s1) == (m2, s2)

    def test_oversize_raises_and_leaves_nothing_behind(self, storage: LocalStorage):
        """关键：超限时必须抛错，且不能留下半个文件占着磁盘。"""
        blob = io.BytesIO(b"B" * 5000)
        with pytest.raises(ValueError):
            storage.put_fileobj("toobig123456", blob, max_bytes=1024)
        assert not storage.exists("toobig123456")

    def test_exactly_at_limit_is_allowed(self, storage: LocalStorage):
        blob = io.BytesIO(b"C" * 1024)
        _, size = storage.put_fileobj("exactlimit12", blob, max_bytes=1024)
        assert size == 1024

    def test_one_byte_over_limit_is_rejected(self, storage: LocalStorage):
        blob = io.BytesIO(b"D" * 1025)
        with pytest.raises(ValueError):
            storage.put_fileobj("onetoover123", blob, max_bytes=1024)

    def test_empty_stream_yields_zero(self, storage: LocalStorage):
        _, size = storage.put_fileobj("emptyfile123", io.BytesIO(b""))
        assert size == 0


class TestDedupeStorage:
    def test_second_identical_upload_can_be_discarded(self, storage: LocalStorage):
        """秒传路径：第二份写完发现 md5 已存在，就把它删掉。"""
        m1, _ = storage.put_fileobj("firstcopy123", io.BytesIO(b"paper"))
        m2, _ = storage.put_fileobj("secondcopy12", io.BytesIO(b"paper"))
        assert m1 == m2

        storage.delete("secondcopy12")
        assert storage.exists("firstcopy123")
        assert not storage.exists("secondcopy12")
