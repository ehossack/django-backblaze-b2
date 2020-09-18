.PHONY: setup cleanup lint format \
		test test-verbose test-coverage clean-django-files \
		run-django run-test-proj \
		cleanup-docker run-sample-proj

setup:
	pip install -r requirements.txt
	poetry install

cleanup: clean-django-files cleanup-docker
	- poetry env remove python
	rm -rf .venv tests/htmlcov tests/cov.xml .coverage tests/test-results sample_app/sample_app/settings.env
	@echo "django-backblaze-b2: still installed by us (`which python`):"
	@cat requirements.txt
	@echo ""
	@echo "You may uninstall these requirements should you desire"

lint: clean-django-files
	poetry run mypy .
	poetry run flake8 django_backblaze_b2 tests
	poetry run black --check .

format:
	poetry run black .

test: tests/test_project/files/migrations/0001_initial.py
	poetry run pytest tests

test-verbose: tests/test_project/files/migrations/0001_initial.py
	PYTEST_ADDOPTS="-vv" make test

test-coverage: tests/test_project/files/migrations/0001_initial.py
	poetry run pytest \
		--cov=django_backblaze_b2 \
		--cov-report term:skip-covered \
		--cov-report html:tests/htmlcov \
		--cov-report xml:tests/cov.xml \
		tests

test-ci: tests/test_project/files/migrations/0001_initial.py
	poetry run pytest \
		--junitxml=tests/test-results/junit.xml \
		--cov=django_backblaze_b2 \
		--cov-report html:tests/htmlcov \
		tests

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
	fi

define DOCKERFILE
FROM python:3.8
COPY requirements.txt poetry.* pyproject.toml ./
RUN pip install -r requirements.txt
RUN poetry config virtualenvs.create false && poetry install
COPY django_backblaze_b2 ./django_backblaze_b2
COPY setup.* README.md MANIFEST.in ./
RUN python setup.py sdist && \
	mv dist/django-backblaze-b2*.tar.gz dist/django-backblaze-b2.tar.gz && \
	pip install dist/django-backblaze-b2.tar.gz && \
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
	docker run -p 8000:8000 \
		--env-file sample_app/sample_app/settings.env \
		-it b2-django-sample:dev
