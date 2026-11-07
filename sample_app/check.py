from importlib import import_module
from importlib.metadata import distribution
from pathlib import Path

import django
from django.conf import settings
from django.core.management import call_command


def main() -> None:
    settings.BACKBLAZE_CONFIG.update(validate_on_init=False, authorize_on_init=False)
    django.setup()

    _verify_installed_package()
    call_command("check")
    call_command("makemigrations", "b2_file_app")
    call_command("migrate")
    call_command("createuser")


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
