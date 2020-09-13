from contextlib import contextmanager
from typing import Optional
from unittest import mock

import pytest
from b2sdk.v1 import B2Api, Bucket
from django.core.files import File

from django_backblaze_b2 import __version__
from django_backblaze_b2.b2_filemeta_shim import FileMetaShim

bucket = mock.Mock(spec_set=Bucket)


def test_version():
    assert __version__ == "0.1.0"


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

    with _mockedBucket(), _fileMeta(size=tempFile.size), mock.patch.object(
        B2Api, "get_download_url_for_file_name", return_value="http://randonneurs.bc.ca"
    ) as getDownloadUrl:
        from tests.test_project.files.models import Files

        filesObject = Files.objects.create(publicFile=tempFile)

        assert filesObject.publicFile.size == tempFile.size
        assert filesObject.publicFile.url == "http://randonneurs.bc.ca"
        tempFile.seek(0)
        bucket.upload_bytes.assert_called_with(
            data_bytes=tempFile.read(), file_name=f"uploads/{tempFile.name}", file_infos={},
        )
        getDownloadUrl.assert_called_with(bucket_name="django", file_name=f"uploads/{tempFile.name}")


@pytest.mark.django_db
def test_deletesFromBucket(tempFile):

    with _mockedBucket(), _fileMeta(size=tempFile.size, id="someId"), mock.patch.object(
        B2Api, "delete_file_version"
    ) as deletion:
        from tests.test_project.files.models import Files

        filesObject = Files.objects.create(publicFile=tempFile)
        filesObject.publicFile.delete()

        deletion.assert_called_with(file_id="someId", file_name=f"uploads/{tempFile.name}")


@pytest.mark.django_db
def test_worksWithFieldFileWriteOperation(tempFile):
    _mockFileDownload(tempFile)

    with _fileMeta(size=tempFile.size):

        fieldFile = _getFileFromNewFilesModelObject(tempFile)
        with fieldFile.open("w") as f:
            f.write("new-contents".encode("utf-8"))

        bucket.upload_bytes.assert_called_with(
            data_bytes=b"new-contents", file_name=f"uploads/{tempFile.name}", file_infos={},
        )


@pytest.mark.django_db
def test_cannotWriteToFileWhenOpenedInReadMode(tempFile):
    with _fileMeta(size=tempFile.size):
        fieldFile = _getFileFromNewFilesModelObject(tempFile)

        with pytest.raises(AttributeError) as error:
            opened = fieldFile.open("r")
            opened.write(b"blah")

        assert "File was not opened for write access." in str(error)


@pytest.mark.django_db
def test_canReadFileContents(tempFile):
    _mockFileDownload(tempFile)

    with _fileMeta(size=tempFile.size):
        fieldFile = _getFileFromNewFilesModelObject(tempFile)

        fileContents = fieldFile.file.read()

        assert fileContents is not None
        assert str(fileContents) != ""


@pytest.mark.django_db
def test_storageCanOpenFile(tempFile):
    _mockFileDownload(tempFile)

    with _fileMeta(size=tempFile.size):
        from tests.test_project.files.models import Files

        filesObject = Files.objects.create(publicFile=tempFile)
        storage = Files._meta.get_field("publicFile").storage
        b2File = storage.open(filesObject.publicFile.name, "r")

        assert b2File.size == tempFile.size


@contextmanager
def _authorizedB2Connection():
    with mock.patch.object(B2Api, "authorize_account"):
        yield


@contextmanager
def _mockedBucket():
    with _authorizedB2Connection(), mock.patch.object(B2Api, "get_bucket_by_name", return_value=bucket):
        yield


@contextmanager
def _fileMeta(size: Optional[int] = None, id: str = "someId"):
    def getSize():
        if size is not None:
            return size
        raise Exception("need size")

    with mock.patch.object(
        FileMetaShim,
        "exists",
        new_callable=mock.PropertyMock,
        return_value=False,  # it's easier for our tests to assume false,
        # because django will try to generate a new name if true
        # https://github.com/django/django/blob/3.1.1/django/core/files/storage.py#L82
    ), mock.patch.object(FileMetaShim, "contentLength", new_callable=getSize,), mock.patch.object(
        FileMetaShim, "id", new_callable=mock.PropertyMock, return_value=id,
    ):
        yield


def _getFileFromNewFilesModelObject(tempFile: File) -> File:
    from tests.test_project.files.models import Files

    Files.objects.create(publicFile=tempFile)
    filesObject = Files.objects.all()[0]

    return filesObject.publicFile


def _mockFileDownload(tempFile: File) -> None:
    def downloadByName(file_name, download_dest):
        if file_name.endswith(tempFile.name):
            tempFile.seek(0)
            download_dest.bytes_written = tempFile.read()
            return None

    bucket.download_file_by_name.side_effect = downloadByName
