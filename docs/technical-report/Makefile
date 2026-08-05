PDFLATEX ?= pdflatex
BIBTEX ?= bibtex
PYTHON ?= python
TARGET := main_public
OUTPUT := AUEC_Technical_Report_v0.36.0-prestandard.pdf

.PHONY: all clean

all: $(OUTPUT)

$(OUTPUT): $(TARGET).tex preamble.tex metadata_public.tex body.tex references.bib $(wildcard sections/*.tex)
	$(PDFLATEX) -interaction=nonstopmode -halt-on-error $(TARGET).tex
	$(BIBTEX) $(TARGET)
	$(PDFLATEX) -interaction=nonstopmode -halt-on-error $(TARGET).tex
	$(PDFLATEX) -interaction=nonstopmode -halt-on-error $(TARGET).tex
	$(PYTHON) -c "from shutil import copyfile; copyfile('$(TARGET).pdf', '$(OUTPUT)')"

clean:
	rm -f $(TARGET).aux $(TARGET).bbl $(TARGET).blg $(TARGET).log $(TARGET).out $(TARGET).pdf $(OUTPUT)
