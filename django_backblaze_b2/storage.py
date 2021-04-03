from datetime import datetime
from logging import getLogger
from typing import IO, Any, Callable, Dict, List, Optional, Tuple, cast

from b2sdk.account_info.abstract import AbstractAccountInfo
from b2sdk.cache import AuthInfoCache
from b2sdk.v1 import B2Api, Bucket, InMemoryAccountInfo, SqliteAccountInfo
from b2sdk.v1.exception import FileNotPresent, NonExistentBucket
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

from django_backblaze_b2.b2_file import B2File
from django_backblaze_b2.cache_account_info import DjangoCacheAccountInfo
from django_backblaze_b2.options import (
    BackblazeB2StorageOptions,
    DjangoCacheAccountInfoConfig,
    SqliteAccountInfoConfig,
    getDefaultB2StorageOptions,
)

logger = getLogger("django-backblaze-b2")


@deconstructible
class BackblazeB2Storage(Storage):
    """Storage class which fulfills the Django Storage contract through b2 apis"""

    def __init__(self, **kwargs):
        opts = self._getDjangoSettingsOptions(kwargs.get("opts", {}))
        if "opts" in kwargs:
            self._validateOptions(kwargs.get("opts"))
        merge(opts, kwargs.get("opts", {}))

        self._bucketName = opts["bucket"]
        self._defaultFileInfo = opts["defaultFileInfo"]
        self._authInfo = dict(
            [(k, v) for k, v in opts.items() if k in ["realm", "application_key_id", "application_key"]]
        )
        self._allowFileOverwrites = opts["allowFileOverwrites"]

        self._getAccountInfo = self._createAccountInfoCallable(opts)

        logger.info(f"{self.__class__.__name__} instantiated to use bucket {self._bucketName}")
        if opts["authorizeOnInit"]:
            logger.debug(f"{self.__class__.__name__} authorizing")
            self.b2Api
            if opts["validateOnInit"]:
                self._getOrCreateBucket(opts["nonExistentBucketDetails"])

    def _getDjangoSettingsOptions(self, kwargOpts: Dict) -> BackblazeB2StorageOptions:
        """Setting terminology taken from:
        https://b2-sdk-python.readthedocs.io/en/master/glossary.html#term-application-key-ID
        kwargOpts available for subclasses
        """
        from django.conf import settings

        if not hasattr(settings, "BACKBLAZE_CONFIG"):
            raise ImproperlyConfigured("add BACKBLAZE_CONFIG dict to django settings")
        if "application_key_id" not in settings.BACKBLAZE_CONFIG or "application_key" not in settings.BACKBLAZE_CONFIG:
            raise ImproperlyConfigured(
                "At minimum BACKBLAZE_CONFIG must contain auth 'application_key' and 'application_key_id'"
                f"\nfound: {settings.BACKBLAZE_CONFIG}"
            )
        self._validateOptions(settings.BACKBLAZE_CONFIG)
        opts = getDefaultB2StorageOptions()
        opts.update(settings.BACKBLAZE_CONFIG)  # type: ignore
        return opts

    def _validateOptions(self, options: Dict) -> None:
        unrecognizedOptions = [k for k in options.keys() if k not in getDefaultB2StorageOptions().keys()]
        if unrecognizedOptions:
            raise ImproperlyConfigured(f"Unrecognized options: {unrecognizedOptions}")

    def _createAccountInfoCallable(self, opts: BackblazeB2StorageOptions) -> Callable[[], AbstractAccountInfo]:
        if (
            not isinstance(opts["accountInfo"], dict)
            or "type" not in opts["accountInfo"]
            or opts["accountInfo"]["type"] not in ["memory", "sqlite", "django-cache"]
        ):
            raise ImproperlyConfigured(
                (f"accountInfo property must be a dict with type found in options.py, was {opts['accountInfo']}")
            )
        if opts["accountInfo"]["type"] == "django-cache":
            logger.debug(f"{self.__class__.__name__} will use {DjangoCacheAccountInfo.__name__}")
            return lambda: DjangoCacheAccountInfo(
                cacheName=cast(DjangoCacheAccountInfoConfig, opts["accountInfo"]).get("cache", "django-backblaze-b2")
            )
        elif opts["accountInfo"]["type"] == "memory":
            logger.debug(f"{self.__class__.__name__} will use {InMemoryAccountInfo.__name__}")
            return lambda: InMemoryAccountInfo()
        elif opts["accountInfo"]["type"] == "sqlite":
            logger.debug(f"{self.__class__.__name__} will use {SqliteAccountInfo.__name__}")
            return lambda: SqliteAccountInfo(
                file_name=cast(SqliteAccountInfoConfig, opts["accountInfo"])["databasePath"]
            )
        raise ImproperlyConfigured()

    @property
    def b2Api(self) -> B2Api:
        if not hasattr(self, "_b2Api"):
            self._accountInfo = self._getAccountInfo()
            self._b2Api = B2Api(account_info=self._accountInfo, cache=AuthInfoCache(self._accountInfo))
            self._b2Api.authorize_account(**self._authInfo)
        return self._b2Api

    @property
    def bucket(self) -> Bucket:
        if not hasattr(self, "_bucket"):
            self._getOrCreateBucket()
        return self._bucket

    def _getOrCreateBucket(self, newBucketDetails=None) -> None:
        try:
            self._bucket = self.b2Api.get_bucket_by_name(self._bucketName)
        except NonExistentBucket as e:
            if newBucketDetails is not None:
                logger.debug(f"Bucket {self._bucketName} not found. Creating with details: {newBucketDetails}")
                if "bucket_type" not in newBucketDetails:
                    newBucketDetails["bucket_type"] = "allPrivate"
                self._bucket = self.b2Api.create_bucket(name=self._bucketName, **newBucketDetails)
            else:
                raise e
        logger.debug(f"Connected to bucket {self._bucket.as_dict()}")

    def _open(self, name: str, mode: str) -> File:
        return B2File(
            name=name, bucket=self.bucket, fileInfos=self._defaultFileInfo, mode=mode, sizeProvider=self.size,
        )

    def _save(self, name: str, content: IO[Any]) -> str:
        """
        Save and retrieve the filename.
        If the file exists it will make another version of that file.
        """
        return B2File(
            name=name, bucket=self.bucket, fileInfos=self._defaultFileInfo, mode="w", sizeProvider=self.size,
        ).saveAndRetrieveFile(content)

    def path(self, name: str) -> str:
        return name

    def delete(self, name: str) -> None:
        try:
            fileInfo = self.bucket.get_file_info_by_name(name)
            logger.debug(f"Deleting file {name} id=({fileInfo.id_})")
            self.b2Api.delete_file_version(file_id=fileInfo.id_, file_name=name)
        except FileNotPresent:
            logger.debug("Not found")

    def exists(self, name: str) -> bool:
        try:
            self.bucket.get_file_info_by_name(name)
            return True
        except FileNotPresent:
            return False

    def size(self, name: str) -> int:
        fileInfo = self.bucket.get_file_info_by_name(name)
        return fileInfo.size if fileInfo.size is not None else 0

    def url(self, name: Optional[str]) -> str:
        if not name:
            raise Exception("Name must be defined")
        return self._getFileUrl(name)

    def _getFileUrl(self, name: str) -> str:
        return self.getBackblazeUrl(name)

    def getBackblazeUrl(self, filename: str) -> str:
        return self.b2Api.get_download_url_for_file_name(bucket_name=self._bucketName, file_name=filename)

    def get_available_name(self, name: str, max_length: Optional[int] = None) -> str:
        if self._allowFileOverwrites:
            return name
        return super().get_available_name(name, max_length)

    def listdir(self, path: str) -> Tuple[List[str], List[str]]:
        """
        List the contents of the specified path. Return a 2-tuple of lists:
        the first item being directories, the second item being files.
        """
        raise NotImplementedError("subclasses of Storage must provide a listdir() method")

    def get_accessed_time(self, name: str) -> datetime:
        """
        Return the last accessed time (as a datetime) of the file specified by
        name. The datetime will be timezone-aware if USE_TZ=True.
        """
        raise NotImplementedError("subclasses of Storage must provide a get_accessed_time() method")

    def get_created_time(self, name: str) -> datetime:
        """
        Return the creation time (as a datetime) of the file specified by name.
        The datetime will be timezone-aware if USE_TZ=True.
        """
        raise NotImplementedError("subclasses of Storage must provide a get_created_time() method")

    def get_modified_time(self, name: str) -> datetime:
        """
        Return the last modified time (as a datetime) of the file specified by
        name. The datetime will be timezone-aware if USE_TZ=True.
        """
        raise NotImplementedError("subclasses of Storage must provide a get_modified_time() method")


def merge(target: Dict, source: Dict, path=None) -> Dict:
    """merges b into a
    https://stackoverflow.com/a/7205107/11076240
    """
    if path is None:
        path = []
    for key in source:
        if key in target:
            printablePath = ".".join(path + [str(key)])
            if isinstance(target[key], dict) and isinstance(source[key], dict):
                merge(target[key], source[key], path + [str(key)])
            elif target[key] != source[key]:
                logger.debug(f"Overriding setting {printablePath} with value {source[key]}")
                target[key] = source[key]
        else:
            target[key] = source[key]
    return target
