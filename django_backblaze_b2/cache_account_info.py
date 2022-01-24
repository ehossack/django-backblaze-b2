import logging
from functools import wraps
from hashlib import sha3_224 as hash
from typing import Iterable, Optional, Tuple

from b2sdk.account_info.exception import MissingAccountData
from b2sdk.account_info.upload_url_pool import UrlPoolAccountInfo
from django.core.cache import InvalidCacheBackendError, caches
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger("django-backblaze-b2")


class StoredBucketInfo:
    name: str
    id_: str


def _handle_result_is_none(item_name=None):
    """
    Raise MissingAccountData if function's result is None.
    adapted from https://github.com/Backblaze/b2-sdk-python/blob/v1.5.0/b2sdk/account_info/in_memory.py
    """

    def wrapper_factory(function):
        @wraps(function)
        def getter_function(self, *args, **kwargs):
            assert function.__name__.startswith("get_")
            result = function(self, *args, **kwargs)
            if result is None:
                self.cache.clear()
                raise MissingAccountData(
                    f"Token refresh required to determine value of '{item_name or function.__name__[len('get_') :]}'",
                )
            return result

        return getter_function

    return wrapper_factory


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
        self.cache.set("bucket_names", [])

    def _set_auth_data(
        self,
        account_id,
        auth_token,
        api_url,
        download_url,
        recommended_part_size,
        absolute_minimum_part_size,
        application_key,
        realm,
        s3_api_url,
        allowed,
        application_key_id,
    ):
        self.cache.set(
            "cached_account_info",
            {
                "account_id": account_id,
                "auth_token": auth_token,
                "api_url": api_url,
                "download_url": download_url,
                "recommended_part_size": recommended_part_size,
                "absolute_minimum_part_size": absolute_minimum_part_size,
                "application_key": application_key,
                "realm": realm,
                "s3_api_url": s3_api_url,
                "allowed": allowed,
                "application_key_id": application_key_id,
            },
            timeout=None,
        )

    def _cached_info(self):
        return self.cache.get("cached_account_info", default={})

    @_handle_result_is_none()
    def get_application_key(self):
        return self._cached_info().get("application_key")

    @_handle_result_is_none()
    def get_application_key_id(self):
        return self._cached_info().get("application_key_id")

    @_handle_result_is_none()
    def get_account_id(self):
        return self._cached_info().get("account_id")

    @_handle_result_is_none()
    def get_api_url(self):
        return self._cached_info().get("api_url")

    @_handle_result_is_none("auth_token")
    def get_account_auth_token(self):
        """Named different from cached value"""
        return self._cached_info().get("auth_token")

    @_handle_result_is_none()
    def get_download_url(self):
        return self._cached_info().get("download_url")

    @_handle_result_is_none()
    def get_realm(self):
        return self._cached_info().get("realm")

    @_handle_result_is_none()
    def get_absolute_minimum_part_size(self):
        return self._cached_info().get("absolute_minimum_part_size")

    @_handle_result_is_none()
    def get_recommended_part_size(self):
        return self._cached_info().get("recommended_part_size")

    @_handle_result_is_none()
    def get_allowed(self):
        return self._cached_info().get("allowed")

    def get_s3_api_url(self):
        return self._cached_info().get("s3_api_url") or ""

    def get_bucket_id_or_none_from_bucket_name(self, bucket_name: str) -> Optional[str]:
        try:
            return self.cache.get(_bucket_cachekey(bucket_name))
        except KeyError as e:
            logger.debug(f"cache miss {bucket_name}: {e}")
            return None

    def get_bucket_name_or_none_from_bucket_id(self, bucket_id: str) -> Optional[str]:
        try:
            for bucket_name in self.cache.get("bucket_names", []):
                bucket_id = self.cache.get(_bucket_cachekey(bucket_name))
                if bucket_id:
                    return bucket_name
            logger.debug(f"cache miss {bucket_id}")
        except KeyError as e:
            logger.debug(f"cache miss {bucket_id}: {e}")
        return None

    def refresh_entire_bucket_name_cache(self, name_id_iterable: Iterable[Tuple[str, str]]):
        bucket_names_to_remove = set(self.cache.get("bucket_names", [])) - {name for name, id in name_id_iterable}
        for (bucket_name, bucket_id) in name_id_iterable:
            self.cache.set(_bucket_cachekey(bucket_name), bucket_id)
        for bucket_name in bucket_names_to_remove:
            self.remove_bucket_name(bucket_name)

    def save_bucket(self, bucket: StoredBucketInfo):
        self.cache.set(_bucket_cachekey(bucket.name), bucket.id_)
        self.cache.set("bucket_names", list(self.cache.get("bucket_names", [])) + [bucket.name])

    def remove_bucket_name(self, bucket_name):
        self.cache.set("bucket_names", [n for n in self.cache.get("bucket_names", []) if n != bucket_name])
        self.cache.delete(_bucket_cachekey(bucket_name))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}{{cacheName={self._cacheName},cache={self.cache}}}"


def _bucket_cachekey(bucket_name: str) -> str:
    return hash(f"bucket-name__{bucket_name}".encode()).hexdigest()
