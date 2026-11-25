import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from shlex import join, quote, split
from tempfile import TemporaryDirectory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--pypi-only", action="store_true")
    args = parser.parse_args()

    try:
        release(args.uv, args.pypi_only)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Release failed: {error}", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nRelease cancelled.", file=sys.stderr)
        return 1
    return 0


def release(uv: str, pypi_only: bool) -> None:
    commit = check_main()
    current_version = output(f"{quote(uv)} version --short --no-cache")
    repository = ""
    can_create_release = False
    already_released = False
    if not pypi_only:
        remote_url = output("git remote get-url --push origin")
        repo_info = json.loads(output(f"gh repo view {quote(remote_url)} --json nameWithOwner,viewerPermission"))
        repository = repo_info["nameWithOwner"]
        can_create_release = repo_info["viewerPermission"] in {"ADMIN", "MAINTAIN", "WRITE"}
        already_released = github_release_exists(repository, current_version)

    released_today = already_released and tag_is_from_today(current_version)
    version = choose_version(current_version, already_released, released_today)
    if version is None:
        return
    if not pypi_only and not can_create_release:
        raise RuntimeError(f"The active gh account cannot create releases in {repository}. Check gh auth status.")
    existing_tag = check_release_tag(repository, current_version, version, commit)
    notes = input("Release Description: ")
    if check_worktree() != commit:
        raise RuntimeError("Local main changed during the release. Review the changes before retrying.")
    if version != current_version:
        commit = commit_version(uv, current_version, version)
        run(f"git push origin {quote(commit)}:refs/heads/main")

    publish(uv, version, notes, commit, existing_tag)
    if not pypi_only:
        run(f"gh release create {quote(version)} --repo {quote(repository)} --verify-tag --notes={quote(notes)}")


def check_main() -> str:
    commit = check_worktree()
    run("git fetch --tags origin refs/heads/main:refs/remotes/origin/main")
    if commit != output("git rev-parse refs/remotes/origin/main"):
        raise RuntimeError("Local main must match origin/main. Review the difference and sync before retrying.")
    return commit


def check_worktree() -> str:
    if output("git branch --show-current") != "main":
        raise RuntimeError("Run the release from main.")
    if output("git status --porcelain"):
        raise RuntimeError("The working tree must be clean.")
    return output("git rev-parse HEAD")


def github_release_exists(repository: str, version: str) -> bool:
    endpoint = f"repos/{repository}/releases/tags/{version}"
    result = subprocess.run(split(f"gh api --include {quote(endpoint)}"), capture_output=True, text=True)
    if result.returncode == 0:
        return True
    status_line = result.stdout.partition("\n")[0].split()
    if len(status_line) >= 2 and status_line[0].startswith("HTTP/") and status_line[1] == "404":
        return False
    raise RuntimeError(f"GitHub release lookup for {version} failed: {result.stderr.strip()}")


def tag_is_from_today(version: str) -> bool:
    timestamp = output(f"git tag --list --format=%(creatordate:unix) {quote(version)}")
    return bool(timestamp) and date.fromtimestamp(int(timestamp)) == date.today()


def check_release_tag(repository: str, current_version: str, version: str, commit: str) -> bool:
    existing_tag = bool(output(f"git tag --list {quote(version)}"))
    if version != current_version:
        if existing_tag or github_release_exists(repository, version):
            raise RuntimeError(f"Version {version} already has a tag or GitHub release.")
    elif existing_tag and output(f"git rev-parse refs/tags/{quote(version)}^{{commit}}") != commit:
        raise RuntimeError(f"Tag {version} points to a different commit. Resolve the tag before continuing.")
    return existing_tag


def choose_version(current_version: str, already_released: bool, released_today: bool) -> str | None:
    if not already_released:
        return current_version if confirm(f"Release {current_version}?") else None
    if released_today:
        print(f"Version {current_version} was released today.")
    if not confirm("Bump version?"):
        return None

    version = input(f"Current version is {current_version}. Enter new version: ").strip()
    if version_parts(version) <= version_parts(current_version):
        raise RuntimeError("Version must increase.")
    return version


def version_parts(version: str) -> tuple[int, ...]:
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}", version):
        raise RuntimeError("Version must be a number in major.minor.patch format.")
    return tuple(int(part) for part in version.split("."))


def confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() in {"y", "yes"}


def commit_version(uv: str, current_version: str, version: str) -> str:
    package_init = Path("django_backblaze_b2/__init__.py")
    version_files = (Path("pyproject.toml"), package_init, Path("uv.lock"))
    original_files = {path: path.read_bytes() for path in version_files}
    source, replacements = re.subn(
        rf'^__version__ = "{re.escape(current_version)}"$',
        f'__version__ = "{version}"',
        package_init.read_text(),
        flags=re.MULTILINE,
    )
    if replacements != 1:
        raise RuntimeError(f"Expected {package_init} to contain version {current_version}.")
    try:
        run(f"{quote(uv)} version --no-sync -- {quote(version)}")
        package_init.write_text(source)
        message = f"chore: bump to {version} for next release"
        run(f"git commit -m {quote(message)} --only -- {join(map(str, version_files))}")
    except (OSError, subprocess.CalledProcessError):
        for path, content in original_files.items():
            if path.read_bytes() != content:
                path.write_bytes(content)
        raise
    return output("git rev-parse HEAD")


def publish(uv: str, version: str, notes: str, commit: str, existing_tag: bool) -> None:
    tag_ref = f"refs/tags/{version}"
    timestamp = output(f"git show -s --format=%ct {quote(commit)}")
    with TemporaryDirectory(prefix="django-backblaze-b2-release-") as build_directory:
        run(
            f"{quote(uv)} build --no-sources --out-dir {quote(build_directory)}",
            env={**os.environ, "SOURCE_DATE_EPOCH": timestamp},
        )
        distributions = Path(build_directory)
        source_distributions = list(distributions.glob("*.tar.gz"))
        wheels = list(distributions.glob("*.whl"))
        if len(source_distributions) != 1 or len(wheels) != 1:
            raise RuntimeError("Expected one source distribution and one wheel from uv build.")
        files = (*source_distributions, *wheels)
        publish_command = f"{quote(uv)} publish --check-url https://pypi.org/simple/ {join(map(str, files))}"
        run(f"{publish_command} --dry-run")
        remote_main = output("git ls-remote --exit-code origin refs/heads/main").split()[0]
        if remote_main != commit:
            raise RuntimeError("Origin main changed during the release. Sync with origin before retrying.")
        if not existing_tag:
            run(f"git tag -a -m {quote(notes)} -- {quote(version)} {quote(commit)}")
        run(f"git push origin {quote(tag_ref)}:{quote(tag_ref)}")
        run(publish_command)


def run(command: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(split(command), check=True, env=env)


def output(command: str) -> str:
    return subprocess.check_output(split(command), text=True).strip()


if __name__ == "__main__":
    raise SystemExit(main())
