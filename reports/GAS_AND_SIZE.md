# Gas and bytecode measurements

## Runtime / initcode bytes

| Contract | Runtime | Initcode | Runtime margin |
|---|---:|---:|---:|
| VAEKKernel | 24,108 | 24,630 | 468 |
| AdapterRegistry | 2,029 | 2,244 | 22,547 |
| ResourceRegistry | 1,013 | 1,224 | 23,563 |
| ERC20TransferAdapter | 1,007 | 1,200 | 23,569 |
| BoundedSwapAdapter | 1,617 | 1,824 | 22,959 |
| ServiceEscrowAdapter | 2,622 | 2,830 | 21,954 |
| GenericPolicyWallet comparator | 2,256 | 2,490 | 22,320 |

The kernel is deployable but has only 468 bytes of EIP-170 runtime margin. This is a serious maintainability constraint.

## Representative Foundry test gas

These are whole test-call measurements and are not transaction-only production benchmarks:

- VAEK low-risk transfer lifecycle: 877,276 gas.
- VAEK bounded swap lifecycle: 1,182,876 gas.
- VAEK service funding lifecycle: 1,312,966 gas.
- Generic parsed ERC-20 transfer: 98,013 gas.
- Generic nested multicall counterexample: 190,905 gas.

Interpretation: VAEK buys a smaller semantic language and richer receipts at substantial bytecode and lifecycle cost. A publication-grade gas benchmark must isolate deployment, submit, verify and execute transactions separately.

