from typing import Any, Dict
from unittest import mock

import pytest
from b2sdk.v1 import B2Api
from b2sdk.v1.exception import NonExistentBucket
from django.core.exceptions import ImproperlyConfigured
from django_backblaze_b2 import BackblazeB2Storage
from django_backblaze_b2.b2_filemeta_shim import FileMetaShim
from requests import HTTPError, Response


def test_requiresConfiguration():
    with mock.patch("django.conf.settings", {}):

        with pytest.raises(ImproperlyConfigured) as error:
            BackblazeB2Storage()

        assert "add BACKBLAZE_CONFIG dict to django settings" in str(error)


def test_requiresConfigurationForAuth(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", {}):

        with pytest.raises(ImproperlyConfigured) as error:
            BackblazeB2Storage()

        assert ("At minimium BACKBLAZE_CONFIG must contain auth 'application_key' and 'application_key_id'") in str(
            error
        )


def test_explicitOptsTakePrecendenceOverDjangoConfig(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({"bucket": "uncool-bucket"})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name"):
        BackblazeB2Storage(opts={"bucket": "cool-bucket"})

        B2Api.get_bucket_by_name.assert_called_once_with("cool-bucket")


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
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name"), mock.patch.object(FileMetaShim, "exists", return_value=True):
        storage = BackblazeB2Storage(opts={"allowFileOverwrites": True})

        availableName = storage.get_available_name("some_name.txt", max_length=None)

        assert availableName == "some_name.txt"


def test_notImplementedMethods(settings):
    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})):
        storage = BackblazeB2Storage(opts={"authorizeOnInit": False})

        for method, callable in [
            ("listdir", lambda _: storage.listdir("/path")),
            ("get_accessed_time", lambda _: storage.get_accessed_time("/file.txt")),
            ("get_created_time", lambda _: storage.get_created_time("/file.txt")),
            ("get_modified_time", lambda _: storage.get_modified_time("/file.txt")),
        ]:
            with pytest.raises(NotImplementedError) as error:
                callable(None)

            assert f"subclasses of Storage must provide a {method}() method" in str(error)


def test_existsFileDoesNotExist(settings):
    fileMetaResponse = mock.Mock(spec=Response)
    fileMetaResponse.status_code = 404

    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name"), mock.patch.object(
        FileMetaShim, "as_dict", side_effect=HTTPError(response=fileMetaResponse)
    ):
        storage = BackblazeB2Storage(opts={})

        doesFileExist = storage.exists("some/file.txt")

        assert not doesFileExist


def test_existsServerError(settings):
    fileMetaResponse = mock.Mock(spec=Response)
    fileMetaResponse.status_code = 500

    with mock.patch.object(settings, "BACKBLAZE_CONFIG", _settingsDict({})), mock.patch.object(
        B2Api, "authorize_account"
    ), mock.patch.object(B2Api, "get_bucket_by_name"), mock.patch.object(
        FileMetaShim, "as_dict", side_effect=HTTPError(response=fileMetaResponse)
    ):
        storage = BackblazeB2Storage(opts={})

        with pytest.raises(HTTPError) as raised:
            storage.exists("some/file.txt")

        assert raised.value.response.status_code == 500


def _settingsDict(config: Dict[str, Any]) -> Dict[str, Any]:
    return {"application_key_id": "---", "application_key": "---", **config}
