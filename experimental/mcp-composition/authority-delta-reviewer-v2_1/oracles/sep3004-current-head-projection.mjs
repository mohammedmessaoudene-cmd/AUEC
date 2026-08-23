import crypto from 'node:crypto';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import { canonical as profileCanonical, clone, commitmentForDecision, evaluate, C14N } from './node/oracle.mjs';

const [, , sourceInput, corpusPath, outputPath] = process.argv;
const EXPECTED_HEAD = '377f8d260ded5b6854871b2ce3c73621ffcaef1d';
const sha256Hex = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
const sha256Prefixed = (value) => `sha256:${sha256Hex(Buffer.from(profileCanonical(value), 'utf8'))}`;
let sourcePath;
let sourceBytes;
let head;
let tree;
let clean;
let sourcePinMatched;
let acquisition;
if (fs.statSync(sourceInput).isDirectory()) {
  sourcePath = `${sourceInput}/seps/3004-tamper-evident-audit-record-contract.md`;
  head = execFileSync('git', ['-C', sourceInput, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  tree = execFileSync('git', ['-C', sourceInput, 'rev-parse', 'HEAD^{tree}'], { encoding: 'utf8' }).trim();
  clean = execFileSync('git', ['-C', sourceInput, 'status', '--porcelain'], { encoding: 'utf8' }).trim() === '';
  sourceBytes = execFileSync('git', ['-C', sourceInput, 'cat-file', 'blob', 'HEAD:seps/3004-tamper-evident-audit-record-contract.md']);
  sourcePinMatched = head === EXPECTED_HEAD;
  acquisition = 'exact local Git checkout and Git blob';
} else {
  sourcePath = sourceInput;
  sourceBytes = fs.readFileSync(sourcePath);
  const pin = JSON.parse(fs.readFileSync(new URL('../upstream/SEP3004_SOURCE_PIN.json', import.meta.url), 'utf8'));
  head = pin.head;
  tree = pin.tree;
  clean = true;
  sourcePinMatched = pin.head === EXPECTED_HEAD && pin.bytes === sourceBytes.length && pin.sha256 === sha256Hex(sourceBytes);
  acquisition = 'embedded byte-pinned Git blob snapshot';
}
const source = sourceBytes.toString('utf8');

const CORE = ['event_id', 'occurred_at', 'principal_id', 'event_type', 'tool_name', 'outcome', 'extensions', 'previous_hash', 'event_hash'];
const PROTECTED = CORE.filter((key) => key !== 'event_hash');
const CALLER_FIELDS = ['purpose_declared', 'session_id', 'invoked_by_principal_id', 'flagged',
  'sources_touched', 'sensitivity_encountered', 'output_disposition', 'human_actor_id'];
const OUTCOMES = ['allowed', 'denied', 'deferred', 'error'];
const UPSTREAM_KAT_CANONICAL = '{"event_id":"99999999-9999-9999-9999-999999999999","event_type":"tool_call","extensions":{"caller-governance":{"flagged":false,"invoked_by_principal_id":null,"purpose_declared":"reconcile June invoices","session_id":"55555555-5555-5555-5555-555555555555"},"runtime-security":{"drift_status":"confirmed","evidence_hash":"sha256:b2c547e2c8f17eafc72ef5c2d4d7b6b4d0f7437ab52bae573a9af14ff5e2d9be","policy_id":"example.org/runtime-drift@3","quarantine_decision":"quarantine","severity":"high"}},"occurred_at":"2026-06-06T12:00:00.000Z","outcome":"deferred","previous_hash":null,"principal_id":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","tool_name":"export"}';
const UPSTREAM_KAT_DIGEST = 'f733fed9cc757165f810b778e4baba1f51a45504988e937707aaab4361b2f064';

function sepString(value) {
  if (value !== value.normalize('NFC')) throw new Error('SEP_NON_NFC_STRING');
  if (value !== value.replace(/^ +| +$/g, '')) throw new Error('SEP_ASCII_SPACE_NOT_CANONICAL');
  for (const char of value) {
    const cp = char.codePointAt(0);
    if ((cp >= 0 && cp <= 0x1f) || (cp >= 0x7f && cp <= 0x9f)) throw new Error('SEP_CONTROL_CHARACTER');
  }
  if (value.length > 8192) throw new Error('SEP_STRING_TOO_LONG');
  return JSON.stringify(value);
}

function sepCanonical(value) {
  if (value === null) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'string') return sepString(value);
  if (Array.isArray(value) || typeof value === 'number') throw new Error('SEP_PROTECTED_VALUE_TYPE');
  if (value && typeof value === 'object') {
    const keys = Object.keys(value).sort();
    if (keys.some((key) => !/^[\x20-\x7e]+$/.test(key))) throw new Error('SEP_REGISTRY_KEY_NOT_ASCII');
    return `{${keys.map((key) => `${JSON.stringify(key)}:${sepCanonical(value[key])}`).join(',')}}`;
  }
  throw new Error('SEP_PROTECTED_VALUE_TYPE');
}

function validateCallerGovernance(record, strictRegistration = true) {
  for (const key of CORE) if (!Object.hasOwn(record, key)) return { pass: false, reason: `MISSING_CORE_${key}` };
  if (![record.event_id, record.principal_id, record.event_type].every((value) => typeof value === 'string' && value.length > 0)) return { pass: false, reason: 'CORE_STRING_TYPE' };
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(record.occurred_at)) return { pass: false, reason: 'TIMESTAMP_TYPE' };
  if (!(typeof record.tool_name === 'string' || record.tool_name === null)) return { pass: false, reason: 'TOOL_NAME_TYPE' };
  if (!OUTCOMES.includes(record.outcome)) return { pass: false, reason: 'OUTCOME_TYPE' };
  if (!(record.previous_hash === null || /^[0-9a-f]{64}$/.test(record.previous_hash))) return { pass: false, reason: 'PREVIOUS_HASH_TYPE' };
  if (!record.extensions || typeof record.extensions !== 'object' || Array.isArray(record.extensions)) return { pass: false, reason: 'EXTENSIONS_TYPE' };
  const extensionIds = Object.keys(record.extensions);
  if (extensionIds.length !== 1 || extensionIds[0] !== 'caller-governance') return { pass: false, reason: 'UNREGISTERED_EXTENSION_TYPE' };
  const caller = record.extensions['caller-governance'];
  if (!caller || typeof caller !== 'object' || Array.isArray(caller)) return { pass: false, reason: 'CALLER_GOVERNANCE_TYPE' };
  if (strictRegistration && Object.keys(caller).some((key) => !CALLER_FIELDS.includes(key))) return { pass: false, reason: 'UNREGISTERED_CALLER_GOVERNANCE_FIELD' };
  if (typeof caller.purpose_declared !== 'string') return { pass: false, reason: 'PURPOSE_DECLARED_REQUIRED' };
  let protectedBytes;
  try {
    const body = Object.fromEntries(PROTECTED.map((key) => [key, record[key]]));
    protectedBytes = Buffer.from(sepCanonical(body), 'utf8');
  } catch (error) { return { pass: false, reason: error.message }; }
  const expectedHash = sha256Hex(protectedBytes);
  if (record.event_hash !== expectedHash) return { pass: false, reason: 'EVENT_HASH_MISMATCH' };
  return { pass: true, reason: 'SEP3004_CURRENT_REGISTERED_SHAPE_PASS', protectedBytes, expectedHash };
}

function projectToCurrentRecord(decision) {
  const withoutHash = {
    event_id: '77777777-7777-7777-7777-777777777777',
    occurred_at: '2026-08-23T12:00:00.000Z',
    principal_id: decision.principal.id,
    event_type: 'tool_call',
    tool_name: decision.tool.id,
    outcome: 'allowed',
    extensions: { 'caller-governance': { purpose_declared: 'review one local file' } },
    previous_hash: null,
  };
  const body = Object.fromEntries(PROTECTED.map((key) => [key, withoutHash[key]]));
  return { ...withoutHash, event_hash: sha256Hex(Buffer.from(sepCanonical(body), 'utf8')) };
}

const corpus = JSON.parse(fs.readFileSync(corpusPath, 'utf8'));
const baseRecord = clone(corpus.vectors.find((vector) => vector.id === 'BASE_STRUCTURED').record);
const decisionA = clone(baseRecord.decision);
const decisionB = clone(baseRecord.decision);
decisionB.decisionId = 'decision-20260823-0002';
decisionB.operations = { requested: ['read'], hostAllowed: ['read', 'write'], effective: ['read'], denied: [], reduced: [] };
decisionB.reasonCodes = ['SERVER_ADMITTED'];
const commitmentA = commitmentForDecision(decisionA);
const commitmentB = commitmentForDecision(decisionB);
const externalRecordA = {
  decision: decisionA,
  decisionEvidence: { form: 'structured+digest', algorithm: 'sha-256', canonicalization: C14N, digest: commitmentA },
};
const externalRecordB = {
  decision: decisionB,
  decisionEvidence: { form: 'structured+digest', algorithm: 'sha-256', canonicalization: C14N, digest: commitmentB },
};
const externalValidationA = evaluate(externalRecordA);
const externalValidationB = evaluate(externalRecordB);
const recordA = projectToCurrentRecord(decisionA);
const recordB = projectToCurrentRecord(decisionB);
const validationA = validateCallerGovernance(recordA);
const validationB = validateCallerGovernance(recordB);
const bytesA = validationA.protectedBytes;
const bytesB = validationB.protectedBytes;

const extraFieldsAttempt = clone(recordA);
extraFieldsAttempt.extensions['caller-governance'].requested_operations = 'read write';
extraFieldsAttempt.event_hash = sha256Hex(Buffer.from(sepCanonical(Object.fromEntries(PROTECTED.map((key) => [key, extraFieldsAttempt[key]]))), 'utf8'));
const extraFieldsValidation = validateCallerGovernance(extraFieldsAttempt, true);

const unregisteredExtensionAttempt = clone(recordA);
unregisteredExtensionAttempt.extensions['authority-delta'] = { decision_digest: commitmentA };
unregisteredExtensionAttempt.event_hash = sha256Hex(Buffer.from(sepCanonical(Object.fromEntries(PROTECTED.map((key) => [key, unregisteredExtensionAttempt[key]]))), 'utf8'));
const unregisteredExtensionValidation = validateCallerGovernance(unregisteredExtensionAttempt, true);

const mapping = [
  { projectedField: 'event_id', upstreamSection: 'SEP-3004 §2.1', upstreamField: 'event_id', sourceLines: '89' },
  { projectedField: 'occurred_at', upstreamSection: 'SEP-3004 §2.1/§2.3', upstreamField: 'occurred_at', sourceLines: '90,246-249' },
  { projectedField: 'principal_id', upstreamSection: 'SEP-3004 §2.1', upstreamField: 'principal_id', sourceLines: '91' },
  { projectedField: 'event_type', upstreamSection: 'SEP-3004 §2.1/§2.9', upstreamField: 'event_type', sourceLines: '92,369-378' },
  { projectedField: 'tool_name', upstreamSection: 'SEP-3004 §2.1', upstreamField: 'tool_name', sourceLines: '93' },
  { projectedField: 'outcome', upstreamSection: 'SEP-3004 §2.1.1', upstreamField: 'outcome', sourceLines: '94,105-121' },
  { projectedField: 'extensions.caller-governance.purpose_declared', upstreamSection: 'SEP-3004 §2.2', upstreamField: 'caller-governance.purpose_declared', sourceLines: '125-163' },
  { projectedField: 'previous_hash', upstreamSection: 'SEP-3004 §2.1/§2.4', upstreamField: 'previous_hash', sourceLines: '96,284-289' },
  { projectedField: 'event_hash', upstreamSection: 'SEP-3004 §2.1/§2.4', upstreamField: 'event_hash', sourceLines: '97,284-294' },
];

const protectedCanonical = bytesA.toString('utf8');
const upstreamKatBody = {
  event_id: '99999999-9999-9999-9999-999999999999',
  event_type: 'tool_call',
  extensions: {
    'caller-governance': {
      flagged: false,
      invoked_by_principal_id: null,
      purpose_declared: 'reconcile June invoices',
      session_id: '55555555-5555-5555-5555-555555555555',
    },
    'runtime-security': {
      drift_status: 'confirmed',
      evidence_hash: 'sha256:b2c547e2c8f17eafc72ef5c2d4d7b6b4d0f7437ab52bae573a9af14ff5e2d9be',
      policy_id: 'example.org/runtime-drift@3',
      quarantine_decision: 'quarantine',
      severity: 'high',
    },
  },
  occurred_at: '2026-06-06T12:00:00.000Z',
  outcome: 'deferred',
  previous_hash: null,
  principal_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  tool_name: 'export',
};
const upstreamKatActualCanonical = sepCanonical(upstreamKatBody);
const upstreamKatActualDigest = sha256Hex(Buffer.from(upstreamKatActualCanonical, 'utf8'));
const report = {
  schemaVersion: 3,
  source: {
    repository: 'modelcontextprotocol/modelcontextprotocol',
    pullRequest: 3004,
    head,
    expectedHead: EXPECTED_HEAD,
    tree,
    clean,
    sourcePinMatched,
    acquisition,
    file: 'seps/3004-tamper-evident-audit-record-contract.md',
    fileSha256: `sha256:${sha256Hex(sourceBytes)}`,
  },
  upstreamFieldMapping: mapping,
  upstreamKnownAnswer: {
    sourceLines: '541-573',
    expectedCanonicalUtf8: UPSTREAM_KAT_CANONICAL,
    actualCanonicalUtf8: upstreamKatActualCanonical,
    canonicalBytesEqual: upstreamKatActualCanonical === UPSTREAM_KAT_CANONICAL,
    expectedSha256: UPSTREAM_KAT_DIGEST,
    actualSha256: upstreamKatActualDigest,
    digestEqual: upstreamKatActualDigest === UPSTREAM_KAT_DIGEST,
  },
  decisionA: {
    requested: decisionA.operations.requested,
    hostAllowed: decisionA.operations.hostAllowed,
    effective: decisionA.operations.effective,
    externalDecisionCanonicalization: C14N,
    externalDecisionDigest: commitmentA,
  },
  decisionB: {
    requested: decisionB.operations.requested,
    hostAllowed: decisionB.operations.hostAllowed,
    effective: decisionB.operations.effective,
    externalDecisionCanonicalization: C14N,
    externalDecisionDigest: commitmentB,
  },
  currentRegisteredCallerGovernance: {
    recordA,
    recordB,
    validationA: { pass: validationA.pass, reason: validationA.reason },
    validationB: { pass: validationB.pass, reason: validationB.reason },
    protectedCanonicalUtf8: protectedCanonical,
    protectedCanonicalUtf8Hex: bytesA.toString('hex'),
    protectedByteLength: bytesA.length,
    bytesEqual: bytesA.equals(bytesB),
    eventHashA: recordA.event_hash,
    eventHashB: recordB.event_hash,
    eventHashesEqual: recordA.event_hash === recordB.event_hash,
  },
  externalProfileSeparation: {
    validationA: externalValidationA,
    validationB: externalValidationB,
    canonicalDecisionBytesEqual: profileCanonical(decisionA) === profileCanonical(decisionB),
    commitmentA,
    commitmentB,
    commitmentsDifferent: commitmentA !== commitmentB,
  },
  currentExtensionRuleTest: {
    basis: [
      '§2.2 lines 127-153 requires registered extension type ids and typed registration fields.',
      '§2.2 lines 159-163 enumerates the current caller-governance required/optional fields and omits the authority-delta decision basis.',
      'C-REC-1 lines 500-503 requires registered type ids and data satisfying the registration.',
    ],
    extraCallerGovernanceFieldsAttempt: { pass: extraFieldsValidation.pass, reason: extraFieldsValidation.reason },
    unregisteredAuthorityDeltaExtensionAttempt: { pass: unregisteredExtensionValidation.pass, reason: unregisteredExtensionValidation.reason },
    conformingStructuredSolutionWithoutRegistrationChange: false,
    boundedInterpretation: 'The current registered caller-governance shape does not type the requested/hostAllowed/effective decision basis. A registration amendment or newly registered extension would be normative registry work; the hash-chain wire construction itself needs no change.',
  },
  classification: 'SCHEMA_BACKED_REPRESENTATION_GAP_CONFIRMED',
  patchScope: 'optional caller-governance registration fields or a separately registered extension; no new core field, chain, transport, or wire primitive',
  nonClaims: [
    'This is a counterfactual same-event comparison, not a SHA-256 collision claim.',
    'This does not prove every MCP implementation loses the decision basis outside SEP-3004 records.',
    'This does not select a normative representation or assert upstream acceptance.',
  ],
};
report.pass = head === EXPECTED_HEAD && clean && sourcePinMatched && validationA.pass && validationB.pass
  && report.upstreamKnownAnswer.canonicalBytesEqual && report.upstreamKnownAnswer.digestEqual
  && bytesA.equals(bytesB) && recordA.event_hash === recordB.event_hash
  && externalValidationA.verdict === 'PASS' && externalValidationB.verdict === 'PASS'
  && profileCanonical(decisionA) !== profileCanonical(decisionB) && commitmentA !== commitmentB
  && !extraFieldsValidation.pass && !unregisteredExtensionValidation.pass
  && mapping.length === PROTECTED.length + 1;
fs.writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({ pass: report.pass, head, recordsConforming: validationA.pass && validationB.pass,
  protectedBytesEqual: bytesA.equals(bytesB), eventHashesEqual: recordA.event_hash === recordB.event_hash,
  externalCommitmentsDifferent: commitmentA !== commitmentB, classification: report.classification }));
if (!report.pass) process.exitCode = 1;

export { sepCanonical, validateCallerGovernance };
