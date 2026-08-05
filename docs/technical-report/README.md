# AUEC v0.36.0-prestandard - technical report source

This directory builds the named-author independent technical report:

```text
main_public.tex -> AUEC_Technical_Report_v0.36.0-prestandard.pdf
```

## Status

- Research pre-standard technical report
- Two-column technical layout
- No journal logo, copyright notice, volume, issue, DOI, or acceptance claim
- Candidate GitHub and Zenodo actions remain unperformed

## Versioning

Public documents use semantic versioning (`AUEC v0.36.0-prestandard`).
Internal engineering labels are excluded from public filenames and prose. The
historical official-protocol evidence bundle retains the identifier
`EB-2026-08-02`; new core-semantic evidence is identified separately as
`CS-2026-08-04`.

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
