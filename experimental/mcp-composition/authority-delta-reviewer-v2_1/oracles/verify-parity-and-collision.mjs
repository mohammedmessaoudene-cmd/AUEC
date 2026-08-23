import fs from 'node:fs';
import { canonical, commitmentForDecision, clone } from './node/oracle.mjs';

const [, , nodePath, pythonPath, corpusPath, outputPath] = process.argv;
const node = JSON.parse(fs.readFileSync(nodePath, 'utf8'));
const python = JSON.parse(fs.readFileSync(pythonPath, 'utf8'));
const corpus = JSON.parse(fs.readFileSync(corpusPath, 'utf8'));
const select = (items) => items.map(({ id, verdict, reason, expectationMatched }) => ({ id, verdict, reason, expectationMatched }));
const stripCausal = (items) => items.map(({ id, sameObject, green, red, restored, beforeDigest, afterDigest, byteEquality, pass }) => (
  { id, sameObject, green, red, restored, beforeDigest, afterDigest, byteEquality, pass }
));
const stripFile = ({ samePath, beforeSha256, afterSha256, byteEquality, red, restored, pass }) => (
  { samePath, beforeSha256, afterSha256, byteEquality, red, restored, pass }
);

const vectorParity = canonical(select(node.vectors)) === canonical(select(python.vectors));
const parserParity = canonical(select(node.parser)) === canonical(select(python.parser));
const katParity = canonical(node.knownAnswerTests) === canonical(python.knownAnswerTests);
const mutationParity = canonical(node.mutations) === canonical(python.mutations);
const causalParity = canonical(stripCausal(node.causalControls)) === canonical(stripCausal(python.causalControls));
const fileRestorationParity = canonical(stripFile(node.fileRestorationControl)) === canonical(stripFile(python.fileRestorationControl));

const base = clone(corpus.vectors.find((vector) => vector.id === 'BASE_STRUCTURED').record);
const commitmentControls = [
  ['policy-id', (d) => { d.policy.id = 'authority-policy-other'; }],
  ['policy-revision', (d) => { d.policy.revision = 'policy-8'; }],
  ['principal-id', (d) => { d.principal.id = 'did:example:bob'; }],
  ['server-id', (d) => { d.server.id = 'mcp://other-server'; }],
  ['tool-id', (d) => { d.tool.id = 'files.write'; }],
  ['action-digest', (d) => { d.actionDigest = `sha256:${'1'.repeat(64)}`; }],
  ['admission-reference', (d) => { d.admission.reference = 'admission-8'; }],
  ['requested-operations', (d) => { d.operations.requested = ['read']; d.operations.denied = []; d.operations.reduced = []; }],
  ['host-allowed-operations', (d) => { d.operations.hostAllowed = ['read', 'write']; }],
  ['budget-requested', (d) => { d.budgets.requested = '101'; d.budgets.denied = '21'; d.budgets.reduced = '21'; }],
  ['list-epoch', (d) => { d.listState.epoch = 'list-8'; }],
  ['anchor-id', (d) => { d.anchor.id = 'anchor-8'; }],
  ['anchor-generation', (d) => { d.anchor.generation = '8'; d.anchor.captureGeneration = '8'; d.anchor.settlementGeneration = '8'; }],
  ['idempotency-contract', (d) => { d.idempotencyContractDigest = `sha256:${'2'.repeat(64)}`; }],
  ['reason-codes', (d) => { d.reasonCodes = ['SERVER_ADMITTED']; }],
  ['extensions', (d) => { d.extensions.tenantId = 'tenant-b'; }],
].map(([id, mutate]) => {
  const changed = clone(base.decision);
  mutate(changed);
  const originalDigest = commitmentForDecision(base.decision);
  const changedDigest = commitmentForDecision(changed);
  return { id, originalDigest, changedDigest, different: originalDigest !== changedDigest };
});

const tenantA = corpus.vectors.find((vector) => vector.id === 'COMMITTED_EXTENSION_TENANT_A').record;
const tenantB = corpus.vectors.find((vector) => vector.id === 'COMMITTED_EXTENSION_TENANT_B').record;
const extensionCollisionControl = {
  tenantA: tenantA.decisionEvidence.digest,
  tenantB: tenantB.decisionEvidence.digest,
  decisionsDifferent: canonical(tenantA.decision) !== canonical(tenantB.decision),
  commitmentsDifferent: tenantA.decisionEvidence.digest !== tenantB.decisionEvidence.digest,
};

const report = {
  schemaVersion: 3,
  nodePass: node.pass,
  pythonPass: python.pass,
  vectorParity,
  parserParity,
  katParity,
  mutationParity,
  causalParity,
  fileRestorationParity,
  canonicalizationDigestParity: node.knownAnswerTests.map((item, index) => ({
    id: item.id,
    node: item.actualDigest,
    python: python.knownAnswerTests[index].actualDigest,
    equal: item.actualDigest === python.knownAnswerTests[index].actualDigest,
  })),
  commitmentControls,
  extensionCollisionControl,
  scopeGates: {
    vectorsAtLeast48: node.vectorCount >= 48 && python.vectorCount >= 48,
    kindsAtLeast16: node.kindCount >= 16 && python.kindCount >= 16,
    parserAtLeast24: node.parser.length >= 24 && python.parser.length >= 24,
    katsAtLeast3: node.knownAnswerTests.length >= 3 && python.knownAnswerTests.length >= 3,
    mutationsExact4096: node.mutations.count === 4096 && python.mutations.count === 4096,
    operatorsAtLeast16: node.mutations.operatorCount >= 16 && python.mutations.operatorCount >= 16,
    unexpectedAcceptanceZero: node.mutations.unexpectedAcceptance === 0 && python.mutations.unexpectedAcceptance === 0,
  },
  boundedConclusion: 'The narrowed V2.1 Core has cross-language byte/digest parity on the pinned domain, a closed structured decision schema, and an explicit fully committed extensions map.',
  nonClaims: [
    'This does not make the profile normative MCP text.',
    'This does not establish production deployment, upstream acceptance, effect occurrence, provider truth, retry behavior, or payment semantics.',
    'Finite vectors and mutations do not prove universal correctness.',
  ],
};
report.pass = node.pass && python.pass && vectorParity && parserParity && katParity && mutationParity
  && causalParity && fileRestorationParity
  && report.canonicalizationDigestParity.every((item) => item.equal)
  && commitmentControls.every((item) => item.different)
  && extensionCollisionControl.decisionsDifferent && extensionCollisionControl.commitmentsDifferent
  && Object.values(report.scopeGates).every(Boolean);
fs.writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({ pass: report.pass, vectorParity, parserParity, katParity, mutationParity,
  causalParity, fileRestorationParity, committedFieldControls: commitmentControls.length,
  extensionCommitmentsDifferent: extensionCollisionControl.commitmentsDifferent }));
if (!report.pass) process.exitCode = 1;
