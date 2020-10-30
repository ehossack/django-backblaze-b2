from typing import Any, Dict, Literal, Optional, TypedDict, Union


class ProxiedBucketNames(TypedDict):
    public: Optional[str]
    loggedIn: Optional[str]
    staff: Optional[str]


class BackblazeB2StorageOptions(TypedDict):
    """Configuration options. Literals indicate defaults"""

    realm: Literal["production"]
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


def getDefaultB2StorageOptions() -> BackblazeB2StorageOptions:
    return {
        "realm": "production",
        "application_key_id": "---",
        "application_key": "---",
        "bucket": "django",
        "authorizeOnInit": True,
        "validateOnInit": True,
        "allowFileOverwrites": False,
        "nonExistentBucketDetails": None,
        "defaultFileInfo": {},
        "specificBucketNames": {"public": None, "loggedIn": None, "staff": None},
    }
