.PHONY: setup cleanup lint format \
		test test-verbose test-coverage test-matrix clean-django-files \
		run-django run-test-proj \
		cleanup-docker run-sample-proj \
		publish-to-pypi release require-var-%

UV ?= uv
UV_RUN = $(UV) run --no-sync
pyversions=$(shell cat .python-versions)
PYTHON_VER ?= $(firstword ${pyversions})
DJANGO_VER ?= 5.2
DOCKER_RUN_FLAGS ?= -it
django-versions-3.10 = 3.2 4.2 5.0 5.1 5.2
django-versions-3.11 = 4.2 5.0 5.1 5.2
django-versions-3.12 = 4.2 5.0 5.1 5.2 6.0 6.1
django-versions-3.13 = 5.1 5.2 6.0 6.1
django-versions-3.14 = 5.2 6.0 6.1
test-combinations = $(foreach python,$(pyversions),$(foreach django,$(django-versions-$(python)),$(python)-django-$(django)))
TEST_OUTPUT_DIR ?= tests
setup:
	$(UV) python pin $(PYTHON_VER)
	$(UV) sync --locked --python $(PYTHON_VER)

require-var-%:
	@if [ -z '${${*}}' ]; then echo 'ERROR: variable $* not set' && exit 1; fi

cleanup: clean-django-files cleanup-docker
	rm -rf .venv tests/htmlcov tests/cov.xml .coverage tests/test-results sample_app/sample_app/settings.env

lint: clean-django-files
	@rm -rf .mypy_cache
	for module in django_backblaze_b2 tests sample_app; do \
		$(UV_RUN) mypy -p $$module --warn-unused-ignores --enable-error-code ignore-without-code || exit 1; \
	done
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .

format:
	$(UV_RUN) ruff format .

test: tests/test_project/files/migrations/0001_initial.py
	$(UV_RUN) pytest tests --maxfail=2

test-verbose: tests/test_project/files/migrations/0001_initial.py
	PYTEST_ADDOPTS="-vv" make test

test-coverage: tests/test_project/files/migrations/0001_initial.py
	$(UV_RUN) pytest \
		--cov=django_backblaze_b2 \
		--cov-report term:skip-covered \
		--cov-report html:tests/htmlcov \
		--cov-report xml:tests/cov.xml \
		tests

test-output-coverage: tests/test_project/files/migrations/0001_initial.py
	$(UV_RUN) pytest \
		--junitxml=$(TEST_OUTPUT_DIR)/test-results/junit.xml \
		--cov=django_backblaze_b2 \
		--cov-report html:$(TEST_OUTPUT_DIR)/htmlcov \
		tests

test-ci:
	$(MAKE) run-test-in-docker-python-$(firstword ${pyversions})-django-$(DJANGO_VER) CHECK_LINT=1
	$(MAKE) -j2 --output-sync=target $(addprefix run-test-in-docker-python-,$(filter-out $(firstword ${pyversions})-django-$(DJANGO_VER),$(test-combinations)))

test-matrix:
	@printf '%s\n' $(test-combinations) | jq -R -s -c 'split("\n")[:-1] | map(split("-django-") | {python: .[0], django: .[1]}) | {include: .}'

define TEST_DOCKERFILE
ARG PYTHON_VER
FROM python:$${PYTHON_VER}
COPY . /app
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_PYTHON=/usr/local/bin/python
ENV PATH="/app/.venv/bin:$${PATH}"
RUN pip install -r requirements.txt && uv sync --locked --no-install-project --python /usr/local/bin/python
ARG DJANGO_VER
RUN uv pip install --python .venv/bin/python "Django~=$${DJANGO_VER}.0"
CMD python --version && python -m django --version && make test-output-coverage && if [ "$${CHECK_LINT}" = "1" ]; then make lint; fi
endef
export TEST_DOCKERFILE

run-test-in-docker-python-%:
	$(eval TEST_PYTHON = $(word 1,$(subst -django-, ,$*)))
	$(eval TEST_DJANGO = $(or $(word 2,$(subst -django-, ,$*)),$(DJANGO_VER)))
	@echo "$$TEST_DOCKERFILE" | docker build -tdjango-backblaze-b2-tests:$* --build-arg PYTHON_VER=$(TEST_PYTHON) --build-arg DJANGO_VER=$(TEST_DJANGO) -f- .
	bash -c "trap 'docker image rm django-backblaze-b2-tests:$*' EXIT; docker run --rm -e CHECK_LINT=$(CHECK_LINT) -e TEST_OUTPUT_DIR=/results -v `pwd`/tests/matrix/$*:/results django-backblaze-b2-tests:$*"

install-reqs-and-test:
	pip install -r requirements.txt
	$(UV) sync --locked --no-install-project --python $(PYTHON_VER)
	$(UV) pip install --python .venv/bin/python "Django~=$(DJANGO_VER).0"
	UV_PYTHON=$(PYTHON_VER) $(MAKE) test-output-coverage

clean-django-files:
	@rm -rf \
		tests/test_project/db.sqlite3 \
		tests/test_project/files/migrations/0001_initial.py

tests/test_project/files/migrations/0001_initial.py:
	$(UV_RUN) python tests/test_project/manage.py makemigrations files
	$(UV_RUN) python tests/test_project/manage.py migrate

run-test-proj: clean-django-files tests/test_project/files/migrations/0001_initial.py
	$(UV_RUN) python tests/test_project/manage.py runserver

cleanup-docker:
	@if docker info >/dev/null 2>&1; then \
		docker rmi -f b2-django-sample:dev; \
		docker rmi -f b2-django-release:latest; \
	fi

define DOCKERFILE
ARG PYTHON_VER=3.14
FROM python:$${PYTHON_VER}
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$${PATH}"
COPY requirements.txt uv.lock pyproject.toml ./
RUN pip install -r requirements.txt
ARG PYTHON_VER
ARG DJANGO_VER
RUN uv sync --locked --no-dev --no-install-project --python /usr/local/bin/python
RUN uv pip install --python /opt/venv/bin/python "Django~=$${DJANGO_VER}.0"
COPY django_backblaze_b2 ./django_backblaze_b2
COPY README.md LICENSE ./
RUN uv build --no-sources && \
	mv dist/django_backblaze_b2*.tar.gz dist/django_backblaze_b2.tar.gz && \
	uv pip install --python /opt/venv/bin/python --no-deps dist/django_backblaze_b2.tar.gz && \
	rm -rf django_backblaze_b2
COPY sample_app ./sample_app
EXPOSE 8000
CMD python sample_app/manage.py makemigrations b2_file_app && \
	python sample_app/manage.py migrate && \
	python sample_app/manage.py createuser && \
	python sample_app/manage.py runserver 0.0.0.0:8000 --insecure --noreload
endef
export DOCKERFILE

run-sample-proj-on-django-%:
	@echo "Build dockerfile b2-django-sample:dev"
	@echo "$$DOCKERFILE" | docker build -t b2-django-sample:dev --build-arg DJANGO_VER=$* --build-arg PYTHON_VER=$(PYTHON_VER) -f- .
	touch sample_app/sample_app/settings.env
	docker run --rm -p 8000:8000 \
		--env-file sample_app/sample_app/settings.env \
		$(DOCKER_RUN_FLAGS) b2-django-sample:dev

run-sample-proj:
	$(MAKE) run-sample-proj-on-django-$(DJANGO_VER)

release: setup publish-to-pypi
	gh release create ${PROJ_VERSION} --notes '${VER_DESCRIPTION}'

publish-to-pypi: require-var-pypi_token
	$(eval VER_DESCRIPTION = $(shell bash -c 'read -p "Release Description: " desc; echo $$desc'))
	$(eval PROJ_VERSION = $(shell $(UV) version --short))
	rm -rf dist
	$(UV) build --no-sources
	@UV_PUBLISH_TOKEN='${pypi_token}' $(UV) publish --dry-run
	@if git show-ref --tags ${PROJ_VERSION} --quiet; then \
		echo "tag for ${PROJ_VERSION} exists, delete it? [y/N] " && \
		read ans && ([ $${ans:-N} = y ] && \
		git tag -d ${PROJ_VERSION} && \
		git tag -a ${PROJ_VERSION} -m '${VER_DESCRIPTION}') || true; \
	else \
		git tag -a ${PROJ_VERSION} -m '${VER_DESCRIPTION}'; \
	fi
	git push -f origin refs/tags/${PROJ_VERSION}
	@UV_PUBLISH_TOKEN='${pypi_token}' $(UV) publish
