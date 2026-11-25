from uuid import uuid4

import requests
from django.core.management import call_command
from django.db.models import FileField
from django.test import LiveServerTestCase

from .models import ModelWithFiles


class SampleAppDownloads(LiveServerTestCase):
    def test_public_upload_and_download(self) -> None:
        with requests.Session() as browser:
            self._upload(browser, "public_file", b"public sample")
            saved_file = ModelWithFiles.objects.get().public_file

            response = browser.get(self.live_server_url + "/b2/" + saved_file.name, timeout=30)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"public sample")

    def _upload(self, browser: requests.Session, field: str, contents: bytes) -> None:
        filename = f"ci-{uuid4().hex}.txt"
        file_field = ModelWithFiles._meta.get_field(field)
        assert isinstance(file_field, FileField)
        self.addCleanup(file_field.storage.delete, f"uploads/{filename}")
        index = self.live_server_url + "/"
        browser.get(index, timeout=30).raise_for_status()
        response = browser.post(
            index,
            data={"csrfmiddlewaretoken": browser.cookies["csrftoken"]},
            files={field: (filename, contents)},
            timeout=60,
        )
        self.assertEqual(response.status_code, 200)
        saved_file = getattr(ModelWithFiles.objects.get(), field)
        self.assertEqual(saved_file.name, f"uploads/{filename}")
        self.assertIn(f'href="{saved_file.url}"', response.text)

    def test_staff_upload_and_download(self) -> None:
        call_command("createuser")
        with requests.Session() as browser:
            self._upload(browser, "staff_file", b"staff sample")
            url = self.live_server_url + ModelWithFiles.objects.get().staff_file.url

            anonymous = browser.get(url, allow_redirects=False, timeout=30)
            self._login_as_staff(browser)
            authenticated = browser.get(url, allow_redirects=False, timeout=30)

            self.assertEqual(anonymous.status_code, 302)
            self.assertTrue(anonymous.headers["Location"].startswith("/admin/login/?next="))
            self.assertEqual(authenticated.status_code, 200)
            self.assertEqual(authenticated.content, b"staff sample")

    def _login_as_staff(self, browser: requests.Session) -> None:
        login_url = self.live_server_url + "/admin/login/"
        browser.get(login_url, timeout=30).raise_for_status()
        response = browser.post(
            login_url,
            data={"username": "staff", "password": "staff", "csrfmiddlewaretoken": browser.cookies["csrftoken"]},
            allow_redirects=False,
            timeout=30,
        )
        self.assertEqual(response.status_code, 302)
