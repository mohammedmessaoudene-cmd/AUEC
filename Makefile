PYTHON ?= python3

.PHONY: test audit technical-report

test:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=reference-runtime $(PYTHON) -m unittest discover -s tests -v

audit:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_license_map.py
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/check_claims.py
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) scripts/public_release_gate.py

technical-report:
	cd docs/technical-report && pdflatex -interaction=nonstopmode -halt-on-error main_public.tex && bibtex main_public && pdflatex -interaction=nonstopmode -halt-on-error main_public.tex && pdflatex -interaction=nonstopmode -halt-on-error main_public.tex
