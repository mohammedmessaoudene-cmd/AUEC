# AUEC v0.35.0-prestandard build reproducibility

The IEEE-style technical report was built from two clean copies with:

```text
SOURCE_DATE_EPOCH=1785715200
FORCE_SOURCE_DATE=1
TZ=UTC
pdflatex -> bibtex -> pdflatex -> pdflatex
```

Both PDF outputs were byte-identical.

```text
File      : AUEC_Technical_Report_v0.35.0-prestandard.pdf
SHA-256   : 84fa8fd33f74069c3a0acbe49f77feec0682689f942841758ba1eada6fc63c13
Size      : 318886 bytes
Pages     : 10
Page size : US Letter
Layout    : IEEEtran journal mode, 10 pt, two columns
```

Release gates also require embedded fonts, no unresolved references, no overfull boxes, clean text extraction, and page-by-page visual inspection.
