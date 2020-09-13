.PHONY: setup cleanup lint format \
		test test-verbose test-coverage \
		run-django

setup:
	pip install -r requirements.txt
	poetry install

cleanup:
	poetry env remove python
	@echo "Still installed on your system (`which python`)"
	@cat requirements.txt
	@echo ""
	@echo "You may uninstall these"
	rm -rf tests/htmlcov tests/cov.xml .coverage

lint:
	poetry run mypy .
	poetry run flake8 django_backblaze_b2 tests
	poetry run black --check .

format:
	poetry run black .

test:
	poetry run pytest tests

test-verbose:
	PYTEST_ADDOPTS="-vv" make test

test-coverage:
	poetry run pytest \
		--cov=django_backblaze_b2 \
		--cov-report term:skip-covered \
		--cov-report html:tests/htmlcov \
		--cov-report xml:tests/cov.xml \
		tests

run-django:
	rm -rf tests/test_project/db.sqlite3 tests/test_project/files/migrations/0001_initial.py
	poetry run python tests/test_project/manage.py makemigrations files
	poetry run python tests/test_project/manage.py migrate
	poetry run python tests/test_project/manage.py runserver