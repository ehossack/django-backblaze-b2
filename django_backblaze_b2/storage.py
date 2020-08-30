from datetime import datetime
from logging import getLogger
from typing import Dict, List, Optional, Tuple

from b2sdk.v1 import B2Api, Bucket, InMemoryAccountInfo
from b2sdk.v1.exception import NonExistentBucket
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

from django_backblaze_b2.b2_file import B2File

logger = getLogger("django-backblaze-b2")


@deconstructible
class BackblazeB2Storage(Storage):
    def __init__(self, **kwargs):
        """Setting terminology taken from:
        https://b2-sdk-python.readthedocs.io/en/master/glossary.html#term-application-key-ID
        """
        from django.conf import settings

        if not hasattr(settings, "BACKBLAZE_CONFIG"):
            raise ImproperlyConfigured("add BACKBLAZE_CONFIG dict to django settings")

        opts = {
            "realm": "production",
            "application_key_id": None,
            "application_key": None,
            "bucket": "django",
            "authorizeOnInit": True,
            "validateOnInit": True,
            "nonExistentBucketDetails": {},
            "defaultFileInfo": {},
        }
        opts.update(settings.BACKBLAZE_CONFIG)
        opts.update(kwargs.get("opts", {}))

        self._bucketName = opts["bucket"]
        self._defaultFileInfo = opts["defaultFileInfo"]
        self._authInfo = dict(
            [
                (k, v)
                for k, v in opts.items()
                if k in ["realm", "application_key_id", "application_key"]
            ]
        )

        if opts["authorizeOnInit"]:
            self.b2Api
            if opts["validateOnInit"]:
                self._getOrCreateBucket(opts["nonExistentBucketDetails"])

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

    def _getOrCreateBucket(self, newBucketDetails={}) -> None:
        try:
            self._bucket = self.b2Api.get_bucket_by_name(self._bucketName)
        except NonExistentBucket as e:
            if newBucketDetails:
                logger.debug(
                    f"Bucket {self._bucketName} not found. Creating with details: {newBucketDetails}"
                )
                if "bucket_type" not in newBucketDetails:
                    newBucketDetails["bucket_type"] = "allPrivate"
                self._bucket = self.b2Api.create_bucket(
                    name=self._bucketName, **newBucketDetails
                )
            else:
                raise e
        logger.debug(f"Connected to bucket {self._bucket.as_dict()}")

    def _open(self, name: str, mode: str) -> File:
        return B2File(
            name=name,
            bucket=self.bucket,
            fileInfos=self._defaultFileInfo,
            mode=mode,
            sizeProvider=self.size,
        )

    def path(self, name: str) -> str:
        return name

    def delete(self, name: str) -> None:
        fileId = FileMetaShim(self, name).id
        logger.debug(f"Deleting file {name} id=({fileId})")
        self.b2Api.delete_file_version(file_id=fileId, file_name=name)

    def exists(self, name: str) -> bool:
        try:
            FileMetaShim(self, name).as_dict()
            return True
        except Exception:
            return False

    def size(self, name: str) -> int:
        return FileMetaShim(self, name).contentLength

    def url(self, name: Optional[str]) -> str:
        if not name:
            raise Exception("Name must be defined")
        return self.b2Api.get_download_url_for_file_name(
            bucket_name=self._bucketName, file_name=name
        )

    def listdir(self, path: str) -> Tuple[List[str], List[str]]:
        """
        List the contents of the specified path. Return a 2-tuple of lists:
        the first item being directories, the second item being files.
        """
        raise NotImplementedError(
            "subclasses of Storage must provide a listdir() method"
        )

    def get_accessed_time(self, name: str) -> datetime:
        """
        Return the last accessed time (as a datetime) of the file specified by
        name. The datetime will be timezone-aware if USE_TZ=True.
        """
        raise NotImplementedError(
            "subclasses of Storage must provide a get_accessed_time() method"
        )

    def get_created_time(self, name: str) -> datetime:
        """
        Return the creation time (as a datetime) of the file specified by name.
        The datetime will be timezone-aware if USE_TZ=True.
        """
        raise NotImplementedError(
            "subclasses of Storage must provide a get_created_time() method"
        )

    def get_modified_time(self, name: str) -> datetime:
        """
        Return the last modified time (as a datetime) of the file specified by
        name. The datetime will be timezone-aware if USE_TZ=True.
        """
        raise NotImplementedError(
            "subclasses of Storage must provide a get_modified_time() method"
        )


class FileMetaShim:
    """
    Shim until you can get file info by name:
    https://github.com/Backblaze/b2-sdk-python/issues/143
    """

    def __init__(self, storage: BackblazeB2Storage, name: str) -> None:
        self._storage = storage
        self._filename = name

    @property
    def id(self) -> str:
        return self.as_dict()["x-bz-file-id"]

    @property
    def contentLength(self) -> int:
        return self.as_dict()["Content-Length"]

    def as_dict(self) -> Dict:
        if not hasattr(self, "_meta"):
            downloadUrl = self._storage.b2Api.session.get_download_url_by_name(
                self._storage._bucketName, self._filename
            )
            downloadAuthorization = self._storage.bucket.get_download_authorization(
                self._filename, 30
            )
            response = self._storage.b2Api.raw_api.b2_http.session.head(
                downloadUrl, headers={"Authorization": downloadAuthorization}
            )
            response.raise_for_status()
            self._meta = response.headers
        return self._meta
