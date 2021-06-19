import re
from typing import Dict, Optional, cast

from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from typing_extensions import Literal

from django_backblaze_b2.options import BackblazeB2StorageOptions, CDNConfig
from django_backblaze_b2.storage import BackblazeB2Storage, logger


class PublicStorage(BackblazeB2Storage):
    """
    Storage that requires no authentication to view.
    If the bucket is public, returns the bucket's url, or CDN if configured
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bucketType: Optional[Literal["allPublic", "allPrivate"]] = None
        self._cdnConfig: Optional[CDNConfig] = kwargs.get("opts", {}).get("cdnConfig")

    def _isPublicBucket(self) -> bool:
        if self._bucketType is None:
            bucketDict = self.bucket.as_dict()
            if bucketDict.get("bucketType") is None:  # sometimes this happens due to cached values
                logger.debug(f"Re-retrieving bucket info for {bucketDict}")
                self._refreshBucket()
                bucketDict = self.bucket.as_dict()
            self._bucketType = bucketDict.get("bucketType")
        return self._bucketType == "allPublic"

    def _getFileUrl(self, name: str) -> str:
        if not self._isPublicBucket():
            return reverse("django_b2_storage:b2-public", args=[name])
        if self._cdnConfig:
            fileUrl = self.getBackblazeUrl(name)
            cdnUrlBase = self._cdnConfig["baseUrl"].replace("https://", "").replace("http://", "").strip("/")
            if self._cdnConfig["includeBucketUrlSegments"]:
                return re.sub(r"f\d+\.backblazeb2\.com", cdnUrlBase, fileUrl)
            return re.sub(r"f\d+\.backblazeb2\.com/file/[^/]+/", cdnUrlBase + "/", fileUrl)
        return self.getBackblazeUrl(name)

    def _getDjangoSettingsOptions(self, kwargOpts: Dict) -> BackblazeB2StorageOptions:
        _validateKwargOpts(kwargOpts)
        if kwargOpts.get("cdnConfig"):
            if not isinstance(kwargOpts["cdnConfig"], dict):
                raise ImproperlyConfigured("django-backblaze-b2 cdnConfig must be a dict")
            if not isinstance(kwargOpts["cdnConfig"].get("baseUrl"), str):
                raise ImproperlyConfigured("cdnConfig.baseUrl must be a string")
            if not isinstance(kwargOpts["cdnConfig"].get("includeBucketUrlSegments"), bool):
                logger.debug("will treat cdnConfig.includeBucketUrlSegments to False")
        options = super()._getDjangoSettingsOptions(kwargOpts)
        _adjustOptions(options, specificBucket="public")
        return options


class LoggedInStorage(BackblazeB2Storage):
    """Storage that requires authentication to view or download files"""

    def _getFileUrl(self, name: str) -> str:
        return reverse("django_b2_storage:b2-logged-in", args=[name])

    def _getDjangoSettingsOptions(self, kwargOpts: Dict) -> BackblazeB2StorageOptions:
        _validateKwargOpts(kwargOpts)
        options = super()._getDjangoSettingsOptions(kwargOpts)
        _adjustOptions(options, specificBucket="loggedIn")
        return options


class StaffStorage(BackblazeB2Storage):
    """Storage that requires staff permission to view or download files"""

    def _getFileUrl(self, name: str) -> str:
        return reverse("django_b2_storage:b2-staff", args=[name])

    def _getDjangoSettingsOptions(self, kwargOpts: Dict) -> BackblazeB2StorageOptions:
        _validateKwargOpts(kwargOpts)
        options = super()._getDjangoSettingsOptions(kwargOpts)
        _adjustOptions(options, specificBucket="staff")
        return options


def _validateKwargOpts(kwargOpts) -> None:
    if "bucket" in kwargOpts:
        raise ImproperlyConfigured("May not specify 'bucket' in proxied storage class")
    if "application_key_id" in kwargOpts or "application_key" in kwargOpts or "realm" in kwargOpts:
        raise ImproperlyConfigured("May not specify auth credentials in proxied storage class")


def _adjustOptions(options: BackblazeB2StorageOptions, specificBucket: str) -> None:
    proxiedStorageBucketName = options.get("specificBucketNames", {}).get(specificBucket)
    if proxiedStorageBucketName:
        options["bucket"] = cast(str, proxiedStorageBucketName)
