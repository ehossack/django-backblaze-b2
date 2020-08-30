# django-backblaze-b2

A storage backend for Django that uses [Backblaze's B2 APIs](https://www.backblaze.com/b2/cloud-storage.html).

Implementation wraps [Official Python SDK](https://github.com/Backblaze/b2-sdk-python)

## How to use

* (planned) some documentation

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
* (planned) support for public/private files, restricted via Django user permissions

## How it works

* Simple storage class
* (planned) some URLs

## Contributing

Contributions welcome! Please ensure test coverage does not decrease in a meaningful way.
Ensure formatting is compliant.

## Setting up for development

### Requires

* python
* (optional) pyenv
* GNU Make

### Running

1. `make setup`

* You can run django with `make run-django` to test django app.
* You can run tests with `make test`
* You can view test coverage with `make test-coverage`, then see in the terminal, 
open `test/htmlcov/index.html`
or use `cov.xml` in your favourite IDE like VSCode

### Cleanup

1. `make cleanup`
