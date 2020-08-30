.PHONY: lint test

setup:
	pip install -r requirements.txt
	poetry install

cleanup:
	poetry env remove python
	@echo "Still installed on your system (`which python`)"
	@cat requirements.txt
	@echo ""
	@echo "You may uninstall these"

lint:
	poetry run mypy .
	poetry run flake8 .
	poetry run black --check .

format:
	poetry run black .

test:
	poetry run pytest