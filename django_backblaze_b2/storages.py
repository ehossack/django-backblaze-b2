from typing import Dict, Optional, cast

from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse

from django_backblaze_b2.options import BackblazeB2StorageOptions
from django_backblaze_b2.storage import BackblazeB2Storage


class PublicStorage(BackblazeB2Storage):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bucketInfo: Optional[bool] = None

    def _isPublicBucket(self) -> bool:
        if self._bucketInfo is None:
            self._bucketInfo = self.bucket.as_dict().get("bucketType") == "allPublic"
        return self._bucketInfo

    def _getFileUrl(self, name: str) -> str:
        if self._isPublicBucket():
            return self.getBackblazeUrl(name)
        return reverse("django_b2_storage:b2-public", args=[name])

    def _getDjangoSettingsOptions(self, kwargOpts: Dict) -> BackblazeB2StorageOptions:
        _validateKwargOpts(kwargOpts)
        options = super()._getDjangoSettingsOptions(kwargOpts)
        _adjustOptions(options, specificBucket="public")
        return options


class LoggedInStorage(BackblazeB2Storage):
    def _getFileUrl(self, name: str) -> str:
        return reverse("django_b2_storage:b2-logged-in", args=[name])

    def _getDjangoSettingsOptions(self, kwargOpts: Dict) -> BackblazeB2StorageOptions:
        _validateKwargOpts(kwargOpts)
        options = super()._getDjangoSettingsOptions(kwargOpts)
        _adjustOptions(options, specificBucket="loggedIn")
        return options


class StaffStorage(BackblazeB2Storage):
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
