import logging
import mimetypes
from typing import Union

from b2sdk.v1.exception import FileNotPresent
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseNotFound
from django.utils.translation import gettext_lazy as _
from django.views.decorators.clickjacking import xframe_options_sameorigin

from django_backblaze_b2 import storage, storages

from ._decorators import requiresLogin

logger = logging.getLogger("django-backblaze-b2")


@xframe_options_sameorigin
def downloadPublicFile(request: HttpRequest, filename: str) -> Union[HttpResponse, FileResponse]:
    """Serves the specified 'filename' without validating any authentication"""
    return _downloadFileFromStorage(storages.PublicStorage(), filename)


@requiresLogin()
@xframe_options_sameorigin
def downloadLoggedInFile(request: HttpRequest, filename: str) -> Union[HttpResponse, FileResponse]:
    """Serves the specified 'filename' validating the user is logged in"""
    return _downloadFileFromStorage(storages.LoggedInStorage(), filename)


@requiresLogin(requiresStaff=True)
@xframe_options_sameorigin
def downloadStaffFile(request: HttpRequest, filename: str) -> Union[HttpResponse, FileResponse]:
    """Serves the specified 'filename' validating the user is logged in and a staff user"""
    return _downloadFileFromStorage(storages.StaffStorage(), filename)


def _downloadFileFromStorage(storage: storage.BackblazeB2Storage, filename: str) -> Union[HttpResponse, FileResponse]:
    if logger.isEnabledFor(logging.DEBUG):
        try:
            logger.debug(f"Downloding file from {storage.getBackblazeUrl(filename)}")
        except Exception:
            logger.exception(f"Debug log failed. Could not retrive b2 file url for {filename}")

    try:
        if storage.exists(filename):
            return FileResponse(storage.open(filename, "r"), content_type=mimetypes.guess_type(filename))
    except (FileNotFoundError, FileNotPresent):
        logging.exception("Opening backblaze file failed")

    return HttpResponseNotFound(_("Could not find file") + f": {filename}")
