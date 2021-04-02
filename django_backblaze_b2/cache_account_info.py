import logging
from functools import wraps
from typing import Iterable, Tuple

from b2sdk.v1 import UrlPoolAccountInfo
from b2sdk.v1.exception import MissingAccountData
from django.core.cache import InvalidCacheBackendError, caches
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


class StoredBucketInfo:
    name: str
    id_: str


def _raise_missing_if_result_is_none(function):
    """
    Raise MissingAccountData if function's result is None.
    adapted from https://github.com/Backblaze/b2-sdk-python/blob/v1.5.0/b2sdk/account_info/in_memory.py
    """

    @wraps(function)
    def getter_function(*args, **kwargs):
        assert function.__name__.startswith("get_")
        result = function(*args, **kwargs)
        if result is None:
            raise MissingAccountData(function.__name__[len("get_") :])
        return result

    return getter_function


class DjangoCacheAccountInfo(UrlPoolAccountInfo):
    """
    Store account information in django's cache: https://docs.djangoproject.com/en/3.1/topics/cache
    """

    def __init__(self, cacheName: str):
        logger.debug(f"Initializing {self.__class__.__name__} with cache '{cacheName}'")
        self._cacheName = cacheName
        try:
            self.cache = caches[cacheName]
            self.cache.set("bucket_names", [])
        except InvalidCacheBackendError:
            logger.exception("Cache assignment failed")
            from django.conf import settings

            helpMessage = (
                (
                    ". "
                    "The default 'accountInfo' option of this library is with a django cache"
                    " by the name of 'django-backblaze-b2'"
                )
                if "accountInfo" not in settings.BACKBLAZE_CONFIG
                else ""
            )

            raise ImproperlyConfigured(f"Expected to find a cache with name '{cacheName}' as per options" + helpMessage)
        super(DjangoCacheAccountInfo, self).__init__()

    def clear(self):
        """
        Remove all info about accounts and buckets.
        """
        self.cache.clear()

    def _set_auth_data(
        self,
        account_id,
        auth_token,
        api_url,
        download_url,
        minimum_part_size,
        application_key,
        realm,
        allowed,
        application_key_id,
    ):
        self.cache.set("account_id", account_id)
        self.cache.set("auth_token", auth_token)
        self.cache.set("api_url", api_url)
        self.cache.set("download_url", download_url)
        self.cache.set("minimum_part_size", minimum_part_size)
        self.cache.set("application_key", application_key)
        self.cache.set("realm", realm)
        self.cache.set("allowed", allowed)
        self.cache.set("application_key_id", application_key_id)

    @_raise_missing_if_result_is_none
    def get_application_key(self):
        return self.cache.get("application_key")

    @_raise_missing_if_result_is_none
    def get_application_key_id(self):
        return self.cache.get("application_key_id")

    @_raise_missing_if_result_is_none
    def get_account_id(self):
        return self.cache.get("account_id")

    @_raise_missing_if_result_is_none
    def get_api_url(self):
        return self.cache.get("api_url")

    def get_account_auth_token(self):
        """Named different from cached value"""
        auth_token = self.cache.get("auth_token")
        if auth_token is None:
            raise MissingAccountData("auth_token")
        return auth_token

    @_raise_missing_if_result_is_none
    def get_download_url(self):
        return self.cache.get("download_url")

    @_raise_missing_if_result_is_none
    def get_realm(self):
        return self.cache.get("realm")

    @_raise_missing_if_result_is_none
    def get_minimum_part_size(self):
        return self.cache.get("minimum_part_size")

    @_raise_missing_if_result_is_none
    def get_allowed(self):
        return self.cache.get("allowed")

    def get_bucket_id_or_none_from_bucket_name(self, bucket_name: str):
        try:
            return self.cache.get(_bucket_cachekey(bucket_name))
        except KeyError as e:
            logger.debug(f"cache miss {bucket_name}: {e}")
            return None

    def refresh_entire_bucket_name_cache(self, name_id_iterable: Iterable[Tuple[str, str]]):
        bucket_names_to_remove = set(self.cache.get("bucket_names")) - {name for name, id in name_id_iterable}
        for (bucket_name, bucket_id) in name_id_iterable:
            self.cache.set(_bucket_cachekey(bucket_name), bucket_id)
        for bucket_name in bucket_names_to_remove:
            self.remove_bucket_name(bucket_name)

    def save_bucket(self, bucket: StoredBucketInfo):
        self.cache.set(_bucket_cachekey(bucket.name), bucket.id_)
        self.cache.set("bucket_names", list(self.cache.get("bucket_names")) + [bucket.name])

    def remove_bucket_name(self, bucket_name):
        self.cache.set("bucket_names", [n for n in self.cache.get("bucket_names") if n != bucket_name])
        self.cache.delete(_bucket_cachekey(bucket_name))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}{{cacheName={self._cacheName},cache={self.cache}}}"


def _bucket_cachekey(bucket_name: str) -> str:
    """Current django versions do not support cache keys greater than 250 characters.
    Backblaze bucket names allow a max of 50 characters. This is a futureproofing error"""
    assert (
        len(bucket_name) + len("bucket-name__") < 250
    ), "This version of django-backblaze-b2 does not support cache keys greater than 250 in length."
    return f"bucket-name__{bucket_name}"
