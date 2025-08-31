# Makefile for Bedehus prosjekt

PYTHON=python3
VENV_DIR=venv
PIP=$(VENV_DIR)/bin/pip
PYTHON_BIN=$(VENV_DIR)/bin/python

.PHONY: venv install run clean

venv:
	$(PYTHON) -m venv $(VENV_DIR)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

run: venv
	$(PYTHON_BIN) mainv2.py

clean:
	rm -rf $(VENV_DIR)

