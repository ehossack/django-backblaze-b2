.PHONY: setup cleanup lint format \
		test test-verbose test-coverage clean-django-files \
		run-django run-test-proj \
		cleanup-docker run-sample-proj \
		publish-to-pypi release require-var-%

pyversions=$(shell cat .python-versions)
setup:
	echo "$(firstword ${pyversions})" > .python-version
	pyenv install -s $(firstword ${pyversions})
	pip install -r requirements.txt
	poetry install --sync

require-var-%:
	@if [ -z '${${*}}' ]; then echo 'ERROR: variable $* not set' && exit 1; fi

cleanup: clean-django-files cleanup-docker
	- poetry env remove python
	rm -rf .venv tests/htmlcov tests/cov.xml .coverage tests/test-results sample_app/sample_app/settings.env
	@echo "django-backblaze-b2: still installed by us (`which python`):"
	@cat requirements.txt
	@echo ""
	@echo "You may uninstall these requirements should you desire"

lint: clean-django-files
	for module in django_backblaze_b2 tests sample_app; do \
		poetry run mypy -p $$module || exit 1; \
	done
	poetry run ruff check .
	poetry run ruff format --check .

format:
	poetry run ruff format .

test: tests/test_project/files/migrations/0001_initial.py
	poetry run pytest tests --maxfail=2

test-verbose: tests/test_project/files/migrations/0001_initial.py
	PYTEST_ADDOPTS="-vv" make test

test-coverage: tests/test_project/files/migrations/0001_initial.py
	poetry run pytest \
		--cov=django_backblaze_b2 \
		--cov-report term:skip-covered \
		--cov-report html:tests/htmlcov \
		--cov-report xml:tests/cov.xml \
		tests

test-output-coverage: tests/test_project/files/migrations/0001_initial.py
	poetry run pytest \
		--junitxml=tests/test-results/junit.xml \
		--cov=django_backblaze_b2 \
		--cov-report html:tests/htmlcov \
		tests

deps_and_test = apt-get update && \
				apt-get install -y build-essential && \
					cd app && make install-reqs-and-test
test-ci:
	@echo "Running tests and lint on python $(firstword ${pyversions})"
	docker run --rm -v `pwd`:/app \
		python:$(firstword ${pyversions})-slim \
		/bin/sh -c "${deps_and_test} && make lint"
	@echo "Running tests on python $(wordlist 2,99,${pyversions})"
	$(MAKE) -j $(addprefix run-test-in-docker-python-,$(wordlist 2,99,${pyversions}))

define TEST_DOCKERFILE
ARG PYTHON_VER
FROM python:$${PYTHON_VER}
COPY . /app
RUN apt-get update && apt-get install -y build-essential
CMD cd /app && make install-reqs-and-test
endef
export TEST_DOCKERFILE

run-test-in-docker-python-%:
	@echo "$$TEST_DOCKERFILE" | docker build -tdjango-backblaze-b2-tests:python-$* --build-arg PYTHON_VER=$* -f- . 
	bash -c "trap 'docker image rm django-backblaze-b2-tests:python-$*' EXIT; docker run --rm django-backblaze-b2-tests:python-$*"

unused:
	docker run --rm \
		-v `pwd`:/app \
		python:$*-slim \
		/bin/sh -c "${deps_and_test}"

install-reqs-and-test:
	pip install -r requirements.txt
	poetry config virtualenvs.create false
	poetry install
	make test-output-coverage

clean-django-files:
	@rm -rf \
		tests/test_project/db.sqlite3 \
		tests/test_project/files/migrations/0001_initial.py

tests/test_project/files/migrations/0001_initial.py:
	poetry run python tests/test_project/manage.py makemigrations files
	poetry run python tests/test_project/manage.py migrate

run-test-proj: clean-django-files tests/test_project/files/migrations/0001_initial.py
	poetry run python tests/test_project/manage.py runserver

cleanup-docker:
	@if docker info >/dev/null 2>&1; then \
		docker rmi -f b2-django-sample:dev; \
		docker rmi -f b2-django-release:latest; \
	fi

define DOCKERFILE
FROM python:3.12
COPY requirements.txt poetry.* pyproject.toml ./
RUN pip install -r requirements.txt
RUN poetry config virtualenvs.create false && poetry install
RUN sed -i 's/python = "^3.8.1"/python = "^3.12.0"/g' pyproject.toml && \
	poetry add django@latest
COPY django_backblaze_b2 ./django_backblaze_b2
COPY setup.* README.md ./
RUN poetry build && \
	mv dist/django_backblaze_b2*.tar.gz dist/django_backblaze_b2.tar.gz && \
	pip install dist/django_backblaze_b2.tar.gz && \
	rm -rf django_backblaze_b2
COPY sample_app ./sample_app
EXPOSE 8000
CMD python sample_app/manage.py makemigrations b2_file_app && \
	python sample_app/manage.py migrate && \
	python sample_app/manage.py createuser && \
	python sample_app/manage.py runserver 0.0.0.0:8000 --insecure --noreload
endef
export DOCKERFILE

run-sample-proj:
	@echo "Build dockerfile b2-django-sample:dev"
	@echo "$$DOCKERFILE" | docker build -t b2-django-sample:dev -f- . 
	touch sample_app/sample_app/settings.env
	docker run --rm -p 8000:8000 \
		--env-file sample_app/sample_app/settings.env \
		-it b2-django-sample:dev

release: publish-to-pypi
	gh release create ${PROJ_VERSION} --notes '${VER_DESCRIPTION}'

publish-to-pypi: require-var-pypi_token
	$(eval VER_DESCRIPTION = $(shell bash -c 'read -p "Release Description: " desc; echo $$desc'))
	$(eval PROJ_VERSION = $(shell poetry run python -c "import toml; print(toml.load('pyproject.toml')['tool']['poetry']['version'])"))
	poetry publish --build --dry-run --username __token__ --password ${pypi_token}
	@if git show-ref --tags ${PROJ_VERSION} --quiet; then \
		echo "tag for ${PROJ_VERSION} exists, delete it? [y/N] " && \
		read ans && ([ $${ans:-N} = y ] && \
		git tag -d ${PROJ_VERSION} && \
		git tag -a ${PROJ_VERSION} -m '${VER_DESCRIPTION}') || true; \
	else \
		git tag -a ${PROJ_VERSION} -m '${VER_DESCRIPTION}'; \
	fi
	git push -f origin refs/tags/${PROJ_VERSION}
	rm -rf dist
	poetry publish --build --username __token__ --password ${pypi_token}