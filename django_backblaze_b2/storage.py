from datetime import datetime
from logging import getLogger
from typing import IO, Any, Dict, List, Optional, Tuple

from b2sdk.v1 import B2Api, Bucket, InMemoryAccountInfo
from b2sdk.v1.exception import FileNotPresent, NonExistentBucket
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

from django_backblaze_b2.b2_file import B2File
from django_backblaze_b2.b2_filemeta_shim import FileMetaShim
from django_backblaze_b2.options import BackblazeB2StorageOptions, getDefaultB2StorageOptions

logger = getLogger("django-backblaze-b2")


@deconstructible
class BackblazeB2Storage(Storage):
    """Storage class which fulfills the Django Storage contract through b2 apis"""

    def __init__(self, **kwargs):
        opts = self._getDjangoSettingsOptions(kwargs.get("opts", {}))
        opts.update(kwargs.get("opts", {}))

        self._bucketName = opts["bucket"]
        self._defaultFileInfo = opts["defaultFileInfo"]
        self._authInfo = dict(
            [(k, v) for k, v in opts.items() if k in ["realm", "application_key_id", "application_key"]]
        )
        self._allowFileOverwrites = opts["allowFileOverwrites"]

        logger.info(f"{self.__class__.__name__} instantiated to use bucket {self._bucketName}")
        if opts["authorizeOnInit"]:
            logger.debug(f"{self.__class__.__name__} authorizing")
            self.b2Api
            if opts["validateOnInit"]:
                self._getOrCreateBucket(opts["nonExistentBucketDetails"])

    def _getDjangoSettingsOptions(self, kwargOpts: Dict) -> BackblazeB2StorageOptions:
        """Setting terminology taken from:
        https://b2-sdk-python.readthedocs.io/en/master/glossary.html#term-application-key-ID
        """
        from django.conf import settings

        if not hasattr(settings, "BACKBLAZE_CONFIG"):
            raise ImproperlyConfigured("add BACKBLAZE_CONFIG dict to django settings")
        if "application_key_id" not in settings.BACKBLAZE_CONFIG or "application_key" not in settings.BACKBLAZE_CONFIG:
            raise ImproperlyConfigured(
                "At minimium BACKBLAZE_CONFIG must contain auth 'application_key' and 'application_key_id'"
                f"\nfound: {settings.BACKBLAZE_CONFIG}"
            )
        opts = getDefaultB2StorageOptions()
        opts.update(settings.BACKBLAZE_CONFIG)  # type: ignore
        return opts

    @property
    def b2Api(self) -> B2Api:
        if not hasattr(self, "_b2Api"):
            self._accountInfo = InMemoryAccountInfo()
            self._b2Api = B2Api(self._accountInfo)
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
            fileId = FileMetaShim(self.b2Api, self.bucket, name).id
            logger.debug(f"Deleting file {name} id=({fileId})")
            self.b2Api.delete_file_version(file_id=fileId, file_name=name)
        except FileNotPresent:
            logger.debug("Not found")

    def exists(self, name: str) -> bool:
        return FileMetaShim(self.b2Api, self.bucket, name).exists

    def size(self, name: str) -> int:
        return FileMetaShim(self.b2Api, self.bucket, name).contentLength

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
