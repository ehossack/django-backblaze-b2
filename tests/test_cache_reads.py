from time import monotonic
from typing import Any, Iterator

import pytest
from b2sdk.v2 import AuthInfoCache, B2Api, B2HttpApiConfig, RawSimulator
from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.locmem import LocMemCache
from django.core.files.base import ContentFile
from django.test import override_settings

from django_backblaze_b2 import BackblazeB2Storage, _file_info_cache, cache_account_info
from django_backblaze_b2.cache_account_info import DjangoCacheAccountInfo


class CountingCache(LocMemCache):
    def __init__(self, name: str, params: dict[str, Any]) -> None:
        super().__init__(name, params)
        self.read_keys: list[str] = []

    def get(self, key: str, default: Any = None, version: int | None = None) -> Any:
        self.read_keys.append(key)
        return super().get(key, default, version)


@pytest.fixture
def counting_cache() -> Iterator[CountingCache]:
    cache_settings = {
        **settings.CACHES,
        "counting-cache": {"BACKEND": f"{__name__}.CountingCache", "LOCATION": __name__},
    }
    with override_settings(CACHES=cache_settings):
        cache = caches["counting-cache"]
        assert isinstance(cache, CountingCache)
        cache.clear()
        yield cache


@pytest.fixture
def b2_storage(counting_cache: CountingCache) -> BackblazeB2Storage:
    account_info = DjangoCacheAccountInfo("counting-cache")
    api = B2Api(
        account_info=account_info,
        cache=AuthInfoCache(account_info),
        api_config=B2HttpApiConfig(_raw_api_class=RawSimulator),
    )
    key_id, key = api.session.raw_api.create_account()
    api.authorize_account("production", key_id, key)
    api.create_bucket("routesheets", "allPublic")
    b2_storage = BackblazeB2Storage(bucket="routesheets", authorize_on_init=False, allow_file_overwrites=True)
    b2_storage._account_info = account_info
    b2_storage._b2_api = api
    return b2_storage


def test_storage_reads_file_metadata_once_per_file(
    b2_storage: BackblazeB2Storage, counting_cache: CountingCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = ["first route.txt", "second.txt", "third.txt"]
    for name in names:
        b2_storage.save(name, ContentFile(b"route"))
        b2_storage.size(name)
    after_memos_expire = monotonic() + 10
    monkeypatch.setattr(_file_info_cache, "monotonic", lambda: after_memos_expire)
    monkeypatch.setattr(cache_account_info, "monotonic", lambda: after_memos_expire)
    counting_cache.read_keys.clear()

    descriptions = []
    reads_per_file = []
    for name in names:
        descriptions.append((b2_storage.exists(name), b2_storage.url(name), b2_storage.size(name)))
        reads_per_file.append(counting_cache.read_keys[:])
        counting_cache.read_keys.clear()

    assert descriptions == [
        (True, "http://download.example.com/file/routesheets/first%20route.txt", 5),
        (True, "http://download.example.com/file/routesheets/second.txt", 5),
        (True, "http://download.example.com/file/routesheets/third.txt", 5),
    ]
    assert [len(keys) for keys in reads_per_file] == [2, 1, 1]
    assert [keys.count("cached_account_info") for keys in reads_per_file] == [1, 0, 0]


def test_save_and_delete_invalidate_shared_and_local_metadata(b2_storage: BackblazeB2Storage) -> None:
    b2_storage.save("route.txt", ContentFile(b"old"))
    b2_storage.size("route.txt")

    b2_storage.save("route.txt", ContentFile(b"updated"))
    size_after_save = b2_storage.size("route.txt")
    b2_storage.delete("route.txt")
    size_after_delete = b2_storage.size("route.txt")
    b2_storage.delete("route.txt")
    exists_after_both_deletes = b2_storage.exists("route.txt")

    assert size_after_save == 7
    assert size_after_delete == 3
    assert not exists_after_both_deletes
