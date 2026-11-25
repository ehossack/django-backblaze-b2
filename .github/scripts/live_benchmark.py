import hashlib
import inspect
import json
import os
import subprocess
import sys
import uuid
from contextlib import closing
from io import BytesIO
from pathlib import Path
from threading import Event, Thread

from b2sdk.v2 import B2Api, Bucket, InMemoryAccountInfo
from django.conf import settings
from django.http import FileResponse

from django_backblaze_b2.b2_file import B2File

root = Path.cwd()
results = Path(__file__).with_name("results.jsonl")


def resident_bytes() -> int:
    pages = int(Path("/proc/self/statm").read_text().split()[1])
    return pages * os.sysconf("SC_PAGE_SIZE")


def live_bucket() -> Bucket:
    api = B2Api(InMemoryAccountInfo())
    api.authorize_account(
        "production",
        os.environ["TEST_BACKBLAZE_APPLICATION_KEY_ID"].strip("\"'"),
        os.environ["TEST_BACKBLAZE_APPLICATION_KEY"].strip("\"'"),
    )
    return api.get_bucket_by_name(os.environ["TEST_BUCKET"].strip("\"'"))


def run() -> None:
    bucket = live_bucket()
    prefix = f"pr-312-benchmark/{uuid.uuid4().hex}"
    versions = []
    try:
        fixtures = []
        for size in (20, 100):
            payload = os.urandom(size * 1024**2)
            name = f"{prefix}/{size}.bin"
            version = bucket.upload_bytes(payload, name)
            versions.append((version.id_, name))
            fixtures.append((str(size), name, hashlib.sha256(payload).hexdigest()))
            del payload
        with results.open("w") as output:
            for trial in range(5):
                for fixture in fixtures:
                    for variant in ("base", "head") if trial % 2 == 0 else ("head", "base"):
                        path = root / variant
                        process = subprocess.run(
                            [sys.executable, "-P", __file__, variant, *fixture],
                            env={**os.environ, "PYTHONPATH": str(path)},
                            capture_output=True,
                            text=True,
                        )
                        if process.returncode:
                            print(process.stdout.strip(), flush=True)
                            raise RuntimeError(f"{variant} worker failed: {process.stdout.strip()}")
                        print(process.stdout.strip(), file=output, flush=True)
                        print(f"Finished trial {trial + 1}, {fixture[0]} MiB, {variant}", flush=True)
    finally:
        for file_id, name in versions:
            bucket.delete_file_version(file_id, name)
        print(f"Removed {len(versions)} benchmark file versions", flush=True)


def worker(variant: str, size: str, name: str, digest: str) -> None:
    path = root / variant
    assert Path(inspect.getfile(B2File)).resolve() == path / "django_backblaze_b2/b2_file.py"
    settings.configure(DEFAULT_CHARSET="utf-8")
    length = int(size) * 1024**2
    file = B2File(name, live_bucket(), lambda _: length, {}, "r")
    baseline = peak = resident_bytes()
    stop = Event()

    def sample() -> None:
        nonlocal peak
        while not stop.wait(0.002):
            peak = max(peak, resident_bytes())

    sampler = Thread(target=sample)
    sampler.start()
    try:
        with closing(FileResponse(file)) as response:
            actual = hashlib.sha256()
            count = 0
            for chunk in response:
                actual.update(chunk)
                count += len(chunk)
            assert actual.hexdigest() == digest and count == length
            assert isinstance(file.file, BytesIO) == (variant == "base")
            peak = max(peak, resident_bytes())
    finally:
        stop.set()
        sampler.join()
    print(json.dumps(dict(size=int(size), variant=variant, baseline=baseline, peak=peak, growth=peak - baseline)))


if __name__ == "__main__":
    try:
        if len(sys.argv) == 1:
            run()
        else:
            worker(*sys.argv[1:])
    except Exception as error:
        print(type(error).__name__, flush=True)
        sys.exit(1)
