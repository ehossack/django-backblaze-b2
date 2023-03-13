import re
from typing import Dict, Optional, cast
from typing_extensions import TypedDict

from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from typing_extensions import Literal

from django_backblaze_b2.options import BackblazeB2StorageOptions, CDNConfig
from django_backblaze_b2.storage import BackblazeB2Storage, logger


class _SdkBucketDict(TypedDict):
    """See https://github.com/Backblaze/b2-sdk-python/blob/2c85182c82ee09b7db7216d70567aafb87f31536/b2sdk/bucket.py#L1148"""  # noqa: E501

    bucketType: Literal["allPublic", "allPrivate"]  # noqa: N815


class PublicStorage(BackblazeB2Storage):
    """
    Storage that requires no authentication to view.
    If the bucket is public, returns the bucket's url, or CDN if configured
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._bucket_type: Optional[Literal["allPublic", "allPrivate"]] = None
        self._cdn_config: Optional[CDNConfig] = kwargs.get("opts", {}).get("cdn_config")

    def _is_public_bucket(self) -> bool:
        if self._bucket_type is None:
            bucket_dict: _SdkBucketDict = self.bucket.as_dict()
            if bucket_dict.get("bucketType") is None:  # sometimes this happens due to cached values
                logger.debug(f"Re-retrieving bucket info for {bucket_dict}")
                self._refresh_bucket()
                bucket_dict = self.bucket.as_dict()
            self._bucket_type = bucket_dict.get("bucketType")
        return self._bucket_type == "allPublic"

    def _get_file_url(self, name: str) -> str:
        if not self._is_public_bucket():
            return reverse("django_b2_storage:b2-public", args=[name])
        if self._cdn_config:
            file_url = self.get_backblaze_url(name)
            cdn_url_base = self._cdn_config["base_url"].replace("https://", "").replace("http://", "").strip("/")
            if self._cdn_config["include_bucket_url_segments"]:
                return re.sub(r"f\d+\.backblazeb2\.com", cdn_url_base, file_url)
            return re.sub(r"f\d+\.backblazeb2\.com/file/[^/]+/", cdn_url_base + "/", file_url)
        return self.get_backblaze_url(name)

    def _get_django_settings_options(self, kwarg_opts: Dict) -> BackblazeB2StorageOptions:
        _validate_kwarg_opts(kwarg_opts)
        if kwarg_opts.get("cdn_config"):
            if not isinstance(kwarg_opts["cdn_config"], dict):
                raise ImproperlyConfigured("django-backblaze-b2 cdn_config must be a dict")
            if not isinstance(kwarg_opts["cdn_config"].get("base_url"), str):
                raise ImproperlyConfigured("cdn_config.base_url must be a string")
            if not isinstance(kwarg_opts["cdn_config"].get("include_bucket_url_segments"), bool):
                logger.debug("will treat cdn_config.include_bucket_url_segments to False")
        options = super()._get_django_settings_options(kwarg_opts)
        _adjust_options(options, specific_bucket="public")
        return options


class LoggedInStorage(BackblazeB2Storage):
    """Storage that requires authentication to view or download files"""

    def _get_file_url(self, name: str) -> str:
        return reverse("django_b2_storage:b2-logged-in", args=[name])

    def _get_django_settings_options(self, kwarg_opts: Dict) -> BackblazeB2StorageOptions:
        _validate_kwarg_opts(kwarg_opts)
        options = super()._get_django_settings_options(kwarg_opts)
        _adjust_options(options, specific_bucket="logged_in")
        return options


class StaffStorage(BackblazeB2Storage):
    """Storage that requires staff permission to view or download files"""

    def _get_file_url(self, name: str) -> str:
        return reverse("django_b2_storage:b2-staff", args=[name])

    def _get_django_settings_options(self, kwarg_opts: Dict) -> BackblazeB2StorageOptions:
        _validate_kwarg_opts(kwarg_opts)
        options = super()._get_django_settings_options(kwarg_opts)
        _adjust_options(options, specific_bucket="staff")
        return options


def _validate_kwarg_opts(kwarg_opts) -> None:
    if "bucket" in kwarg_opts:
        raise ImproperlyConfigured("May not specify 'bucket' in proxied storage class")
    if "application_key_id" in kwarg_opts or "application_key" in kwarg_opts or "realm" in kwarg_opts:
        raise ImproperlyConfigured("May not specify auth credentials in proxied storage class")


def _adjust_options(options: BackblazeB2StorageOptions, specific_bucket: str) -> None:
    proxied_storage_bucket_name = options.get("specific_bucket_names", {}).get(specific_bucket)
    if proxied_storage_bucket_name:
        options["bucket"] = cast(str, proxied_storage_bucket_name)
