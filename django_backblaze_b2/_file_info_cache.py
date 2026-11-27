from dataclasses import dataclass
from hashlib import sha3_224
from logging import getLogger
from threading import Lock
from time import monotonic
from typing import Dict, Optional

from b2sdk.v2 import Bucket
from django.core.cache.backends.base import BaseCache
from typing_extensions import TypedDict

logger = getLogger("django-backblaze-b2")


class _SdkBaseFileInfoDict(TypedDict):
    """See https://github.com/Backblaze/b2-sdk-python/blob/2c85182c82ee09b7db7216d70567aafb87f31536/b2sdk/file_version.py"""  # noqa: E501

    fileId: str  # noqa: N815
    fileName: str  # noqa: N815
    fileInfo: dict  # noqa: N815


class _SdkFileInfoDict(_SdkBaseFileInfoDict, total=False):
    """See https://github.com/Backblaze/b2-sdk-python/blob/2c85182c82ee09b7db7216d70567aafb87f31536/b2sdk/file_version.py#L143"""  # noqa: E501

    size: int
    uploadTimestamp: int  # noqa: N815
    contentType: str  # noqa: N815


@dataclass(frozen=True)
class _CachedFileInfo:
    """A worker's copy of the file metadata and when it must be fetched again."""

    file_info: _SdkFileInfoDict
    expires_at: float


class FileInfoCache:
    """Avoid reading Django's cache twice when rendering a file link.

    A page can call exists() to check a file, then size() to display its size.
    Both calls need the same metadata, and each read from DatabaseCache runs a
    SQL query. Keep the first result in memory so the second call can reuse it.

    A save or delete in another worker invalidates the shared cache entry.
    The local copy expires after two seconds so this worker checks the shared
    cache again on the next lookup.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._recent_file_info: Dict[str, _CachedFileInfo] = {}

    def get(self, cache: BaseCache, bucket: Bucket, name: str) -> Optional[_SdkFileInfoDict]:
        with self._lock:
            cached = self._recent_file_info.get(name)
            if cached is not None and monotonic() < cached.expires_at:
                return cached.file_info

            file_info = self._get_or_set_shared_file_info(cache, bucket, name)
            if file_info is not None:
                max_cached_files = 256
                if len(self._recent_file_info) >= max_cached_files:
                    self._recent_file_info.clear()
                self._recent_file_info[name] = _CachedFileInfo(file_info=file_info, expires_at=monotonic() + 2)
            return file_info

    def _get_or_set_shared_file_info(self, cache: BaseCache, bucket: Bucket, name: str) -> Optional[_SdkFileInfoDict]:
        key = self._cache_key(bucket.name, name)
        cache_miss = object()
        cached_file_info = cache.get(key, cache_miss)
        if cached_file_info is not cache_miss:
            return cached_file_info

        logger.debug(f"file info cache miss for {name}")
        file_info: _SdkFileInfoDict = bucket.get_file_info_by_name(name).as_dict()
        if cache.add(key, file_info, timeout=60):
            return file_info
        return cache.get(key, file_info)

    def invalidate(self, cache: BaseCache, bucket_name: str, name: str) -> None:
        with self._lock:
            self._recent_file_info.pop(name, None)
            cache.delete(self._cache_key(bucket_name, name))

    @staticmethod
    def _cache_key(bucket_name: str, name: str) -> str:
        return sha3_224(f"{bucket_name}__{name}".encode()).hexdigest()
