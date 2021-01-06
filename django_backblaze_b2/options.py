from typing import Any, Dict, Optional, Union, cast

try:
    from typing import TypedDict
except Exception:
    from mypy_extensions import TypedDict


class ProxiedBucketNames(TypedDict):
    public: Optional[str]
    loggedIn: Optional[str]
    staff: Optional[str]


class BackblazeB2StorageOptions(TypedDict):
    """Configuration options."""

    realm: str  # default "production"
    application_key_id: str
    application_key: str
    bucket: str
    authorizeOnInit: bool
    validateOnInit: bool
    allowFileOverwrites: bool
    # see: https://b2-sdk-python.readthedocs.io/en/master/api/api.html#b2sdk.v1.B2Api.create_bucket
    nonExistentBucketDetails: Optional[Dict[str, Union[str, Dict[str, Any]]]]
    defaultFileInfo: Dict[str, Any]
    specificBucketNames: ProxiedBucketNames
    sqliteDatabase: str  # default unset


def getDefaultB2StorageOptions() -> BackblazeB2StorageOptions:
    return cast(
        BackblazeB2StorageOptions,
        {
            "realm": "production",
            "bucket": "django",
            "authorizeOnInit": True,
            "validateOnInit": True,
            "allowFileOverwrites": False,
            "nonExistentBucketDetails": None,
            "defaultFileInfo": {},
            "specificBucketNames": {"public": None, "loggedIn": None, "staff": None},
        },
    )
