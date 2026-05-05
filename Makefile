PYTHON ?= python

.PHONY: help install daemon daemon-dev-relay daemon-coordinator test test-dev-relay test-coordinator

help:
	@echo "Available targets:"
	@echo "  install            - Install Python dependencies (ai/requirements.txt)"
	@echo "  daemon             - Alias for daemon-dev-relay (most common)"
	@echo "  daemon-dev-relay   - Run Hayoung Dev Manager bot ($(PYTHON) -m ai.dev_relay.main)"
	@echo "  daemon-coordinator - Run Hayoung AI Coordinator bot ($(PYTHON) -m ai.coordinator.main)"
	@echo "  test               - Run all pytest suites under ai/tests/"
	@echo "  test-dev-relay     - Run dev_relay tests only"
	@echo "  test-coordinator   - Run coordinator tests only"
	@echo ""
	@echo "Override interpreter via PYTHON=... (default: python from active venv/PATH)."

install:
	$(PYTHON) -m pip install -r ai/requirements.txt

daemon: daemon-dev-relay

daemon-dev-relay:
	$(PYTHON) -m ai.dev_relay.main

daemon-coordinator:
	$(PYTHON) -m ai.coordinator.main

test:
	$(PYTHON) -m pytest ai/tests/ -v

test-dev-relay:
	$(PYTHON) -m pytest ai/tests/dev_relay/ -v

test-coordinator:
	$(PYTHON) -m pytest ai/tests/test_coordinator_*.py -v
