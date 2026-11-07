# django-backblaze-b2

[![pypi version](https://img.shields.io/pypi/v/django-backblaze-b2)](https://pypi.org/project/django-backblaze-b2/)
[![python version](https://img.shields.io/pypi/pyversions/django-backblaze-b2)](https://pypi.org/project/django-backblaze-b2/)
[![django version](https://img.shields.io/pypi/djversions/django-backblaze-b2)](https://pypi.org/project/django-backblaze-b2/)

A storage backend for Django that uses [Backblaze's B2 APIs](https://www.backblaze.com/b2/cloud-storage.html).

Implementation wraps [Official Python SDK](https://github.com/Backblaze/b2-sdk-python)

## Changelog / Releases

See [https://github.com/ehossack/django-backblaze-b2/releases](https://github.com/ehossack/django-backblaze-b2/releases)

## How to use

1. Install from this repo, or install from PyPi: `pip install django-backblaze-b2`
Requires Python 3.10 or newer. See the compatibility table below.
1. Configure your django `settings`. A minimalistic config would be:
```python
CACHES = {
    "default": .... ,
    # add a cache via db table or memcached that can be accessed from multiple threads
    "django-backblaze-b2": {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'django_backblaze_b2_cache_table',
    }
}

BACKBLAZE_CONFIG = {
    # however you want to securely retrieve these values
    "application_key_id": os.getenv("BACKBLAZE_KEY_ID"),
    "application_key": os.getenv("BACKBLAZE_KEY"),
}
```

Theoretically you may now refer to the base storage class as a storage class (see the sample app for some usage: you can run with `make run-sample-proj` although you might want to configure the `SECONDS_TO_RUN_APP` variable in `settings.env` to be 0 for unlimited to try things out)
e.g.
```python
from django_backblaze_b2 import BackblazeB2Storage

class MyModel(models.Model):
    file_field = models.FileField(
        upload_to="uploads",
        storage=BackblazeB2Storage
    )
```

### Public/Logged-In/Private storage

1. Add `django_backblaze_b2` to your `INSTALLED_APPS`
1. Add the urls to your `urlpatterns` in the root `urls.py`:
```python
    urlpatterns = [
        ...
        path('', include('django_backblaze_b2.urls')),
    ]
```

### Caching

To retrieve file metadata ("file info" as the b2 sdk names it), this library has to authorize and request data from b2 servers, even for just resolving the url for a file. Because these are network calls, and relatively expensive in comparison to a file-based storage, and because data is unlikely to change frequently, there is some caching done by this library.  
By default, the account information (`account_info`) configuration of the settings uses a cache by the name of `django-backblaze-b2` which you must have in your `CACHES` section of your `settings.py`. This is to leverage django's thread-safe cache implementations, and if you are using a database cache table or memcached, (rather than LocMemCache) your cache can be shared by the multiple django processes that typically serve requests.  
It is not recommended configure `account_info` with the `default` django cache, as the `clear()` method may be called during the backblaze lifecycle.  
If you do not wish to use a django cache, you can use a sqlite database on disk for caching, or use a non-thread-safe in-memory implementation. This is only recommended for single-threaded deployments (remember in most deployments a new thread serves each request).  
For further discussion on this see https://github.com/ehossack/django-backblaze-b2/issues/16

### Configurations

You may want to use your own bucket name, or set further configuration such as lazy authorization/validation, or specifying file metadata.  
Refer to [the options](./django_backblaze_b2/options.py) for all options.  
You can modify the settings dict, but additionally override any setting with the `opts` keyword argument to the storage classes.

To specify different buckets to use for your public, logged-in, staff storage, you can set the 
`specificBucketNames` attribute of the settings dict.
## Why

There are several Django storage packages out there already which support B2, but none met my needs. These are:

* [django-storages](https://github.com/jschneier/django-storages)
    * Large community engagement ✅
    * Well-tested ✅
    * [Second-class support](https://github.com/jschneier/django-storages/issues/765) via [Apache Libcloud](https://github.com/apache/libcloud) ❌
    * Disconnect in configuration and actual use ❌
    * PR list with low turnaround ❌
* [django-b2](https://github.com/pyutil/django-b2)
    * Similar aim to this project, around official backblaze SDK ✅
    * Mixed goals (storage, scripts) ❌
    * Tests?? ❌
* [django-backblazeb2-storage](https://github.com/royendgel/django-backblazeb2-storage)
    * Simple configuration ✅
    * Not based around python SDK (potentially harder to keep up with version changes) ❌
    * Tests?? ❌

### S3 Compatible API

Backblazed can be used with an [S3-compatible API](https://www.backblaze.com/b2/docs/s3_compatible_api.html)
This is great, but most packages use an older version of the S3 Api (v2). Backblaze uses v4.

### What this package offers

* Type Annotations
* Tested
* No hacks required to get up and running around API deficiencies (any hacks are not exposed in API)
* Support for public/private files, restricted via Django user permissions
* Support for CDN and cached url details

## How it works

* A simple implementation of the `django.core.files.storage.Storage` class provides handling for storage behaviour within your Django application
* Three url routes are appended to the root of your application:  
    1. `/b2/`
    2. `/b2l/`
    3. `/b2s/`
These routes act as a proxy/intermediary between the requester and backblaze b2 apis. The public `/b2/` allows exposing files from a private bucket, and the logged-in and staff routes will perform the known validations of a django app to prevent unauthorized access.
* If you use a CDN config, you can specify the CDN options and then include the bucket url segments (`/file/<bucket-name>/`) if your CDN is proxying the classic b2 url (e.g. `f000.backblazeb2.com`) or not, if you are proxying the s3-compatible url.

### Gotchas

* The original filename + any upload paths is stored in the database. Thus your column name must be of sufficient length to hold that (unchanged behaviour from `FileSystemStorage`)
*  When retrieving files from the `PublicStorage`, `LoggedInStorage` or `StaffStorage`, you may not override the `"bucket"` or authorization options, or else when the app proxies the file download, it will be unable to retrieve the file from the respective bucket.
* Simply using `LoggedInStorage` or `StaffStorage` is not enough to protect your files if your bucket is not public. If any individual gains access to the file ids/urls for these files, there is no authentication around them. It is up to the implementer to ensure the security of their application.
* Once the file is uploaded, and someone obtains a file url (e.g. http://djangodomain.com/b2l/uploads/image.png), the django model is no longer involved in file resolution. This means that if you share the bucket between multiple use-cases, you could in theory find files that don't belong to your django app (e.g. some image2.png), or similarly if you delete/change your models, the files could still be downloaded. Consider using an app like [django-cleanup](https://github.com/un1t/django-cleanup) if this is important to you

## Contributing

Contributions welcome!

* Please ensure test coverage does not decrease in a meaningful way.
* Ensure formatting is compliant (`make lint`)
* Use [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/)

## Setting up for development

### Requires

* [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.9.10 or newer
* GNU Make
* (optional) docker - run sample app

#### Version compatibility

Development and the sample app default to Python 3.14 and Django 5.2 LTS.
Tests use the latest patch release of each Django series below.

| Python | Django |
| ------ | ------ |
| 3.10 | 3.2, 4.2, 5.0, 5.1, 5.2 |
| 3.11 | 4.2, 5.0, 5.1, 5.2 |
| 3.12 | 4.2, 5.0, 5.1, 5.2, 6.0, 6.1 |
| 3.13 | 5.1, 5.2, 6.0, 6.1 |
| 3.14 | 5.2, 6.0, 6.1 |

Python 3.10 is retained as a legacy exception for Django 3.2, whose official
Python support ends at 3.10. Python 3.9 is no longer supported by this package.
Older Django compatibility does not imply upstream security maintenance.
See [Python support status](https://devguide.python.org/versions/) and
[Django supported releases](https://www.djangoproject.com/download/#supported-versions).

### Running

1. `make setup`

uv installs the selected Python version and creates `.venv` from `uv.lock`.
Use `make setup PYTHON_VER=3.13` to select another supported Python version.
Run `uv lock` after editing dependencies and commit the updated `uv.lock`.
Run `make setup` after lockfile changes. Test commands use the prepared
environment without syncing so the CI matrix keeps its selected Django version.

* You can run django with `make run-django` to test django app.
* You can run tests with `make test`
* You can view test coverage with `make test-coverage`, then see in the terminal, 
open `test/htmlcov/index.html`
or use `cov.xml` in your favourite IDE like VSCode

### Continuous integration

GitHub Actions runs linting, package builds, and the Python/Django test matrix
on pull requests and pushes to `main`. The matrix comes from the Makefile via
`make test-matrix`, which requires `jq`. Test reports and distributions are
available as workflow artifacts.

Sample-app checks build and install the source distribution in Docker, then
run Django checks, migrations, and user creation with dummy B2 settings.
These checks do not authorize with Backblaze or require repository secrets.

### Releasing

1. `make release pypi_token=...`

`make release` builds the wheel and source distribution with `uv build`, checks
the upload with `uv publish --dry-run`, and publishes to PyPI with `uv publish`.

### Cleanup

1. `make cleanup`
