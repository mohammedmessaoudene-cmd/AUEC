# Publication strategy

## What can be published immediately after the IP election

- GitHub public repository as a pre-release;
- source-only archive;
- technical report/preprint;
- sealed EB-2026-08-02 evidence as a release asset;
- Zenodo software record and DOI;
- draft MCP SEP for community discussion;
- independent implementer challenge.

## What does not need to be complete before initial publication

- A2A official conformance;
- macOS execution;
- external red-team;
- independent clean-room implementation;
- provider pilot;
- production-grade U2;
- formal standards adoption.

These are validation and production gates. They must remain visible, but waiting for all of them would prevent the public review needed to close them.

## Release labels

Use:

```text
pre-standard
research software
engineering alpha
conformance evidence checkpoint
not production ready
```

Do not use:

```text
world standard
DARPA certified
production secure
official A2A conformant
patented / patent pending (unless true)
```

## Recommended publication order

1. Resolve the IP release gate.
2. Create the public GitHub repository from `public-repo/`.
3. Replace placeholder repository URLs and assign a controlled extension namespace.
4. Run the release checklist and publish a GitHub pre-release.
5. Enable GitHub-Zenodo integration or create a manual Zenodo software deposit.
6. Reserve a DOI, insert it into the report metadata and publish the record.
7. Publish the technical report/preprint.
8. Open a discussion/issue with the MCP community before or alongside a formal SEP.
9. Invite independent implementers and security reviewers.
