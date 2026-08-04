# Governance - initial research phase

## Roles

- **Project editor:** maintains the specification text and public release record.
- **Runtime maintainers:** maintain reference implementations without defining the standard unilaterally.
- **Conformance maintainers:** own public vectors, negative controls and evidence formats.
- **Security reviewers:** may veto a release that weakens a hard invariant.
- **Independent implementers:** validate portability without access to hidden reference internals.

During the initial release, Mohammed Messaoudene acts as project editor. This is not intended as permanent single-person governance.

## Decision rules

- Normative changes require a public issue, proposed text and at least one implementation or test vector.
- Security-hardening changes may be expedited, but require retrospective documentation.
- A conformance claim must identify the exact runner, commit, profile, command and raw output.
- Production status requires independent security and interoperability evidence; internal votes cannot substitute for it.

## Conflict of interest

Reviewers must disclose employment, funding or ownership interests materially related to a proposal.
