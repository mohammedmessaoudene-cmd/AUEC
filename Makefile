PYTHON ?= python3

.PHONY: test audit demo-authority-boundary technical-report

test:
	$(PYTHON) -B -m unittest discover -s tests -v

audit:
	$(PYTHON) -B scripts/check_repository_hashes.py
	$(PYTHON) -B scripts/check_license_map.py
	$(PYTHON) -B scripts/check_claims.py
	$(PYTHON) -B scripts/public_release_gate.py

demo-authority-boundary:
	$(PYTHON) -B scripts/demo_authority_boundary.py --verify-evidence evidence/authority-boundary-demo.json

technical-report:
	cd docs/technical-report && pdflatex -interaction=nonstopmode -halt-on-error main_public.tex && bibtex main_public && pdflatex -interaction=nonstopmode -halt-on-error main_public.tex && pdflatex -interaction=nonstopmode -halt-on-error main_public.tex
