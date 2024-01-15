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

download_version_factory = DownloadVersionFactory(mock.create_autospec(spec=B2Api, name=f"Mock API for {__name__}"))


def test_requires_configuration():
    with mock.patch("django.conf.settings", {}):
        with pytest.raises(ImproperlyConfigured) as error:
            BackblazeB2Storage()

        assert "add BACKBLAZE_CONFIG dict to django settings" in str(error)


def test_requires_configuration_for_auth(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", {}):
        with pytest.raises(ImproperlyConfigured) as error:
            BackblazeB2Storage()

        assert ("At minimum BACKBLAZE_CONFIG must contain auth 'application_key' and 'application_key_id'") in str(
            error
        )


def test_explicit_opts_take_precedence_over_django_config(settings):
    with mock.patch.object(
        settings, "BACKBLAZE_CONFIG", _settings_dict({"bucket": "uncool-bucket"})
    ), mock.patch.object(B2Api, "authorize_account"), mock.patch.object(B2Api, "get_bucket_by_name"):
        BackblazeB2Storage(opts={"bucket": "cool-bucket"})

        B2Api.get_bucket_by_name.assert_called_once_with("cool-bucket")


def test_complains_with_unrecognized_options(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name"):
        with pytest.raises(ImproperlyConfigured) as error:
            BackblazeB2Storage(opts={"unrecognized": "option"})

        assert str(error.value) == "Unrecognized options: ['unrecognized']"


def test_kwargs_take_precedence_over_django_config(settings):
    with mock.patch.object(
        settings, "BACKBLAZE_CONFIG", _settings_dict({"bucket": "uncool-bucket"})
    ), mock.patch.object(B2Api, "authorize_account"), mock.patch.object(B2Api, "get_bucket_by_name"):
        BackblazeB2Storage(bucket="cool-bucket")

        B2Api.get_bucket_by_name.assert_called_once_with("cool-bucket")


def test_complains_with_opts_and_kwargs(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name"):
        with pytest.raises(ImproperlyConfigured) as error:
            BackblazeB2Storage(bucket="cool-bucket", opts={"allow_file_overwrites": True})

        assert str(error.value) == "Can only specify opts or keyword args, not both!"


def test_defaults_to_authorize_on_init(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name"):
        BackblazeB2Storage(opts={})

        B2Api.authorize_account.assert_called_once_with(
            realm="production", application_key_id="---", application_key="---"
        )


def test_defaults_to_validate_init(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name"):
        BackblazeB2Storage(opts={})

        B2Api.get_bucket_by_name.assert_called_once_with("django")


def test_defaults_to_not_creating_bucket(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name", side_effect=NonExistentBucket):
        with pytest.raises(NonExistentBucket):
            BackblazeB2Storage(opts={})

        B2Api.get_bucket_by_name.assert_called_once_with("django")


def test_can_create_bucket(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name", side_effect=NonExistentBucket), mock.patch.object(
        B2Api, "create_bucket"
    ):
        BackblazeB2Storage(opts={"non_existent_bucket_details": {}})

        B2Api.get_bucket_by_name.assert_called_once_with("django")
        B2Api.create_bucket.assert_called_once_with(name="django", bucket_type="allPrivate")


def test_lazy_authorization(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name"):
        storage = BackblazeB2Storage(opts={"authorize_on_init": False})
        B2Api.authorize_account.assert_not_called()
        B2Api.get_bucket_by_name.assert_not_called()

        storage.open("/some/file.txt", "r")
        B2Api.authorize_account.assert_called_once_with(
            realm="production", application_key_id="---", application_key="---"
        )


def test_cached_account_info(settings):
    cache_name = "test-cache"
    bucket = mock.MagicMock()
    bucket.name = "django"
    bucket.id_ = "django-bucket-id"
    cache_account_info = DjangoCacheAccountInfo(cache_name)
    cache_account_info.set_auth_data(
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
    cache_account_info.save_bucket(bucket)

    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "list_buckets"):
        BackblazeB2Storage(opts={"account_info": {"type": "django-cache", "cache": cache_name}})

        B2Api.list_buckets.assert_not_called()


def test_lazy_bucket_non_existent(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name", side_effect=NonExistentBucket):
        storage = BackblazeB2Storage(opts={"validate_on_init": False})
        B2Api.get_bucket_by_name.assert_not_called()

        with pytest.raises(NonExistentBucket):
            storage.open("/some/file.txt", "r")
        B2Api.get_bucket_by_name.assert_called()


def test_name_uses_literal_filename_as_path(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})):
        storage = BackblazeB2Storage(opts={"authorize_on_init": False})

        assert storage.path("some/file.txt") == "some/file.txt"


def test_url_requires_name(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})):
        storage = BackblazeB2Storage(opts={"authorize_on_init": False})

        with pytest.raises(Exception) as error:
            storage.url(name=None)

        assert "Name must be defined" in str(error)


def test_get_available_name_with_overwrites(settings):
    mocked_bucket = mock.Mock(spec=Bucket)
    mocked_bucket.get_file_info_by_name.return_value = _get_file_info_by_name_response(
        1, "some_name.txt", file_size=12345
    )
    mocked_bucket.name = "bucket"

    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name") as api:
        api.return_value = mocked_bucket
        storage = BackblazeB2Storage(opts={"allow_file_overwrites": True})

        available_name = storage.get_available_name("some_name.txt", max_length=None)

        assert available_name == "some_name.txt"


def test_get_created_time(settings):
    current_utc_time_millis = round(time.time() * 1000)
    mocked_bucket = mock.Mock(spec=Bucket)
    mocked_bucket.get_file_info_by_name.return_value = _get_file_info_by_name_response(
        1, "some_name.txt", file_size=12345, timestamp=current_utc_time_millis
    )
    mocked_bucket.name = "bucket"

    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name") as api:
        api.return_value = mocked_bucket
        storage = BackblazeB2Storage()

        created_time = storage.get_created_time("some_name.txt")

        assert created_time == datetime.fromtimestamp(current_utc_time_millis / 1000, timezone.utc)


def test_get_modified_time(settings):
    current_utc_time_millis = round(time.time() * 1000)
    mocked_bucket = mock.Mock(spec=Bucket)
    mocked_bucket.get_file_info_by_name.return_value = _get_file_info_by_name_response(
        1, "some_name.txt", file_size=12345, timestamp=current_utc_time_millis
    )
    mocked_bucket.name = "bucket"

    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name") as api:
        api.return_value = mocked_bucket
        storage = BackblazeB2Storage()

        modified_time = storage.get_modified_time("some_name.txt")

        assert modified_time == datetime.fromtimestamp(current_utc_time_millis / 1000, timezone.utc)
        assert modified_time == storage.get_created_time("some_name.txt")


def test_get_size_without_caching(settings):
    current_utc_time_millis = round(time.time() * 1000)
    mocked_bucket = mock.Mock(spec=Bucket)
    mocked_bucket.get_file_info_by_name.return_value = _get_file_info_by_name_response(
        1, "some_name.txt", file_size=12345, timestamp=current_utc_time_millis
    )
    mocked_bucket.name = "bucket"

    with mock.patch.object(
        settings, "BACKBLAZE_CONFIG", _settings_dict({"forbid_file_property_caching": True})
    ), mock.patch.object(B2Api, "authorize_account"), mock.patch.object(B2Api, "get_bucket_by_name") as api:
        api.return_value = mocked_bucket
        storage = BackblazeB2Storage()

        size = storage.size("some_name.txt")

        assert size == 12345


def test_not_implemented_methods(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})):
        storage = BackblazeB2Storage(opts={"authorize_on_init": False})

        for method, callable in [
            ("listdir", lambda _: storage.listdir("/path")),
            ("get_accessed_time", lambda _: storage.get_accessed_time("/file.txt")),
        ]:
            with pytest.raises(NotImplementedError) as error:
                callable(None)

            assert f"subclasses of Storage must provide a {method}() method" in str(error)


def test_exists_file_does_not_exist(settings):
    mocked_bucket = mock.Mock(spec=Bucket)
    mocked_bucket.name = "bucketname"
    mocked_bucket.get_file_info_by_name.side_effect = FileNotPresent()

    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name") as api:
        api.return_value = mocked_bucket
        storage = BackblazeB2Storage(opts={})

        does_file_exist = storage.exists("some/file.txt")

        assert not does_file_exist
        assert mocked_bucket.get_file_info_by_name.call_count == 1


def test_can_use_sqlite_account_info(settings, tmpdir, caplog):
    caplog.set_level(logging.DEBUG, logger="django-backblaze-b2")
    tempfile = tmpdir.mkdir("sub").join("database.sqlite3")
    tempfile.write("some-invalid-context")
    with mock.patch.object(
        settings,
        "BACKBLAZE_CONFIG",
        _settings_dict({"account_info": {"type": "sqlite", "database_path": str(tempfile)}}),
    ), mock.patch.object(B2Api, "authorize_account"), mock.patch.object(B2Api, "get_bucket_by_name"):
        with pytest.raises(CorruptAccountInfo) as error:
            BackblazeB2Storage(opts={})

        assert str(tempfile) in str(error.value)
        assert ("django-backblaze-b2", 10, "BackblazeB2Storage will use SqliteAccountInfo") in caplog.record_tuples


def _settings_dict(config: Dict[str, Any]) -> Dict[str, Any]:
    return {"application_key_id": "---", "application_key": "---", **config}


def _get_file_info_by_name_response(
    file_id: str,
    file_name: str,
    file_size: Optional[int],
    timestamp: float = (datetime.now() - timedelta(hours=1)).timestamp(),
) -> DownloadVersion:
    return download_version_factory.from_response_headers(
        {
            "x-bz-file-id": file_id,
            "x-bz-file-name": file_name,
            "Content-Length": file_size,
            # other required headers
            "x-bz-content-sha1": hashlib.sha1(file_name.encode()).hexdigest(),
            "content-type": "text/plain",
            "x-bz-upload-timestamp": timestamp,
        }
    )
