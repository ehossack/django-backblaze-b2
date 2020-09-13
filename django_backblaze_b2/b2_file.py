from io import BytesIO
from logging import getLogger
from typing import IO, Any, Callable, Dict, Optional

from b2sdk.v1 import Bucket, DownloadDestBytes
from django.core.files.base import File

logger = getLogger("django-backblaze-b2")


class B2File(File):
    """Read/Write as lazy as possible"""

    def __init__(
        self, name: str, bucket: Bucket, sizeProvider: Callable[[str], int], fileInfos: Dict[str, str], mode: str,
    ):
        self.name: str = name
        self._bucket: Bucket = bucket
        self._sizeProvider = sizeProvider
        self._fileInfos = fileInfos
        self._mode: str = mode
        self._hasUnwrittenData: bool = False
        self._contents: Optional[IO] = None

    # https://github.com/python/mypy/issues/4125 -- kinda makes you wonder why we like mypy?
    @property  # type: ignore
    def file(self) -> IO[Any]:  # type: ignore
        if self._contents is None:
            data = self._readFileContents()
            self._contents = BytesIO(data)
        return self._contents

    # https://github.com/python/mypy/issues/1465
    @file.setter  # type: ignore
    def file(self, value: IO[Any]) -> None:
        self._contents = value

    def _readFileContents(self) -> bytes:
        download_dest = DownloadDestBytes()
        self._bucket.download_file_by_name(file_name=self.name, download_dest=download_dest)
        return download_dest.get_bytes_written()

    @property
    def size(self) -> int:
        if not hasattr(self, "_size"):
            self._size = self._sizeProvider(self.name)
        return self._size

    def read(self, num_bytes: Optional[int] = None) -> bytes:
        return self.file.read(num_bytes if isinstance(num_bytes, int) else -1)

    def write(self, content: bytes) -> int:
        if "w" not in self._mode:
            raise AttributeError("File was not opened for write access.")
        self.file = BytesIO(content)

        self._hasUnwrittenData = True
        return len(content)

    def close(self) -> None:
        if self._hasUnwrittenData:
            self.saveAndRetrieveFile(self.file)
        self.file.close()

    def saveAndRetrieveFile(self, content: IO[Any]) -> str:
        """
        Save and retrieve the filename.
        If the file exists it will make another version of that file.
        """
        logger.debug(f"Saving {self.name} to b2 bucket ({self._bucket.get_id()})")
        self._bucket.upload_bytes(
            data_bytes=content.read(), file_name=self.name, file_infos=self._fileInfos,
        )
        self._hasUnwrittenData = False
        return self.name
