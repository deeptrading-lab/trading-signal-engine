PYTHON ?= python
SYMBOL ?= BTC

.PHONY: help install daemon daemon-dev-relay daemon-coordinator bitcoin-server signal signal-offline test test-dev-relay test-coordinator test-bitcoin-signal

help:
	@echo "Available targets:"
	@echo "  install            - Install Python dependencies (ai/requirements.txt)"
	@echo "  daemon             - Alias for daemon-dev-relay (most common)"
	@echo "  daemon-dev-relay   - Run Hayoung Dev Manager bot ($(PYTHON) -m ai.dev_relay.main)"
	@echo "  daemon-coordinator - Run Hayoung AI Coordinator bot ($(PYTHON) -m ai.coordinator.main)"
	@echo "  bitcoin-server     - Run local Bitcoin allocation HTTP server"
	@echo "  signal SYMBOL=BTC  - Generate a Bitcoin allocation brief via free provider"
	@echo "  signal-offline SYMBOL=BTC - Generate a brief with deterministic sample prices"
	@echo "  test               - Run all pytest suites under ai/tests/"
	@echo "  test-dev-relay     - Run dev_relay tests only"
	@echo "  test-coordinator   - Run coordinator tests only"
	@echo "  test-bitcoin-signal - Run Bitcoin allocation MVP tests only"
	@echo ""
	@echo "Override interpreter via PYTHON=... (default: python from active venv/PATH)."

install:
	$(PYTHON) -m pip install -r ai/requirements.txt

daemon: daemon-dev-relay

daemon-dev-relay:
	$(PYTHON) -m ai.dev_relay.main

daemon-coordinator:
	$(PYTHON) -m ai.coordinator.main

bitcoin-server:
	$(PYTHON) -m ai.bitcoin_signal.server

signal:
	$(PYTHON) -m ai.bitcoin_signal.cli $(SYMBOL)

signal-offline:
	$(PYTHON) -m ai.bitcoin_signal.cli $(SYMBOL) --offline

test:
	$(PYTHON) -m pytest ai/tests/ -v

test-dev-relay:
	$(PYTHON) -m pytest ai/tests/dev_relay/ -v

test-coordinator:
	$(PYTHON) -m pytest ai/tests/test_coordinator_*.py -v

test-bitcoin-signal:
	$(PYTHON) -m pytest ai/tests/test_bitcoin_signal.py -v
