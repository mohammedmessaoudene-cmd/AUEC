# Authority-delta reviewer CI

The `Authority delta reviewer` job in `.github/workflows/ci.yml` complements
the existing Python test matrix. It runs for the workflow's existing pull
request events and pushes to main; it does not add a privileged event trigger.

## Execution and scope

The job uses a Windows hosted runner, PowerShell, Python 3.11 and Node 24.19.0.
Its checkout/setup actions are pinned to exact commits. Runtime setup may
download distributions; the reviewer itself uses the committed inputs and no
network service. No package dependencies are installed for the reviewer.

It invokes the existing `demo/run-review.ps1`, which checks corpus generation,
both project-controlled oracles, parser fixtures, canonicalization KATs,
assigned-reason mutations, parity, the pinned SEP projection, bounded static
scans, and the 22 selected semantic source mutations. The runner throws on
native command errors and failed reviewer gates. A final repository hash
check detects drift in regenerated tracked evidence.

The existing Python matrix is unchanged. Counts are finite test coverage, not
universal correctness. A CI pass is not a human review, external adoption,
independent organizational validation, or a certification.

## Permissions and output

The job has only `contents: read`, disables credential persistence and automatic
Node package-manager caching, and has a 15-minute job timeout. It neither
publishes an artifact nor updates branches, PRs, comments, tags or releases.
Ordinary GitHub Actions job logs are still retained by GitHub. There is no
secret input, `pull_request_target`, `continue-on-error`, or automatic retry.

Review results are regenerated in the checkout; they are not committed or
uploaded by the job. If the final hash check fails, investigate the difference
rather than regenerating and accepting expected hashes inside CI.

## Local replay

From the checkout root, with the stated runtimes on PATH:

```powershell
$ErrorActionPreference = 'Stop'
& ./experimental/mcp-composition/authority-delta-reviewer-v2_1/demo/run-review.ps1
if ($LASTEXITCODE -ne 0) { throw "Reviewer failed: $LASTEXITCODE" }
python -B scripts/check_repository_hashes.py
if ($LASTEXITCODE -ne 0) { throw "Evidence hash check failed: $LASTEXITCODE" }
```

Running these commands locally does not exercise the GitHub scheduler or the
setup actions. A first actual hosted run remains necessary after a separately
authorized publication. This job is not automatically a required branch check;
branch-protection changes require a separate repository decision.
