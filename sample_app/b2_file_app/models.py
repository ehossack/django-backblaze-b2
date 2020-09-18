from django.db import models

from django_backblaze_b2 import BackblazeB2Storage, LoggedInStorage, PublicStorage, StaffStorage


class ModelWithFiles(models.Model):
    b2StorageFile = models.FileField(
        name="b2StorageFile",
        upload_to="uploads",
        verbose_name="B2 Storage File",
        storage=BackblazeB2Storage,  # type: ignore
        blank=True,
    )
    publicFile = models.FileField(
        name="publicFile",
        upload_to="uploads",
        verbose_name="Public File",
        storage=PublicStorage,  # type: ignore
        blank=True,
    )
    loggedInFile = models.FileField(
        name="loggedInFile",
        upload_to="uploads",
        verbose_name="Logged-In File",
        storage=LoggedInStorage,  # type: ignore
        blank=True,
    )
    staffFile = models.FileField(
        name="staffFile",
        upload_to="uploads",
        verbose_name="Staff-Only File",
        storage=StaffStorage,  # type: ignore
        blank=True,
    )

    def __str__(self) -> str:
        return (
            f"f={self.b2StorageFile or '<none>'}"
            f", p={self.publicFile or '<none>'}"
            f", li={self.loggedInFile or '<none>'}"
            f", s={self.staffFile or '<none>'}"
        )
