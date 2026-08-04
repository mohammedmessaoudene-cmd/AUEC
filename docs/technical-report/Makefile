PDFLATEX ?= pdflatex
BIBTEX ?= bibtex
TARGET := main_public
OUTPUT := AUEC_Technical_Report_v0.35.0-prestandard.pdf

.PHONY: all clean

all: $(OUTPUT)

$(OUTPUT): $(TARGET).tex preamble.tex metadata_public.tex body.tex references.bib $(wildcard sections/*.tex)
	$(PDFLATEX) -interaction=nonstopmode -halt-on-error $(TARGET).tex
	$(BIBTEX) $(TARGET)
	$(PDFLATEX) -interaction=nonstopmode -halt-on-error $(TARGET).tex
	$(PDFLATEX) -interaction=nonstopmode -halt-on-error $(TARGET).tex
	cp $(TARGET).pdf $(OUTPUT)

clean:
	rm -f $(TARGET).aux $(TARGET).bbl $(TARGET).blg $(TARGET).log $(TARGET).out $(TARGET).pdf $(OUTPUT)
