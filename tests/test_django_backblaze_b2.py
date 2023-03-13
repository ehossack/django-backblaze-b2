import datetime
import hashlib
import logging
from contextlib import contextmanager
from io import IOBase
from typing import Callable, Optional
from unittest import mock

import pytest
from b2sdk.api import B2Api, Bucket
from b2sdk.exception import FileNotPresent
from b2sdk.file_version import DownloadVersion, DownloadVersionFactory
from b2sdk.transfer.inbound.downloaded_file import DownloadedFile
from django.contrib.auth.models import User
from django.core.files import File
from django.http import FileResponse
from django.test import Client
from django_backblaze_b2 import __version__

bucket = mock.create_autospec(spec=Bucket, name=f"Mock Bucket for {__name__}")
bucket.name = "bucketname"
downloadVersionFactory = DownloadVersionFactory(mock.create_autospec(spec=B2Api, name=f"Mock API for {__name__}"))


def test_version():
    assert __version__ == "1.0.1"


@pytest.mark.django_db
def test_raisesNoExceptionWhenLoadingModel():
    error = None
    try:
        from tests.test_project.files.models import Files

        Files.objects.all().first()
    except Exception as e:
        error = e

    assert error is None, "Should not throw exception"


@pytest.mark.django_db
def test_uploadsBytesToBucket(tempFile):
    _mockFileDoesNotExist(tempFile)
    with _mockedBucket(), mock.patch.object(
        B2Api, "get_download_url_for_file_name", return_value="http://randonneurs.bc.ca"
    ) as getDownloadUrl:
        from tests.test_project.files.models import Files

        filesObject = Files.objects.create(b2StorageFile=tempFile)
        _mockFileExists(tempFile)

        assert filesObject.b2StorageFile.size == tempFile.size
        assert filesObject.b2StorageFile.url == "http://randonneurs.bc.ca"
        tempFile.seek(0)
        bucket.upload_bytes.assert_called_with(
            data_bytes=tempFile.read(),
            file_name=f"uploads/{tempFile.name}",
            file_infos={},
        )
        getDownloadUrl.assert_called_with(bucket_name="django", file_name=f"uploads/{tempFile.name}")


@pytest.mark.django_db
def test_deletesFromBucket(tempFile):
    _mockFileDoesNotExist(tempFile)
    with _mockedBucket(), mock.patch.object(B2Api, "delete_file_version") as deletion:
        from tests.test_project.files.models import Files

        filesObject = Files.objects.create(b2StorageFile=tempFile)
        _mockFileExists(tempFile)

        filesObject.b2StorageFile.delete()

        deletion.assert_called_with(file_id="someId", file_name=f"uploads/{tempFile.name}")


@pytest.mark.django_db
def test_worksWithFieldFileWriteOperation(tempFile):
    _mockFileDownload(tempFile)

    with _fileInfo(size=tempFile.size):

        fieldFile = _getFileFromNewFilesModelObject(tempFile)
        with fieldFile.open("w") as f:
            f.write("new-contents".encode("utf-8"))

        bucket.upload_bytes.assert_called_with(
            data_bytes=b"new-contents",
            file_name=f"uploads/{tempFile.name}",
            file_infos={},
        )


@pytest.mark.django_db
def test_cannotWriteToFileWhenOpenedInReadMode(tempFile):
    with _fileInfo(size=tempFile.size):
        fieldFile = _getFileFromNewFilesModelObject(tempFile)

        with pytest.raises(AttributeError) as error:
            opened = fieldFile.open("r")
            opened.write(b"blah")

        assert "File was not opened for write access." in str(error)


@pytest.mark.django_db
def test_canReadFileContents(tempFile):
    _mockFileDownload(tempFile)

    with _fileInfo(size=tempFile.size):
        fieldFile = _getFileFromNewFilesModelObject(tempFile)

        fileContents = fieldFile.file.read()

        assert fileContents is not None
        assert str(fileContents) != ""


@pytest.mark.django_db
def test_storageCanOpenFile(tempFile):
    _mockFileDownload(tempFile)
    _mockFileDoesNotExist(tempFile)

    with _fileInfo(size=tempFile.size):
        from tests.test_project.files.models import Files

        filesObject = Files.objects.create(b2StorageFile=tempFile)
        _mockFileExists(tempFile)
        storage = Files._meta.get_field("b2StorageFile").storage
        b2File = storage.open(filesObject.b2StorageFile.name, "r")

        assert b2File.size == tempFile.size


@pytest.mark.django_db
def test_generatesPublicFileUrl(tempFile):
    _mockFileDoesNotExist(tempFile)
    with _mockedBucket():
        from tests.test_project.files.models import Files

        filesObject = Files.objects.create(publicFile=tempFile)
        _mockFileExists(tempFile)

        assert filesObject.publicFile.size == tempFile.size
        assert filesObject.publicFile.url == f"/b2/uploads/{tempFile.name}"


@pytest.mark.django_db
def test_generatesPublicFileUrlAsRawB2Url():
    with _mockedBucket(), mock.patch.object(
        bucket, "as_dict", return_value={"bucketType": "allPublic"}
    ), mock.patch.object(
        B2Api,
        "get_download_url_for_file_name",
        side_effect=lambda bucket_name, file_name: f"https://f000.backblazeb2.com/file/{bucket_name}/{file_name}",
    ) as getDownloadUrl:
        from django_backblaze_b2 import PublicStorage

        storage = PublicStorage()

        assert storage.url("some/file.jpeg") == "https://f000.backblazeb2.com/file/django/some/file.jpeg"
        getDownloadUrl.assert_called_with(bucket_name="django", file_name="some/file.jpeg")


@pytest.mark.django_db
def test_generatesPublicFileUrlAsCDNUrl():
    with _mockedBucket(), mock.patch.object(
        bucket, "as_dict", return_value={"bucketType": "allPublic"}
    ), mock.patch.object(
        B2Api,
        "get_download_url_for_file_name",
        side_effect=lambda bucket_name, file_name: f"https://f000.backblazeb2.com/file/{bucket_name}/{file_name}",
    ):
        from django_backblaze_b2 import PublicStorage

        storage = PublicStorage(
            opts={"cdnConfig": {"baseUrl": "https://randonneurs.bc.ca", "includeBucketUrlSegments": True}}
        )

        assert storage.url("some/file.jpeg") == "https://randonneurs.bc.ca/file/django/some/file.jpeg"


@pytest.mark.django_db
def test_generatesPublicFileUrlAsCDNUrlWithoutPath():
    with _mockedBucket(), mock.patch.object(
        bucket, "as_dict", return_value={"bucketType": "allPublic"}
    ), mock.patch.object(
        B2Api,
        "get_download_url_for_file_name",
        side_effect=lambda bucket_name, file_name: f"https://f000.backblazeb2.com/file/{bucket_name}/{file_name}",
    ):
        from django_backblaze_b2 import PublicStorage

        storage = PublicStorage(
            opts={"cdnConfig": {"baseUrl": "https://s3.randonneurs.bc.ca", "includeBucketUrlSegments": False}}
        )

        assert storage.url("some/file.jpeg") == "https://s3.randonneurs.bc.ca/some/file.jpeg"


@pytest.mark.django_db
def test_generatesPublicFileWithRetryIfBucketTypeMissing(caplog):
    caplog.set_level(logging.DEBUG, logger="django-backblaze-b2")
    counter = 0

    def getDict() -> dict:
        nonlocal counter

        counter += 1
        if counter < 3:
            return {}
        return {"bucketType": "allPublic"}

    with _mockedBucket(), mock.patch.object(bucket, "as_dict", side_effect=getDict), mock.patch.object(
        B2Api,
        "get_download_url_for_file_name",
        side_effect=lambda bucket_name, file_name: f"https://f000.backblazeb2.com/file/{bucket_name}/{file_name}",
    ) as getDownloadUrl:
        from django_backblaze_b2 import PublicStorage

        storage = PublicStorage()

        assert storage.url("some/file.jpeg") == "https://f000.backblazeb2.com/file/django/some/file.jpeg"
        getDownloadUrl.assert_called_with(bucket_name="django", file_name="some/file.jpeg")
        assert ("django-backblaze-b2", 10, f"Re-retrieving bucket info for {str({})}") in caplog.record_tuples


@pytest.mark.django_db
def test_canDownloadUsingPublicStorage(tempFile, client: Client):
    _mockFileDownload(tempFile)
    _mockFileDoesNotExist(tempFile)
    with _mockedBucket():
        from tests.test_project.files.models import Files

        filesObject = Files.objects.create(publicFile=tempFile)
        _mockFileExists(tempFile)
        response = client.get(filesObject.publicFile.url)

        assert isinstance(response, FileResponse)
        assert response.getvalue() == tempFile.file.read()


@pytest.mark.django_db
def test_requiresAuthForLoggedInStorage(tempFile, client: Client):
    _mockFileDownload(tempFile)
    _mockFileDoesNotExist(tempFile)
    with _mockedBucket():
        from tests.test_project.files.models import Files

        filesObject = Files.objects.create(loggedInFile=tempFile)
        response = client.get(filesObject.loggedInFile.url)

        assert response.status_code == 302
        assert response.get("Location") == f"/accounts/login/?next=/b2l/uploads/{tempFile}"


@pytest.mark.django_db
def test_requiresAuthForStaffStorage(tempFile, client: Client):
    _mockFileDownload(tempFile)
    with _mockedBucket():
        from tests.test_project.files.models import Files

        filesObject = Files.objects.create(staffFile=tempFile)
        response = client.get(filesObject.staffFile.url)

        assert response.status_code == 302
        assert response.get("Location") == f"/accounts/login/?next=/b2s/uploads/{tempFile}"


@pytest.mark.django_db
def test_requiresAuthForStaffStorageWhenLoggedIn(tempFile, client: Client):
    _mockFileDownload(tempFile)
    with _mockedBucket():
        from tests.test_project.files.models import Files

        user = User.objects.create_user(username="user", password="user", is_staff=False)
        filesObject = Files.objects.create(staffFile=tempFile)
        client.force_login(user)
        response = client.get(filesObject.staffFile.url)

        assert response.status_code == 401
        assert response.content == b"Unauthorized"


@pytest.mark.django_db
def test_canDownloadUsingLoggedInStorage(tempFile, client: Client):
    _mockFileDownload(tempFile)
    _mockFileDoesNotExist(tempFile)
    with _mockedBucket():
        from tests.test_project.files.models import Files

        user = User.objects.create_user(username="user", password="user", is_staff=False)
        filesObject = Files.objects.create(loggedInFile=tempFile)

        _mockFileExists(tempFile)
        client.force_login(user)
        response = client.get(filesObject.loggedInFile.url)

        assert isinstance(response, FileResponse)
        assert response.getvalue() == tempFile.file.read()


@pytest.mark.django_db
def test_canDownloadUsingStaffStorage(tempFile, client: Client):
    _mockFileDownload(tempFile)
    _mockFileDoesNotExist(tempFile)
    with _mockedBucket():
        from tests.test_project.files.models import Files

        staffUser = User.objects.create_user(username="user", password="user", is_staff=True)
        filesObject = Files.objects.create(staffFile=tempFile)

        _mockFileExists(tempFile)
        client.force_login(staffUser)
        response = client.get(filesObject.staffFile.url)

        assert isinstance(response, FileResponse)
        assert response.getvalue() == tempFile.file.read()


@pytest.mark.django_db
def test_appropriatelyHandlesNonExtantFile(tempFile, client: Client, caplog):
    caplog.set_level(logging.DEBUG, logger="django-backblaze-b2")
    _mockFileDownload(tempFile)
    _mockFileDoesNotExist(tempFile)
    with _mockedBucket():
        from tests.test_project.files.models import Files

        filesObject = Files.objects.create(publicFile=tempFile)
        response = client.get(filesObject.publicFile.url)

        assert response.status_code == 404
        assert response.content.decode("utf-8") == f"Could not find file: uploads/{tempFile}"
        assert caplog.record_tuples == [
            ("django-backblaze-b2", 10, f"file info cache miss for uploads/{tempFile}"),
            ("django-backblaze-b2", 10, f"Saving uploads/{tempFile} to b2 bucket ({bucket.get_id()})"),
            (
                "django-backblaze-b2",
                10,
                (
                    "Initializing PublicStorage with options "
                    "{'realm': 'production', 'application_key_id': '<redacted>', "
                    "'application_key': '<redacted>', 'bucket': 'django', "
                    "'authorizeOnInit': False, 'validateOnInit': False, 'allowFileOverwrites': False, "
                    "'accountInfo': {'type': 'django-cache', 'cache': 'django-backblaze-b2'}, "
                    "'forbidFilePropertyCaching': False, "
                    "'specificBucketNames': {'public': None, 'loggedIn': None, 'staff': None}, "
                    "'cdnConfig': None, "
                    "'nonExistentBucketDetails': None, "
                    "'defaultFileInfo': {}"
                    "}"
                ),
            ),
            ("django-backblaze-b2", 10, "PublicStorage will use DjangoCacheAccountInfo"),
            ("django-backblaze-b2", 20, "PublicStorage instantiated to use bucket django"),
            ("django-backblaze-b2", 10, "Initializing DjangoCacheAccountInfo with cache 'django-backblaze-b2'"),
            ("django-backblaze-b2", 40, f"Debug log failed. Could not retrive b2 file url for uploads/{tempFile}"),
            ("django-backblaze-b2", 10, f"Connected to bucket {bucket.as_dict()}"),
            ("django-backblaze-b2", 10, f"file info cache miss for uploads/{tempFile}"),
            ("django.request", 30, f"Not Found: /b2/uploads/{tempFile}"),
        ]


@contextmanager
def _authorizedB2Connection():
    with mock.patch.object(B2Api, "authorize_account"):
        yield


@contextmanager
def _mockedBucket():
    with _authorizedB2Connection(), mock.patch.object(B2Api, "get_bucket_by_name", return_value=bucket):
        yield


@contextmanager
def _fileInfo(
    size: Optional[int] = None,
    id: str = "someId",
    name: str = "someFile",
    doesFileExist: Optional[Callable[[], bool]] = None,
):
    def existOrThrow():
        if doesFileExist():
            return _get_file_info_by_name_response(id, name, size)
        raise FileNotPresent()

    if doesFileExist is None:
        with mock.patch.object(bucket, "get_file_info_by_name", side_effect=FileNotPresent):
            yield
    else:
        with mock.patch.object(bucket, "get_file_info_by_name", new_callable=existOrThrow):
            yield


def _getFileFromNewFilesModelObject(tempFile: File) -> File:
    from tests.test_project.files.models import Files

    Files.objects.create(b2StorageFile=tempFile)
    filesObject = Files.objects.all()[0]

    return filesObject.b2StorageFile


def _mockFileDownload(tempFile: File) -> None:
    def downloadFileFactory(file_name):
        downloadedFile = mock.create_autospec(spec=DownloadedFile, name=f"Mock download for {__name__}")

        def saveIntoBytes(file: IOBase, allow_seeking: bool = True):
            tempFile.seek(0)
            file.write(tempFile.read())
            tempFile.seek(0)

        downloadedFile.save.side_effect = saveIntoBytes
        return downloadedFile

    bucket.download_file_by_name.side_effect = downloadFileFactory


def _mockFileDoesNotExist(tempFile: File) -> None:
    bucket.get_file_info_by_name.side_effect = FileNotPresent


def _mockFileExists(tempFile: File, b2FileId: str = "someId") -> None:
    bucket.get_file_info_by_name.side_effect = None
    bucket.get_file_info_by_name.return_value = _get_file_info_by_name_response(
        b2FileId, tempFile.name or "tempFile", tempFile.size
    )


def _get_file_info_by_name_response(fileId: str, fileName: str, fileSize: Optional[int]) -> DownloadVersion:
    return downloadVersionFactory.from_response_headers(
        {
            "x-bz-file-id": fileId,
            "x-bz-file-name": fileName,
            "Content-Length": fileSize,
            # other required headers
            "x-bz-content-sha1": hashlib.sha1(fileName.encode()).hexdigest(),
            "content-type": "text/plain",
            "x-bz-upload-timestamp": (datetime.datetime.now() - datetime.timedelta(hours=1)).timestamp(),
        }
    )
