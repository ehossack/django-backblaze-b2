from typing import Any, Dict
from unittest import mock

import pytest
from b2sdk.v2 import B2Api
from django.core.exceptions import ImproperlyConfigured
from typing_extensions import Type

from django_backblaze_b2 import BackblazeB2Storage
from django_backblaze_b2.storages import LoggedInStorage, PublicStorage, StaffStorage


@pytest.mark.parametrize(
    "specific_bucket_key,storageclass",
    [("public", PublicStorage), ("logged_in", LoggedInStorage), ("staff", StaffStorage)],
)
def test_can_get_bucket_name_from_specific_bucket_names(
    specific_bucket_key: str, storageclass: Type[BackblazeB2Storage], request: pytest.FixtureRequest
):
    settings = request.getfixturevalue("settings")
    with (
        mock.patch.object(
            settings,
            "BACKBLAZE_CONFIG",
            _settings_dict({"specific_bucket_names": {specific_bucket_key: "this-bucket"}}),
        ),
        mock.patch.object(B2Api, "authorize_account"),
        mock.patch.object(B2Api, "get_bucket_by_name") as b2_api_get_bucket_by_name,
    ):
        storageclass(validate_on_init=True)
        BackblazeB2Storage(validate_on_init=True)  # ensure it uses default still

        assert b2_api_get_bucket_by_name.call_count == 2
        b2_api_get_bucket_by_name.assert_any_call("this-bucket")
        b2_api_get_bucket_by_name.assert_any_call("django")


@pytest.mark.parametrize("storageclass", [PublicStorage, LoggedInStorage, StaffStorage])
def test_complains_with_supplied_bucket_name_in_proxy_class(
    storageclass: Type[BackblazeB2Storage], request: pytest.FixtureRequest
):
    settings = request.getfixturevalue("settings")
    with (
        mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})),
        mock.patch.object(B2Api, "authorize_account"),
        mock.patch.object(B2Api, "get_bucket_by_name"),
    ):
        with pytest.raises(ImproperlyConfigured) as error:
            storageclass(bucket="supplied")

        assert str(error.value) == "May not specify 'bucket' in proxied storage class"


@pytest.mark.parametrize("storageclass", [PublicStorage, LoggedInStorage, StaffStorage])
@pytest.mark.parametrize("auth_arg", ["application_key_id", "application_key", "realm"])
def test_complains_with_supplied_auth_config_in_proxy_class(
    storageclass: Type[BackblazeB2Storage], auth_arg: str, request: pytest.FixtureRequest
):
    settings = request.getfixturevalue("settings")
    with (
        mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})),
        mock.patch.object(B2Api, "authorize_account"),
        mock.patch.object(B2Api, "get_bucket_by_name"),
    ):
        with pytest.raises(ImproperlyConfigured) as error:
            # typecheck complains on dynamic type with TypedDict
            storageclass(opts={auth_arg: "supplied"})  # type: ignore[misc]

        assert str(error.value) == "May not specify auth credentials in proxied storage class"


@pytest.mark.parametrize(
    "specific_bucket_key,storageclass",
    [("public", PublicStorage), ("logged_in", LoggedInStorage), ("staff", StaffStorage)],
)
def test_can_supply_specific_bucket_names(
    specific_bucket_key: str, storageclass: Type[BackblazeB2Storage], request: pytest.FixtureRequest
):
    settings = request.getfixturevalue("settings")
    with (
        mock.patch.object(settings, "BACKBLAZE_CONFIG", _settings_dict({})),
        mock.patch.object(B2Api, "authorize_account"),
        mock.patch.object(B2Api, "get_bucket_by_name") as b2_api_get_bucket_by_name,
    ):
        # typecheck complains on dynamic type with TypedDict
        storageclass(validate_on_init=True, specific_bucket_names={specific_bucket_key: "bucket-in-args"})  # type: ignore[misc]

        b2_api_get_bucket_by_name.assert_called_with("bucket-in-args")


def _settings_dict(config: Dict[str, Any]) -> Dict[str, Any]:
    return {"application_key_id": "---", "application_key": "---", **config}
