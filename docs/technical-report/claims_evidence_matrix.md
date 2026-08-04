# Claim--Evidence Matrix

| ID | Claim | Evidence | Verdict | Class |
|---|---|---|---|---|
| C01 | A remote manifest cannot widen host policy | Policy-intersection equations; runtime policy enforcement; negative tests | SUPPORTED UNDER TRUSTED POLICY-INTERPRETER ASSUMPTION | design+implementation |
| C02 | Equivalent manifests retain semantics across tested bindings | Binding architecture; official MCP results; transport tests | SUPPORTED FOR TESTED BINDINGS | executed+implementation |
| C03 | U0 has no ambient authority | U0 operation registry and default host policy | SUPPORTED FOR U0 | design+implementation |
| C04 | Output classification is monotone | Lattice rule; validation tests | SUPPORTED FOR EXPLICIT FLOW IN U0 | design+implementation |
| C05 | Result semantics distinguish epistemic status, representation, and classification | Revised normative model; current wire-compatibility note | SUPPORTED AS DESIGN; EXPLICIT SCHEMA MIGRATION PENDING | design |
| C06 | An unverified claim cannot authorize an effect | Normative authorization rule; U0 excludes claim/hypothesis outputs and admits pure effects only | SUPPORTED BY EXCLUSION IN U0; GENERAL RICH-PROFILE TRANSITIONS NOT YET IMPLEMENTED | design+U0 implementation |
| C07 | Modification of a complete receipt chain is detectable | Canonical receipts; tamper tests; collision-resistance and trusted-terminal assumptions | SUPPORTED WITH STATED ASSUMPTIONS | implementation |
| C08 | MCP 2025-11-25 active passes 39/39 | Unchanged official runner in sealed Evidence Bundle EB-2026-08-02 | SUPPORTED | executed |
| C09 | MCP 2026-07-28 pinned release-candidate profile passes 22/22 | Unchanged official runner in sealed Evidence Bundle EB-2026-08-02 | SUPPORTED FOR PINNED RELEASE CANDIDATE | executed |
| C10 | The tested MCP draft suite passes 85/85 | Unchanged official runner in sealed Evidence Bundle EB-2026-08-02 | SUPPORTED | executed |
| C11 | Four selected mechanisms causally affect official runner outcomes | Four isolated negative controls | SUPPORTED FOR SELECTED MECHANISMS | executed |
| C12 | A2A is officially conformant | Upstream TCK remains 79/80 and 76/78 | NO-GO OFFICIAL A2A CONFORMANCE | red evidence |
| C13 | AUEC reduces provider cost without quality loss | No authorized provider pilot | UNSUPPORTED; FUTURE WORK | blocked |
| C14 | The artifact is production secure | No independent red-team or certified sandbox | NO-GO PRODUCTION SECURITY | blocked |

| C15 | The contribution is a transport-independent composition of host policy intersection, epistemic authorization, and portable receipts | Related-work comparison; formal model; protocol bindings; causal controls | POSITIONED AS A BOUNDED SYSTEMS CONTRIBUTION; LEGAL OR ABSOLUTE NOVELTY NOT ESTABLISHED | design+literature |
