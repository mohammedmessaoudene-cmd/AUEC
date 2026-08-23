# Novelty boundary and competitor delta

> Checked against official primary sources on 2026-08-23. This is an engineering comparison, not a novelty/FTO opinion.

## ERC-8196

ERC-8196 is a final AI-agent authenticated wallet standard with policy-bound execution, target allowlists, transaction/day limits, verification and an audit chain. Its official `executeAction` surface includes `address target`, `uint256 value` and `bytes data`. VAEK therefore does not claim policy-bound agent execution; its testable delta is refusing that generic action language and exposing three typed effects with effect-specific attenuation and actual-result receipts. Source: https://eips.ethereum.org/EIPS/eip-8196

## ERC-8004

ERC-8004 is a draft identity/reputation/validation registry design with pluggable trust models proportional to value at risk; payments are orthogonal. VAEK does not claim agent discovery or tiered validation. It can consume verifier evidence while keeping hard authority deterministic. Source: https://eips.ethereum.org/EIPS/eip-8004

## ERC-7710

ERC-7710 defines smart-contract delegation, caveat enforcement, batch processing and revocation. VAEK does not claim capability delegation. Its narrower question is whether closed effect semantics and three-stage receipts reduce parser/audit burden after delegation. Source: https://eips.ethereum.org/EIPS/eip-7710

## ERC-8183

ERC-8183 defines agentic jobs, providers, evaluators, escrow states and optional hooks/opaque `optParams`. VAEK's service adapter is only an effect-control demonstration; it does not invent agentic escrow. VAEK deliberately omits a provider-selected hook and opaque forwarded bytes in R2. Source: https://eips.ethereum.org/EIPS/eip-8183

## GenLayer

GenLayer Intelligent Contracts use validator consensus/equivalence for non-deterministic LLM/web outputs. VAEK instead assumes the probabilistic decision may be wrong and constrains the downstream effect. The systems are complementary, not direct substitutes. Source: https://docs.genlayer.com/developers/intelligent-contracts/introduction

## Measured candidate contribution

The fair comparator shows that a generic wallet can match a typed transfer when it adds a dedicated parser. It also demonstrates that allowing a generic nested-call selector reopens an uninspected semantic surface. VAEK removes that surface by construction and binds requested/authorized/executed values, at the cost of much larger code, lower composability and adapter-specific engineering.

Verdict: the composition is a defensible research hypothesis with a concrete counterexample, not established scientific novelty or superiority.

