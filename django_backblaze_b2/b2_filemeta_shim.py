from logging import getLogger

from b2sdk.exception import B2Error, interpret_b2_error
from b2sdk.v1 import B2Api, Bucket
from requests import HTTPError, Response
from requests.models import CaseInsensitiveDict

logger = getLogger("django-backblaze-b2")


class FileMetaShim:
    """
    Shim until you can get file info by name:
    https://github.com/Backblaze/b2-sdk-python/issues/143

    Internally, does a HEAD on the file's url.
    Caches the result in-memory for the lifetime of this object's existence
    """

    def __init__(self, b2Api: B2Api, bucketInstance: Bucket, filename: str) -> None:
        self._b2Api = b2Api
        self._bucket = bucketInstance
        self._filename = filename

    @property
    def id(self) -> str:
        return self.as_dict()["x-bz-file-id"]

    @property
    def contentLength(self) -> int:
        return self.as_dict()["Content-Length"]

    @property
    def exists(self) -> bool:
        try:
            self.as_dict()  # obtain meta via Http
            return True
        except HTTPError as e:
            if e.response.status_code == 404:
                return False
            try:
                raise interpret_b2_error(
                    e.response.status_code,
                    e.response.json().get("code"),
                    e.response.json().get("message"),
                    e.response.headers,
                )
            except B2Error:
                raise
            except Exception:
                logger.exception("Could not interpret b2 error")
                raise Exception(f"Status: {e.response.status_code}, Content: {e.response.content}")

    def as_dict(self) -> CaseInsensitiveDict:
        if not hasattr(self, "_meta"):
            logger.debug(f"HEAD bucket={self._bucket.name} file={self._filename}")
            head_attempts = 4
            for attempt in range(0, head_attempts):
                try:
                    self._meta = self._get_head_response().headers
                    return self._meta
                except HTTPError as e:
                    if attempt == 3 or e.response.status_code == 404:
                        raise
                    if not self._b2Api.authorize_automatically():
                        raise

            # try one last time
            self._meta = self._get_head_response().headers
        return self._meta

    def _get_head_response(self) -> Response:
        downloadUrl = self._b2Api.session.get_download_url_by_name(self._bucket.name, self._filename)
        downloadAuthorization = self._bucket.get_download_authorization(self._filename, 30)
        response = self._b2Api.raw_api.b2_http.session.head(
            downloadUrl, headers={"Authorization": downloadAuthorization}
        )
        response.raise_for_status()
        return response
