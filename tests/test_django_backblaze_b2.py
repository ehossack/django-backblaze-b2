import datetime
import hashlib
import logging
from contextlib import contextmanager
from io import IOBase
from typing import Callable, Dict, Optional, Union
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
from django_backblaze_b2.storages import _SdkBucketDict

bucket = mock.create_autospec(spec=Bucket, name=f"Mock Bucket for {__name__}")
bucket.name = "bucketname"
download_version_factory = DownloadVersionFactory(mock.create_autospec(spec=B2Api, name=f"Mock API for {__name__}"))

sdk_public_bucket_dict: _SdkBucketDict = {"bucketType": "allPublic"}


def test_version():
    assert __version__ == "1.0.1"


@pytest.mark.django_db
def test_raises_no_exception_when_loading_model():
    error = None
    try:
        from tests.test_project.files.models import Files

        Files.objects.all().first()
    except Exception as e:
        error = e

    assert error is None, "Should not throw exception"


@pytest.mark.django_db
def test_uploads_bytes_to_bucket(tempfile):
    _mock_filedoesnotexist(tempfile)
    with _mocked_bucket(), mock.patch.object(
        B2Api, "get_download_url_for_file_name", return_value="http://randonneurs.bc.ca"
    ) as get_download_url:
        from tests.test_project.files.models import Files

        files_object = Files.objects.create(b2_storagefile=tempfile)
        _mock_fileexists(tempfile)

        assert files_object.b2_storagefile.size == tempfile.size
        assert files_object.b2_storagefile.url == "http://randonneurs.bc.ca"
        tempfile.seek(0)
        bucket.upload_bytes.assert_called_with(
            data_bytes=tempfile.read(),
            file_name=f"uploads/{tempfile.name}",
            file_info={},
        )
        get_download_url.assert_called_with(bucket_name="django", file_name=f"uploads/{tempfile.name}")


@pytest.mark.django_db
def test_deletes_from_bucket(tempfile):
    _mock_filedoesnotexist(tempfile)
    with _mocked_bucket(), mock.patch.object(B2Api, "delete_file_version") as deletion:
        from tests.test_project.files.models import Files

        files_object = Files.objects.create(b2_storagefile=tempfile)
        _mock_fileexists(tempfile)

        files_object.b2_storagefile.delete()

        deletion.assert_called_with(file_id="someId", file_name=f"uploads/{tempfile.name}")


@pytest.mark.django_db
def test_works_with_field_file_write_operation(tempfile):
    _mock_file_download(tempfile)

    with _file_info(size=tempfile.size):
        field_file = _get_file_from_new_files_model_object(tempfile)
        with field_file.open("w") as f:
            f.write("new-contents".encode("utf-8"))

        bucket.upload_bytes.assert_called_with(
            data_bytes=b"new-contents",
            file_name=f"uploads/{tempfile.name}",
            file_info={},
        )


@pytest.mark.django_db
def test_cannot_write_to_file_when_opened_in_read_mode(tempfile):
    with _file_info(size=tempfile.size):
        field_file = _get_file_from_new_files_model_object(tempfile)

        with pytest.raises(AttributeError) as error:
            opened = field_file.open("r")
            opened.write(b"blah")

        assert "File was not opened for write access." in str(error)


@pytest.mark.django_db
def test_can_read_file_contents(tempfile):
    _mock_file_download(tempfile)

    with _file_info(size=tempfile.size):
        field_file = _get_file_from_new_files_model_object(tempfile)

        file_contents = field_file.file.read()

        assert file_contents is not None
        assert str(file_contents) != ""


@pytest.mark.django_db
def test_storage_can_open_file(tempfile):
    _mock_file_download(tempfile)
    _mock_filedoesnotexist(tempfile)

    with _file_info(size=tempfile.size):
        from tests.test_project.files.models import Files

        files_object = Files.objects.create(b2_storagefile=tempfile)
        _mock_fileexists(tempfile)
        storage = Files._meta.get_field("b2_storagefile").storage
        b2_file = storage.open(files_object.b2_storagefile.name, "r")

        assert b2_file.size == tempfile.size


@pytest.mark.django_db
def test_generates_public_file_url(tempfile):
    _mock_filedoesnotexist(tempfile)
    with _mocked_bucket():
        from tests.test_project.files.models import Files

        files_object = Files.objects.create(public_file=tempfile)
        _mock_fileexists(tempfile)

        assert files_object.public_file.size == tempfile.size
        assert files_object.public_file.url == f"/b2/uploads/{tempfile.name}"


@pytest.mark.django_db
def test_generates_public_file_url_as_raw_b2_url():
    with _mocked_bucket(), mock.patch.object(bucket, "as_dict", return_value=sdk_public_bucket_dict), mock.patch.object(
        B2Api,
        "get_download_url_for_file_name",
        side_effect=lambda bucket_name, file_name: f"https://f000.backblazeb2.com/file/{bucket_name}/{file_name}",
    ) as get_download_url:
        from django_backblaze_b2 import PublicStorage

        storage = PublicStorage()

        assert storage.url("some/file.jpeg") == "https://f000.backblazeb2.com/file/django/some/file.jpeg"
        get_download_url.assert_called_with(bucket_name="django", file_name="some/file.jpeg")


@pytest.mark.django_db
def test_generates_public_file_url_as_cdn_url():
    with _mocked_bucket(), mock.patch.object(bucket, "as_dict", return_value=sdk_public_bucket_dict), mock.patch.object(
        B2Api,
        "get_download_url_for_file_name",
        side_effect=lambda bucket_name, file_name: f"https://f000.backblazeb2.com/file/{bucket_name}/{file_name}",
    ):
        from django_backblaze_b2 import PublicStorage

        storage = PublicStorage(
            opts={"cdn_config": {"base_url": "https://randonneurs.bc.ca", "include_bucket_url_segments": True}}
        )

        assert storage.url("some/file.jpeg") == "https://randonneurs.bc.ca/file/django/some/file.jpeg"


@pytest.mark.django_db
def test_generates_public_file_url_as_cdn_url_without_path():
    with _mocked_bucket(), mock.patch.object(bucket, "as_dict", return_value=sdk_public_bucket_dict), mock.patch.object(
        B2Api,
        "get_download_url_for_file_name",
        side_effect=lambda bucket_name, file_name: f"https://f000.backblazeb2.com/file/{bucket_name}/{file_name}",
    ):
        from django_backblaze_b2 import PublicStorage

        storage = PublicStorage(
            opts={"cdn_config": {"base_url": "https://s3.randonneurs.bc.ca", "include_bucket_url_segments": False}}
        )

        assert storage.url("some/file.jpeg") == "https://s3.randonneurs.bc.ca/some/file.jpeg"


@pytest.mark.django_db
def test_generates_public_file_with_retry_if_bucket_type_missing(caplog):
    caplog.set_level(logging.DEBUG, logger="django-backblaze-b2")
    counter = 0

    def get_dict() -> Union[_SdkBucketDict, Dict[str, None]]:
        nonlocal counter

        counter += 1
        if counter < 3:
            return {}
        return sdk_public_bucket_dict

    with _mocked_bucket(), mock.patch.object(bucket, "as_dict", side_effect=get_dict), mock.patch.object(
        B2Api,
        "get_download_url_for_file_name",
        side_effect=lambda bucket_name, file_name: f"https://f000.backblazeb2.com/file/{bucket_name}/{file_name}",
    ) as get_download_url:
        from django_backblaze_b2 import PublicStorage

        storage = PublicStorage()

        assert storage.url("some/file.jpeg") == "https://f000.backblazeb2.com/file/django/some/file.jpeg"
        get_download_url.assert_called_with(bucket_name="django", file_name="some/file.jpeg")
        assert ("django-backblaze-b2", 10, f"Re-retrieving bucket info for {str({})}") in caplog.record_tuples


@pytest.mark.django_db
def test_can_download_using_public_storage(tempfile, client: Client):
    _mock_file_download(tempfile)
    _mock_filedoesnotexist(tempfile)
    with _mocked_bucket():
        from tests.test_project.files.models import Files

        files_object = Files.objects.create(public_file=tempfile)
        _mock_fileexists(tempfile)
        response = client.get(files_object.public_file.url)

        assert isinstance(response, FileResponse)
        assert response.getvalue() == tempfile.file.read()


@pytest.mark.django_db
def test_requires_auth_for_logged_in_storage(tempfile, client: Client):
    _mock_file_download(tempfile)
    _mock_filedoesnotexist(tempfile)
    with _mocked_bucket():
        from tests.test_project.files.models import Files

        files_object = Files.objects.create(logged_in_file=tempfile)
        response = client.get(files_object.logged_in_file.url)

        assert response.status_code == 302
        assert response.get("Location") == f"/accounts/login/?next=/b2l/uploads/{tempfile}"


@pytest.mark.django_db
def test_requires_auth_for_staff_storage(tempfile, client: Client):
    _mock_file_download(tempfile)
    with _mocked_bucket():
        from tests.test_project.files.models import Files

        files_object = Files.objects.create(staff_file=tempfile)
        response = client.get(files_object.staff_file.url)

        assert response.status_code == 302
        assert response.get("Location") == f"/accounts/login/?next=/b2s/uploads/{tempfile}"


@pytest.mark.django_db
def test_requires_auth_for_staff_storage_when_logged_in(tempfile, client: Client):
    _mock_file_download(tempfile)
    with _mocked_bucket():
        from tests.test_project.files.models import Files

        user = User.objects.create_user(username="user", password="user", is_staff=False)
        files_object = Files.objects.create(staff_file=tempfile)
        client.force_login(user)
        response = client.get(files_object.staff_file.url)

        assert response.status_code == 401
        assert response.content == b"Unauthorized"


@pytest.mark.django_db
def test_can_download_using_logged_in_storage(tempfile, client: Client):
    _mock_file_download(tempfile)
    _mock_filedoesnotexist(tempfile)
    with _mocked_bucket():
        from tests.test_project.files.models import Files

        user = User.objects.create_user(username="user", password="user", is_staff=False)
        files_object = Files.objects.create(logged_in_file=tempfile)

        _mock_fileexists(tempfile)
        client.force_login(user)
        response = client.get(files_object.logged_in_file.url)

        assert isinstance(response, FileResponse)
        assert response.getvalue() == tempfile.file.read()


@pytest.mark.django_db
def test_can_download_using_staff_storage(tempfile, client: Client):
    _mock_file_download(tempfile)
    _mock_filedoesnotexist(tempfile)
    with _mocked_bucket():
        from tests.test_project.files.models import Files

        staff_user = User.objects.create_user(username="user", password="user", is_staff=True)
        files_object = Files.objects.create(staff_file=tempfile)

        _mock_fileexists(tempfile)
        client.force_login(staff_user)
        response = client.get(files_object.staff_file.url)

        assert isinstance(response, FileResponse)
        assert response.getvalue() == tempfile.file.read()


@pytest.mark.django_db
def test_appropriately_handles_non_extant_file(tempfile, client: Client, caplog):
    caplog.set_level(logging.DEBUG, logger="django-backblaze-b2")
    _mock_file_download(tempfile)
    _mock_filedoesnotexist(tempfile)
    with _mocked_bucket():
        from tests.test_project.files.models import Files

        files_object = Files.objects.create(public_file=tempfile)
        response = client.get(files_object.public_file.url)

        assert response.status_code == 404
        assert response.content.decode("utf-8") == f"Could not find file: uploads/{tempfile}"
        assert caplog.record_tuples == [
            ("django-backblaze-b2", 10, f"file info cache miss for uploads/{tempfile}"),
            ("django-backblaze-b2", 10, f"Saving uploads/{tempfile} to b2 bucket ({bucket.get_id()})"),
            (
                "django-backblaze-b2",
                10,
                (
                    "Initializing PublicStorage with options "
                    "{'realm': 'production', 'application_key_id': '<redacted>', "
                    "'application_key': '<redacted>', 'bucket': 'django', "
                    "'authorize_on_init': False, 'validate_on_init': False, 'allow_file_overwrites': False, "
                    "'account_info': {'type': 'django-cache', 'cache': 'django-backblaze-b2'}, "
                    "'forbid_file_property_caching': False, "
                    "'specific_bucket_names': {'public': None, 'logged_in': None, 'staff': None}, "
                    "'cdn_config': None, "
                    "'non_existent_bucket_details': None, "
                    "'default_file_info': {}"
                    "}"
                ),
            ),
            ("django-backblaze-b2", 10, "PublicStorage will use DjangoCacheAccountInfo"),
            ("django-backblaze-b2", 20, "PublicStorage instantiated to use bucket django"),
            ("django-backblaze-b2", 10, "Initializing DjangoCacheAccountInfo with cache 'django-backblaze-b2'"),
            ("django-backblaze-b2", 40, f"Debug log failed. Could not retrive b2 file url for uploads/{tempfile}"),
            ("django-backblaze-b2", 10, f"Connected to bucket {bucket.as_dict()}"),
            ("django-backblaze-b2", 10, f"file info cache miss for uploads/{tempfile}"),
            ("django.request", 30, f"Not Found: /b2/uploads/{tempfile}"),
        ]


@contextmanager
def _authorized_b2_connection():
    with mock.patch.object(B2Api, "authorize_account"):
        yield


@contextmanager
def _mocked_bucket():
    with _authorized_b2_connection(), mock.patch.object(B2Api, "get_bucket_by_name", return_value=bucket):
        yield


@contextmanager
def _file_info(
    size: Optional[int] = None,
    id: str = "someId",
    name: str = "someFile",
    does_file_exist: Optional[Callable[[], bool]] = None,
):
    def exist_or_throw():
        if does_file_exist():
            return _get_file_info_by_name_response(id, name, size)
        raise FileNotPresent()

    if does_file_exist is None:
        with mock.patch.object(bucket, "get_file_info_by_name", side_effect=FileNotPresent):
            yield
    else:
        with mock.patch.object(bucket, "get_file_info_by_name", new_callable=exist_or_throw):
            yield


def _get_file_from_new_files_model_object(tempfile: File) -> File:
    from tests.test_project.files.models import Files

    Files.objects.create(b2_storagefile=tempfile)
    files_object = Files.objects.all()[0]

    return files_object.b2_storagefile


def _mock_file_download(tempfile: File) -> None:
    def _download_file_factory(file_name):
        downloaded_file = mock.create_autospec(spec=DownloadedFile, name=f"Mock download for {__name__}")

        def save_into_bytes(file: IOBase, allow_seeking: bool = True):
            tempfile.seek(0)
            file.write(tempfile.read())
            tempfile.seek(0)

        downloaded_file.save.side_effect = save_into_bytes
        return downloaded_file

    bucket.download_file_by_name.side_effect = _download_file_factory


def _mock_filedoesnotexist(tempfile: File) -> None:
    bucket.get_file_info_by_name.side_effect = FileNotPresent


def _mock_fileexists(tempfile: File, b2_file_id: str = "someId") -> None:
    bucket.get_file_info_by_name.side_effect = None
    bucket.get_file_info_by_name.return_value = _get_file_info_by_name_response(
        b2_file_id, tempfile.name or "tempfile", tempfile.size
    )


def _get_file_info_by_name_response(file_id: str, file_name: str, file_size: Optional[int]) -> DownloadVersion:
    return download_version_factory.from_response_headers(
        {
            "x-bz-file-id": file_id,
            "x-bz-file-name": file_name,
            "Content-Length": file_size,
            # other required headers
            "x-bz-content-sha1": hashlib.sha1(file_name.encode()).hexdigest(),
            "content-type": "text/plain",
            "x-bz-upload-timestamp": (datetime.datetime.now() - datetime.timedelta(hours=1)).timestamp(),
        }
    )
