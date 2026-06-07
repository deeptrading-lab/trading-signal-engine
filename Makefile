PYTHON ?= python
SYMBOL ?= BTC
TICKER ?= AAPL
PORT ?= 8000

.PHONY: help install daemon-coordinator bitcoin-server kr-news-server signal signal-offline kr-news kr-news-sample test test-coordinator test-bitcoin-signal test-kr-stock-signal

help:
	@echo "Available targets:"
	@echo "  install            - Install Python dependencies (ai/requirements.txt)"
	@echo "  daemon-coordinator - Run Hayoung AI Coordinator bot ($(PYTHON) -m ai.coordinator.main)"
	@echo "  bitcoin-server     - Run local Bitcoin allocation HTTP server"
	@echo "  kr-news-server     - Run Korean stock news HTTP API"
	@echo "  signal SYMBOL=BTC  - Generate a Bitcoin allocation brief via free provider"
	@echo "  signal-offline SYMBOL=BTC - Generate a brief with deterministic sample prices"
	@echo "  kr-news SYMBOL=삼성전자 - Collect, summarize, and score Korean stock news via OpenAI"
	@echo "  kr-news-sample SYMBOL=삼성전자 - Run Korean stock news scoring with deterministic sample data"
	@echo "  test               - Run all pytest suites under ai/tests/"
	@echo "  test-coordinator   - Run coordinator tests only"
	@echo "  test-bitcoin-signal - Run Bitcoin allocation MVP tests only"
	@echo "  test-kr-stock-signal - Run Korean stock news tests only"
	@echo ""
	@echo "Override interpreter via PYTHON=... (default: python from active venv/PATH)."
	@echo ""
	@echo "Note: dev-relay 봇은 별도 레포 HY0118/dev-manager-bot 로 분리됨."

install:
	$(PYTHON) -m pip install -r ai/requirements.txt

daemon-coordinator:
	$(PYTHON) -m ai.coordinator.main

bitcoin-server:
	$(PYTHON) -m ai.bitcoin_signal.server

kr-news-server:
	$(PYTHON) -m ai.kr_stock_signal.server

signal:
	$(PYTHON) -m ai.bitcoin_signal.cli $(SYMBOL)

signal-offline:
	$(PYTHON) -m ai.bitcoin_signal.cli $(SYMBOL) --offline

kr-news:
	$(PYTHON) -m ai.kr_stock_signal.cli $(SYMBOL)

kr-news-sample:
	$(PYTHON) -m ai.kr_stock_signal.cli $(SYMBOL) --provider sample

test:
	$(PYTHON) -m pytest ai/tests/ -v

test-coordinator:
	$(PYTHON) -m pytest ai/tests/test_coordinator_*.py -v

test-bitcoin-signal:
	$(PYTHON) -m pytest ai/tests/test_bitcoin_signal.py -v

test-kr-stock-signal:
	$(PYTHON) -m pytest ai/tests/test_kr_stock_signal.py -v
