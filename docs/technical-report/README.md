# AUEC v0.35.0-prestandard - IEEE-style technical report source

This directory builds the named-author independent technical report:

```text
main_public.tex -> AUEC_Technical_Report_v0.35.0-prestandard.pdf
```

## Status

- Independent technical report / research pre-standard
- Not peer reviewed
- IEEE-style layout is used for readability only
- Not affiliated with, submitted to, or endorsed by IEEE
- No IEEE logo, copyright notice, volume, issue, DOI, or acceptance claim
- GitHub and Zenodo publication remain separately authorized actions
- Journal submission remains paused

## Versioning

Public documents use semantic versioning (`AUEC v0.35.0-prestandard`). Internal engineering labels are excluded from public filenames and prose. The evidence bundle cited by the report has the stable public identifier `EB-2026-08-02` and is independently versioned from the report.

## Build

```bash
make
```

or:

```bash
pdflatex -interaction=nonstopmode -halt-on-error main_public.tex
bibtex main_public
pdflatex -interaction=nonstopmode -halt-on-error main_public.tex
pdflatex -interaction=nonstopmode -halt-on-error main_public.tex
```

The report source and narrative content are licensed under CC BY 4.0. Evidence files retain the notices stated in the repository.
