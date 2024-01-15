from django.db import models

from django_backblaze_b2 import LoggedInStorage, PublicStorage, StaffStorage


class Files(models.Model):
    b2_storagefile = models.FileField(name="b2_storagefile", upload_to="uploads", verbose_name="B2 Storage File")
    public_file = models.FileField(
        name="public_file",
        upload_to="uploads",
        verbose_name="Public File",
        storage=PublicStorage,
    )
    logged_in_file = models.FileField(
        name="logged_in_file",
        upload_to="uploads",
        verbose_name="Logged-In File",
        storage=LoggedInStorage,
    )
    staff_file = models.FileField(
        name="staff_file",
        upload_to="uploads",
        verbose_name="Staff-Only File",
        storage=StaffStorage,
    )

    def __str__(self) -> str:
        return (
            f"f={self.b2_storagefile}, p={self.public_file.url}, li={self.logged_in_file.url}, s={self.staff_file.url}"
        )
