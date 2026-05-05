.PHONY: help install daemon daemon-dev-relay daemon-coordinator test test-dev-relay test-coordinator

help:
	@echo "Available targets:"
	@echo "  install            - Install Python dependencies (ai/requirements.txt)"
	@echo "  daemon             - Alias for daemon-dev-relay (most common)"
	@echo "  daemon-dev-relay   - Run Hayoung Dev Manager bot (python -m ai.dev_relay.main)"
	@echo "  daemon-coordinator - Run Hayoung AI Coordinator bot (python -m ai.coordinator.main)"
	@echo "  test               - Run all pytest suites under ai/tests/"
	@echo "  test-dev-relay     - Run dev_relay tests only"
	@echo "  test-coordinator   - Run coordinator tests only"

install:
	pip install -r ai/requirements.txt

daemon: daemon-dev-relay

daemon-dev-relay:
	python -m ai.dev_relay.main

daemon-coordinator:
	python -m ai.coordinator.main

test:
	pytest ai/tests/ -v

test-dev-relay:
	pytest ai/tests/dev_relay/ -v

test-coordinator:
	pytest ai/tests/test_coordinator_*.py -v
