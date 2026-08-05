# AUEC v0.36.0-prestandard build reproducibility

The IEEE-style technical report was built from two clean copies with:

```text
SOURCE_DATE_EPOCH=1785715200
FORCE_SOURCE_DATE=1
TZ=UTC
pdflatex -> bibtex -> pdflatex -> pdflatex
```

Both PDF outputs were byte-identical.

```text
File      : AUEC_Technical_Report_v0.36.0-prestandard.pdf
SHA-256   : 2bc42dd37f4fcf879d4f77171d2966acabc2d7082b8c132775637e9d286b5a3e
Size      : 328380 bytes
Pages     : 11
Page size : US Letter
Layout    : IEEEtran journal mode, 10 pt, two columns
```

Release gates also require embedded fonts, no unresolved references, no overfull boxes, clean text extraction, and page-by-page visual inspection.
