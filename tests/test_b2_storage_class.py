import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from unittest import mock

import pytest
from b2sdk.account_info.exception import CorruptAccountInfo
from b2sdk.api import B2Api, Bucket
from b2sdk.exception import FileNotPresent, NonExistentBucket
from b2sdk.file_version import DownloadVersion, DownloadVersionFactory
from django.core.exceptions import ImproperlyConfigured
from django_backblaze_b2 import BackblazeB2Storage
from django_backblaze_b2.cache_account_info import DjangoCacheAccountInfo

downloadVersionFactory = DownloadVersionFactory(mock.create_autospec(spec=B2Api, name=f"Mock API for {__name__}"))


def test_requiresConfiguration():
    with mock.patch("django.conf.settings", {}):

        with pytest.raises(ImproperlyConfigured) as error:
            BackblazeB2Storage()

        assert "add BACKBLAZE_CONFIG dict to django settings" in str(error)


def test_requiresConfigurationForAuth(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", {}):

        with pytest.raises(ImproperlyConfigured) as error:
            BackblazeB2Storage()

        assert ("At minimum BACKBLAZE_CONFIG must contain auth 'application_key' and 'application_key_id'") in str(
            error
        )


def test_explicitOptsTakePrecendenceOverDjangoConfig(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({"bucket": "uncool-bucket"})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name"):
        BackblazeB2Storage(opts={"bucket": "cool-bucket"})

        B2Api.get_bucket_by_name.assert_called_once_with("cool-bucket")


def test_complainsWithUnrecognizedOptions(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name"):

        with pytest.raises(ImproperlyConfigured) as error:
            BackblazeB2Storage(opts={"unrecognized": "option"})

        assert str(error.value) == "Unrecognized options: ['unrecognized']"


def test_defaultsToAuthorizeOnInit(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name"):
        BackblazeB2Storage(opts={})

        B2Api.authorize_account.assert_called_once_with(
            realm="production", application_key_id="---", application_key="---"
        )


def test_defaultsToValidateInit(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name"):
        BackblazeB2Storage(opts={})

        B2Api.get_bucket_by_name.assert_called_once_with("django")


def test_defaultsToNotCreatingBucket(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name", side_effect=NonExistentBucket):

        with pytest.raises(NonExistentBucket):
            BackblazeB2Storage(opts={})

        B2Api.get_bucket_by_name.assert_called_once_with("django")


def test_canCreateBucket(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name", side_effect=NonExistentBucket), mock.patch.object(
        B2Api, "create_bucket"
    ):

        BackblazeB2Storage(opts={"nonExistentBucketDetails": {}})

        B2Api.get_bucket_by_name.assert_called_once_with("django")
        B2Api.create_bucket.assert_called_once_with(name="django", bucket_type="allPrivate")


def test_lazyAuthorization(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name"):

        storage = BackblazeB2Storage(opts={"authorizeOnInit": False})
        B2Api.authorize_account.assert_not_called()
        B2Api.get_bucket_by_name.assert_not_called()

        storage.open("/some/file.txt", "r")
        B2Api.authorize_account.assert_called_once_with(
            realm="production", application_key_id="---", application_key="---"
        )


def test_cachedAccountInfo(settings):
    cacheName = "test-cache"
    bucket = mock.MagicMock()
    bucket.name = "django"
    bucket.id_ = "django-bucket-id"
    cacheAccountInfo = DjangoCacheAccountInfo(cacheName)
    cacheAccountInfo.set_auth_data(
        "account-id",
        "auth-token",
        "api-url",
        "download-url",
        "recommended-part-size",
        "absolute-minimum-part-size",
        "application-key",
        "realm",
        "http://s3.api.url",
        dict(
            bucketId=None,
            bucketName=None,
            capabilities=["readFiles"],
            namePrefix=None,
        ),
        "application-key-id",
    )
    cacheAccountInfo.save_bucket(bucket)

    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "list_buckets"):

        BackblazeB2Storage(opts={"accountInfo": {"type": "django-cache", "cache": cacheName}})

        B2Api.list_buckets.assert_not_called()


def test_lazyBucketNonExistent(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name", side_effect=NonExistentBucket):

        storage = BackblazeB2Storage(opts={"validateOnInit": False})
        B2Api.get_bucket_by_name.assert_not_called()

        with pytest.raises(NonExistentBucket):
            storage.open("/some/file.txt", "r")
        B2Api.get_bucket_by_name.assert_called()


def test_nameUsesLiteralFilenameAsPath(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})):
        storage = BackblazeB2Storage(opts={"authorizeOnInit": False})

        assert storage.path("some/file.txt") == "some/file.txt"


def test_urlRequiresName(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})):
        storage = BackblazeB2Storage(opts={"authorizeOnInit": False})

        with pytest.raises(Exception) as error:
            storage.url(name=None)

        assert "Name must be defined" in str(error)


def test_get_available_nameWithOverwrites(settings):
    mockedBucket = mock.Mock(spec=Bucket)
    mockedBucket.get_file_info_by_name.return_value = _get_file_info_by_name_response(
        1, "some_name.txt", fileSize=12345
    )
    mockedBucket.name = "bucket"

    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name") as api:
        api.return_value = mockedBucket
        storage = BackblazeB2Storage(opts={"allowFileOverwrites": True})

        availableName = storage.get_available_name("some_name.txt", max_length=None)

        assert availableName == "some_name.txt"


def test_get_created_time(settings):
    currentUTCTimeMillis = round(time.time() * 1000)
    mockedBucket = mock.Mock(spec=Bucket)
    mockedBucket.get_file_info_by_name.return_value = _get_file_info_by_name_response(
        1, "some_name.txt", fileSize=12345, timestamp=currentUTCTimeMillis
    )
    mockedBucket.name = "bucket"

    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name") as api:
        api.return_value = mockedBucket
        storage = BackblazeB2Storage()

        createdTime = storage.get_created_time("some_name.txt")

        assert createdTime == datetime.utcfromtimestamp(currentUTCTimeMillis / 1000).replace(tzinfo=timezone.utc)


def test_get_modified_time(settings):
    currentUTCTimeMillis = round(time.time() * 1000)
    mockedBucket = mock.Mock(spec=Bucket)
    mockedBucket.get_file_info_by_name.return_value = _get_file_info_by_name_response(
        1, "some_name.txt", fileSize=12345, timestamp=currentUTCTimeMillis
    )
    mockedBucket.name = "bucket"

    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name") as api:
        api.return_value = mockedBucket
        storage = BackblazeB2Storage()

        modifiedTime = storage.get_modified_time("some_name.txt")

        assert modifiedTime == datetime.utcfromtimestamp(currentUTCTimeMillis / 1000).replace(tzinfo=timezone.utc)
        assert modifiedTime == storage.get_created_time("some_name.txt")


def test_get_size_without_caching(settings):
    currentUTCTimeMillis = round(time.time() * 1000)
    mockedBucket = mock.Mock(spec=Bucket)
    mockedBucket.get_file_info_by_name.return_value = _get_file_info_by_name_response(
        1, "some_name.txt", fileSize=12345, timestamp=currentUTCTimeMillis
    )
    mockedBucket.name = "bucket"

    with mock.patch.object(
        settings, "BACKBLAZE_CONFIG", _settingsDict({"forbidFilePropertyCaching": True})
    ), mock.patch.object(B2Api, "authorize_account"), mock.patch.object(B2Api, "get_bucket_by_name") as api:
        api.return_value = mockedBucket
        storage = BackblazeB2Storage()

        size = storage.size("some_name.txt")

        assert size == 12345


def test_notImplementedMethods(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})):
        storage = BackblazeB2Storage(opts={"authorizeOnInit": False})

        for method, callable in [
            ("listdir", lambda _: storage.listdir("/path")),
            ("get_accessed_time", lambda _: storage.get_accessed_time("/file.txt")),
        ]:
            with pytest.raises(NotImplementedError) as error:
                callable(None)

            assert f"subclasses of Storage must provide a {method}() method" in str(error)


def test_existsFileDoesNotExist(settings):
    mockedBucket = mock.Mock(spec=Bucket)
    mockedBucket.name = "bucketname"
    mockedBucket.get_file_info_by_name.side_effect = FileNotPresent()

    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name") as api:
        api.return_value = mockedBucket
        storage = BackblazeB2Storage(opts={})

        doesFileExist = storage.exists("some/file.txt")

        assert not doesFileExist
        assert mockedBucket.get_file_info_by_name.call_count == 1


def test_canUseSqliteAccountInfo(settings, tmpdir, caplog):
    caplog.set_level(logging.DEBUG, logger="django-backblaze-b2")
    tempFile = tmpdir.mkdir("sub").join("database.sqlite3")
    tempFile.write("some-invalid-context")
    with mock.patch.object(
        settings, "BACKBLAZE_CONFIG", _settingsDict({"accountInfo": {"type": "sqlite", "databasePath": str(tempFile)}})
    ), mock.patch.object(B2Api, "authorize_account"), mock.patch.object(B2Api, "get_bucket_by_name"):

        with pytest.raises(CorruptAccountInfo) as error:
            BackblazeB2Storage(opts={})

        assert str(tempFile) in str(error.value)
        assert ("django-backblaze-b2", 10, "BackblazeB2Storage will use SqliteAccountInfo") in caplog.record_tuples


def _settingsDict(config: Dict[str, Any]) -> Dict[str, Any]:
    return {"application_key_id": "---", "application_key": "---", **config}


def _get_file_info_by_name_response(
    fileId: str,
    fileName: str,
    fileSize: Optional[int],
    timestamp: float = (datetime.now() - timedelta(hours=1)).timestamp(),
) -> DownloadVersion:
    return downloadVersionFactory.from_response_headers(
        {
            "x-bz-file-id": fileId,
            "x-bz-file-name": fileName,
            "Content-Length": fileSize,
            # other required headers
            "x-bz-content-sha1": hashlib.sha1(fileName.encode()),
            "content-type": "text/plain",
            "x-bz-upload-timestamp": timestamp,
        }
    )
