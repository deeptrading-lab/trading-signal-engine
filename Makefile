PYTHON ?= python
PORT ?= 8000

.PHONY: help install install-dev server test

help:
	@echo "Available targets:"
	@echo "  install     - Install production dependencies"
	@echo "  install-dev - Install production and test dependencies"
	@echo "  server  - Run CRUD and market stream engine"
	@echo "  test    - Run pytest"

install:
	$(PYTHON) -m pip install -r ai/requirements.txt

install-dev:
	$(PYTHON) -m pip install -r ai/requirements-dev.txt

server:
	PORT=$(PORT) $(PYTHON) -m ai.market_data_engine.server

test:
	$(PYTHON) -m pytest ai/tests/ -v
