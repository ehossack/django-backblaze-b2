from typing import Any, Dict, Optional, Union

from typing_extensions import Literal, TypedDict


class ProxiedBucketNames(TypedDict):
    public: Optional[str]
    loggedIn: Optional[str]
    staff: Optional[str]


class DjangoCacheAccountInfoConfig(TypedDict):
    type: Literal["django-cache"]
    cache: str


class InMemoryAccountInfoConfig(TypedDict):
    type: Literal["memory"]


class SqliteAccountInfoConfig(TypedDict):
    type: Literal["sqlite"]
    databasePath: str


class CDNConfig(TypedDict):
    baseUrl: str
    includeBucketUrlSegments: bool


class BackblazeB2StorageOptions(TypedDict):
    """Configuration options."""

    realm: str  # default "production"
    application_key_id: str
    application_key: str
    bucket: str
    authorizeOnInit: bool
    validateOnInit: bool
    allowFileOverwrites: bool
    accountInfo: Optional[Union[DjangoCacheAccountInfoConfig, InMemoryAccountInfoConfig, SqliteAccountInfoConfig]]
    forbidFilePropertyCaching: bool
    specificBucketNames: ProxiedBucketNames
    cdnConfig: Optional[CDNConfig]
    # see: https://b2-sdk-python.readthedocs.io/en/master/api/api.html#b2sdk.v1.B2Api.create_bucket
    nonExistentBucketDetails: Optional[Dict[str, Union[str, Dict[str, Any]]]]
    defaultFileInfo: Dict[str, Any]


def getDefaultB2StorageOptions() -> BackblazeB2StorageOptions:
    return {
        "realm": "production",
        "application_key_id": "you must set this value yourself",
        "application_key": "you must set this value yourself",
        "bucket": "django",
        "authorizeOnInit": True,
        "validateOnInit": True,
        "allowFileOverwrites": False,
        "accountInfo": {"type": "django-cache", "cache": "django-backblaze-b2"},
        "forbidFilePropertyCaching": False,
        "specificBucketNames": {"public": None, "loggedIn": None, "staff": None},
        "cdnConfig": None,
        "nonExistentBucketDetails": None,
        "defaultFileInfo": {},
    }
