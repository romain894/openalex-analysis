PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
PYTEST_ARGS ?= -q

.PHONY: help install-dev test test-unit test-live build

help:
	@printf '%s\n' \
	  'make install-dev  Install the library and test/build tools' \
	  'make test         Run mocked tests and existing live API tests' \
	  'make test-unit    Run mocked tests without OpenAlex requests' \
	  'make test-live    Run existing tests against the OpenAlex API' \
	  'make build        Build the wheel and source archive in dist/' \
	  'Override the interpreter with PYTHON=/path/to/python.'

install-dev:
	$(PYTHON) -m pip install -e '.[dev]'

test: test-unit test-live

test-unit:
	$(PYTHON) -m pytest tests/ $(PYTEST_ARGS)

test-live:
	$(PYTHON) -m pytest tests/tests.py $(PYTEST_ARGS)

build:
	$(PYTHON) -m build
