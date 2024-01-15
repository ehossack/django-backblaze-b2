import logging
import random
import string

import pytest
from django.core.files import File


def randomword(length=5):
    letters = string.ascii_lowercase
    return "".join(random.choice(letters) for i in range(length))


@pytest.fixture()
def tempfile() -> File:
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(f"filename-{randomword()}.pdf", b"file-contents")  # must be bytestring


@pytest.fixture(autouse=True)
def debug_logging() -> None:
    logging.getLogger("django-backblaze-b2").setLevel(logging.DEBUG)
