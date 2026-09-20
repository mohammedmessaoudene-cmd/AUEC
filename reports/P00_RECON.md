# P00 — Repository reconnaissance and evidence inventory

> RESEARCH PROTOTYPE — NOT AUDITED — NO PRODUCTION FUNDS

PHASE: P00 repository reconnaissance  
INPUT COMMIT: `e1dda3b01c94d427cda75f10535d8fddf86c2c02`  
OBJECTIVE: Establish the exact repository, evidence, branch, workflow and secret boundary before R2 implementation.

## Hypotheses and exit conditions

- H0: the handoff may be stale or incomplete; the actual repository is authoritative for observed state.
- H1: the seven packaged R1 artifacts should match the historical branch byte-for-byte by Git blob identity.
- Exit: clean dedicated local branch, exact base SHA, verified artifact map, workflow classification, bounded secret scan, assumptions and tool snapshot.

## Repository state

- Repository: `https://github.com/mohammedmessaoudene-cmd/AUEC`
- Historical branch: `bv-aic-r1-ci-20260822`
- Exact base: `e1dda3b01c94d427cda75f10535d8fddf86c2c02`
- Dedicated branch: `codex/vaek-r2-effect-kernel` (created locally; not pushed during P00)
- Default branch observed remotely: `main` at `6bb9e83fa7ca5abdc9bf08f8454725820d161090`
- Existing open PR observed: draft PR #2, unrelated head `codex/mcp-authority-composition-spike`.
- Initial checkout was clean.

## Evidence map

The handoff's seven Git blob IDs were independently reproduced:

| Artifact | Git blob |
|---|---|
| `bv-aic-r1/contracts/BVAICAuthority.sol` | `747dec93d51cbf802808406aa8c02d28e98d669f` |
| `bv-aic-r1/contracts/MockERC20.sol` | `19838e7cbfb1899d7c97d117c45b35a376b00f3` |
| `bv-aic-r1/test/BVAICAuthority.t.sol` | `c14a7e9c94fe6d66c65de15419559cd856b85650` |
| `bv-aic-r1/test/BVAICInvariant.t.sol` | `ad1a27212407e639ff8825fe03d8f28084e28bd5` |
| `bv-aic-r1/foundry.toml` | `dedce057b21901b21088d7b242c30c0873ca879e` |
| `bv-aic-r1/scripts/anvil_deploy_smoke.sh` | `c92d5f79ab5ef300f2b377450c92527d7a73c798` |
| `bv-aic-r1/reports/FOUNDRY_CI_PASS.txt` | `99411f9cc35219e9222f4def86a11857eeaba290` |

The package validation and SHA-256 inventory both returned `PASS`. The ZIP SHA-256 is `235402bd91a6238225756a68727ecb5d66e907bed54e5fdaa3931f346b439cb9`.

## Workflow classification

- `.github/workflows/ci.yml`: stable repository Python CI; read-only contents permission; relevant to avoiding regressions outside R2.
- `.github/workflows/bv-aic-r1.yml`: reproducible Foundry steps are useful, but the workflow also performs a push-triggered public Shido deployment, grants `contents: write`, and commits generated evidence. Those external/public steps are not copied into R2 CI.
- `bv-aic-r1/scripts/anvil_deploy_smoke.sh`: mandatory local baseline proof.
- `deploy_sepolia.sh`, `shido_public_deploy.sh`, `zenith_public_deploy.sh`: external experiments only; not mandatory and not run in R2.

## Secret and unsafe-artifact scan

Commands used a repository-wide filename scan followed by narrowed patterns for 32-byte literals, PEM private keys and quoted secret assignments. Result:

- no PEM private key;
- no checked-in production credential identified;
- one 32-byte literal is the standard public Anvil development key in the local smoke script;
- two `PRIVATE_KEY` assignments generate fresh ephemeral keys at runtime in historical public-testnet scripts;
- public RPC endpoints and environment-variable references are present, but no external deployment is authorized or attempted.

This is a bounded regex scan, not a complete secret-audit proof.

## Files changed

- `reports/P00_RECON.md`
- `reports/ASSUMPTION_REGISTER.md`
- `reports/TOOL_VERSIONS.txt`

## Commands

```text
git ls-remote --heads https://github.com/mohammedmessaoudene-cmd/AUEC.git
gh repo clone ... --branch bv-aic-r1-ci-20260822 --single-branch
git switch -c codex/vaek-r2-effect-kernel
git ls-tree -r --name-only HEAD
gh pr list --state open ...
git hash-object -- <seven baseline files>
python scripts/validate_package.py
python scripts/verify_sha256.py
rg ... secret-pattern inventory
```

## Observed results

- Package validation: PASS.
- Package SHA-256 validation: PASS.
- Core R1 provenance: all seven blob IDs match.
- Foundry and Anvil: unavailable on the initial Windows PATH; remediation deferred to P01.

## Failures, causes and corrections

- Failure: initial `forge --version` and `anvil --version` were unavailable.
- Root cause: Foundry was not installed on this host PATH.
- Correction plan: install the exact official v1.7.1 Windows binaries and record their hashes/source before baseline execution.
- No baseline test has yet been claimed PASS from this host.

## Committee objections

- EVM: historical CI mixes semantic testing with public faucet/RPC activity and self-committing evidence.
- Formal methods: historical test counts establish only exercised properties, not schema closure or proof.
- AI safety: R1 supports only a transfer-shaped authority and does not establish closed multi-effect semantics.
- Red team: regex scanning is not a substitute for history-wide secret analysis; remote external scripts remain risky if triggered.
- Interoperability: existing AUEC terminology and publication artifacts must not be silently relabeled as VAEK evidence.

## Gate verdict

`P00_PASS`

REMAINING RISKS: Foundry toolchain missing; baseline not yet locally reproduced; target branch not yet pushed; public repository visibility if later pushed.  
NEXT PHASE: P01 exact R1 reproduction with pinned Foundry/Anvil.

