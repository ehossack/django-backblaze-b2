from django.db import models

from django_backblaze_b2 import AdminStorage, LoggedInStorage, PublicStorage


class Files(models.Model):
    publicFile = models.FileField(
        name="publicFile", upload_to="uploads", verbose_name="Public File", storage=PublicStorage,  # type: ignore
    )
    loggedInFile = models.FileField(
        name="loggedInFile",
        upload_to="uploads",
        verbose_name="Logged-In File",
        storage=LoggedInStorage,  # type: ignore
    )
    adminFile = models.FileField(
        name="adminFile", upload_to="uploads", verbose_name="Admin-Only File", storage=AdminStorage,  # type: ignore
    )

    def __str__(self) -> str:
        return f"p={self.publicFile.url}, li={self.loggedInFile.url}, a={self.adminFile.url}"
