from django.db import models
from django_backblaze_b2 import LoggedInStorage, PublicStorage, StaffStorage


class Files(models.Model):
    b2StorageFile = models.FileField(name="b2StorageFile", upload_to="uploads", verbose_name="B2 Storage File")
    publicFile = models.FileField(
        name="publicFile",
        upload_to="uploads",
        verbose_name="Public File",
        storage=PublicStorage,  # type: ignore
    )
    loggedInFile = models.FileField(
        name="loggedInFile",
        upload_to="uploads",
        verbose_name="Logged-In File",
        storage=LoggedInStorage,  # type: ignore
    )
    staffFile = models.FileField(
        name="staffFile",
        upload_to="uploads",
        verbose_name="Staff-Only File",
        storage=StaffStorage,  # type: ignore
    )

    def __str__(self) -> str:
        return f"f={self.b2StorageFile}, p={self.publicFile.url}, li={self.loggedInFile.url}, s={self.staffFile.url}"
