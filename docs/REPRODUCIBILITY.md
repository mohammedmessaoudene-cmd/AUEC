# Reproducibility

## Local source smoke test

```bash
export PYTHONPATH="$PWD/reference-runtime"
python -m unittest discover -s tests -v
python examples/run_example.py
```

## Evidence verification

The full EB-2026-08-02 evidence archive is distributed separately as a release asset and in the complete publication dossier. Verify its SHA-256 before extracting.

```text
e8d07f3108bfaae73b165c663ba2993057d6fc844931f85ef74b3dd5b187c59c
```

The public source repository intentionally omits local absolute paths and large toolchain caches. Those remain preserved in the sealed evidence bundle for auditability.
