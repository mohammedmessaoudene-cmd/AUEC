# VAEK R2 — Verifiable AI Effect Kernel

> RESEARCH PROTOTYPE — NOT AUDITED — NO PRODUCTION FUNDS — DO NOT DEPLOY TO MAINNET

VAEK R2 tests a narrow hypothesis: a probabilistic agent should express only closed typed effects, while a deterministic kernel owns authorization, risk controls, adapter selection, execution and receipts.

Implemented effects:

- `TRANSFER_ERC20`
- `SWAP_EXACT_INPUT`
- `BUY_SERVICE_ESCROW`

The AI bridge cannot submit a target, selector, adapter address or executable byte payload. The Solidity entry points and adapters are effect-specific.

## Reproduce locally

Requires Foundry v1.7.1, Solidity 0.8.24 and Python 3.11 with PyCryptodome for the independent receipt verifier.

```bash
forge fmt --check
forge build --sizes
forge test -vvv
PYTHONPATH=agent python -m unittest discover -s agent/tests -v
PYTHONPATH=tools/receipt_verifier python -m unittest discover -s tools/receipt_verifier -p 'test_*.py' -v
python tools/check_prohibited_surfaces.py
bash scripts/anvil_demo.sh
```

Evidence and limitations are in the repository-level `reports/` directory. Passing tests do not constitute an audit or proof of novelty.

