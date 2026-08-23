# ADR-004 — Compile the R2 kernel through Solidity IR

Status: accepted after the first P03 compile failure.

The typed request and receipt structures caused a Solidity `stack too deep` failure in the legacy code generator. R2 enables the pinned Solidity 0.8.24 `via_ir` pipeline with optimization rather than deleting bound fields or collapsing typed interfaces. This is a compiler configuration change, not a security-property relaxation. CI and every local build use the same setting.

Risk: IR compilation adds a compiler-path assumption. The compiler remains exactly pinned and all behavioral tests, bytecode-size measurements and static review run against the emitted IR bytecode.

