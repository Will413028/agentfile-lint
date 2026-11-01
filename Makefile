PYTHON ?= python3

.PHONY: check
check:
	@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "agentfile-lint needs Python >= 3.11, but $(PYTHON) is " + sys.version.split()[0] + ". Use: make check PYTHON=python3.12")'
	$(PYTHON) -m unittest discover -s tests
