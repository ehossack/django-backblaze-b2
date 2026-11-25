import sys
from contextlib import contextmanager, nullcontext
from importlib import import_module
from importlib.metadata import distribution
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import django
from b2sdk.v2 import B2Api, B2HttpApiConfig, InMemoryAccountInfo, RawSimulator
from django.conf import settings
from django.core.management import call_command


def main() -> None:
    with nullcontext() if "--live" in sys.argv else _simulated_bucket():
        django.setup()
        _verify_installed_package()
        call_command("check")
        call_command("makemigrations", "b2_file_app")
        call_command("migrate")
        call_command("createuser")
        call_command("test", "b2_file_app.live_tests", interactive=False)


@contextmanager
def _simulated_bucket() -> Iterator[None]:
    api = B2Api(InMemoryAccountInfo(), api_config=B2HttpApiConfig(_raw_api_class=RawSimulator))
    key_id, key = api.session.raw_api.create_account()
    api.authorize_account("production", key_id, key)
    api.create_bucket(settings.BACKBLAZE_CONFIG["bucket"], "allPrivate")
    settings.BACKBLAZE_CONFIG.update(application_key_id=key_id, application_key=key)
    with patch("django_backblaze_b2.storage.B2Api", return_value=api):
        yield


def _verify_installed_package() -> None:
    installed_package = distribution("django-backblaze-b2")
    package_directory = Path(str(installed_package.locate_file("django_backblaze_b2"))).resolve()
    imported_package = import_module("django_backblaze_b2")
    if imported_package.__file__ is None or Path(imported_package.__file__).resolve().parent != package_directory:
        raise RuntimeError("The sample app must import the installed distribution.")
    if not (package_directory / "py.typed").is_file():
        raise RuntimeError("The installed distribution must include py.typed.")


if __name__ == "__main__":
    main()
