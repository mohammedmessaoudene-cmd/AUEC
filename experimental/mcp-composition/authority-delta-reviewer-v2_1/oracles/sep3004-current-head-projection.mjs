import crypto from 'node:crypto';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import { canonical as profileCanonical, clone, commitmentForDecision, evaluate, C14N } from './node/oracle.mjs';

const [, , sourceInput, corpusPath, outputPath] = process.argv;
const EXPECTED_HEAD = '9405ba2ff8be99b9e0005bebd0ea4b77ac4dc885';
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
const normativeRulesPresent = [
  'All values defined by this profile MUST be JSON strings',
  'An OPTIONAL field that is absent means the',
  '`sources_touched` encoding.',
  'recorded-but-empty set is carried as `null`, never as `"[]"`',
  'require **well-formed Unicode**',
  'UTF-16 code units',
  'Unicode category Cc',
  'UTF-8 byte sequences (equivalently, Unicode code-point order)',
  '**Escape minimally and encode as UTF-8.**',
  'MUST be expressed as **lowercase',
  'hexadecimal**',
].every((fragment) => source.includes(fragment));

const CORE = ['event_id', 'occurred_at', 'principal_id', 'event_type', 'tool_name', 'outcome', 'extensions', 'previous_hash', 'event_hash'];
const PROTECTED = CORE.filter((key) => key !== 'event_hash');
const CALLER_FIELDS = ['purpose_declared', 'session_id', 'invoked_by_principal_id', 'flagged',
  'sources_touched', 'sensitivity_encountered', 'output_disposition', 'human_actor_id'];
const OUTCOMES = ['allowed', 'denied', 'deferred', 'error'];
const UPSTREAM_KAT_CANONICAL = '{"event_id":"99999999-9999-9999-9999-999999999999","event_type":"tool_call","extensions":{"caller-governance":{"flagged":false,"invoked_by_principal_id":null,"purpose_declared":"reconcile June invoices","session_id":"55555555-5555-5555-5555-555555555555"},"runtime-security":{"drift_status":"confirmed","evidence_hash":"sha256:b2c547e2c8f17eafc72ef5c2d4d7b6b4d0f7437ab52bae573a9af14ff5e2d9be","policy_id":"example.org/runtime-drift@3","quarantine_decision":"quarantine","severity":"high"}},"occurred_at":"2026-06-06T12:00:00.000Z","outcome":"deferred","previous_hash":null,"principal_id":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa","tool_name":"export"}';
const UPSTREAM_KAT_DIGEST = 'f733fed9cc757165f810b778e4baba1f51a45504988e937707aaab4361b2f064';

function hasLoneSurrogate(value) {
  for (let i = 0; i < value.length; i += 1) {
    const unit = value.charCodeAt(i);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(i + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return true;
      i += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) return true;
  }
  return false;
}

function validUtcMillis(value) {
  if (typeof value !== 'string') return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{3})Z$/.exec(value);
  if (!match) return false;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const monthDays = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return month >= 1 && month <= 12 && day >= 1 && day <= monthDays[month - 1]
    && hour <= 23 && minute <= 59 && second <= 59;
}

function validateSourcesTouched(value) {
  if (value === null) return { pass: true };
  if (typeof value !== 'string') return { pass: false, reason: 'OPTIONAL_VALUE_TYPE' };
  let parsed;
  try { parsed = JSON.parse(value); } catch { return { pass: false, reason: 'SOURCES_TOUCHED_JSON_ARRAY' }; }
  if (!Array.isArray(parsed) || parsed.some((item) => typeof item !== 'string')) {
    return { pass: false, reason: 'SOURCES_TOUCHED_JSON_ARRAY' };
  }
  if (parsed.length === 0) return { pass: false, reason: 'SOURCES_TOUCHED_EMPTY_SET_MUST_BE_NULL' };
  for (const item of parsed) {
    if (item.length === 0) return { pass: false, reason: 'SOURCES_TOUCHED_EMPTY_ELEMENT' };
    if (hasLoneSurrogate(item)) return { pass: false, reason: 'SOURCES_TOUCHED_ELEMENT_LONE_SURROGATE' };
    if (item !== item.normalize('NFC')) return { pass: false, reason: 'SOURCES_TOUCHED_ELEMENT_NON_NFC' };
    try { sepString(item); } catch { return { pass: false, reason: 'SOURCES_TOUCHED_ELEMENT_PROTECTED_STRING' }; }
  }
  const normalized = [...new Set(parsed)].sort((left, right) => Buffer.compare(Buffer.from(left, 'utf8'), Buffer.from(right, 'utf8')));
  if (value !== JSON.stringify(normalized)) return { pass: false, reason: 'SOURCES_TOUCHED_NOT_CANONICAL' };
  return { pass: true };
}

function sepString(value) {
  if (hasLoneSurrogate(value)) throw new Error('SEP_LONE_SURROGATE');
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
  if (!validUtcMillis(record.occurred_at)) return { pass: false, reason: 'TIMESTAMP_INVALID' };
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
  for (const [key, value] of Object.entries(caller)) {
    if (key === 'purpose_declared') continue;
    if (key === 'flagged') {
      if (!(typeof value === 'boolean' || value === null)) return { pass: false, reason: 'FLAGGED_TYPE' };
    } else if (!(typeof value === 'string' || value === null)) return { pass: false, reason: 'OPTIONAL_VALUE_TYPE' };
  }
  if (Object.hasOwn(caller, 'sources_touched')) {
    const sources = validateSourcesTouched(caller.sources_touched);
    if (!sources.pass) return sources;
  }
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

function rehashRecord(record) {
  const body = Object.fromEntries(PROTECTED.map((key) => [key, record[key]]));
  record.event_hash = sha256Hex(Buffer.from(sepCanonical(body), 'utf8'));
  return record;
}

function callerCase(field, value) {
  const record = clone(recordA);
  record.extensions['caller-governance'][field] = value;
  try { return rehashRecord(record); } catch { return record; }
}

const currentHeadCases = [];
function recordValidationCase(id, expected, expectedReason, result) {
  const actual = result.pass ? 'PASS' : 'REJECT';
  currentHeadCases.push({
    id,
    expected,
    expectedReason,
    actual,
    actualReason: result.reason,
    pass: actual === expected && result.reason === expectedReason,
  });
}

recordValidationCase('BASE_A_CONFORMS', 'PASS', 'SEP3004_CURRENT_REGISTERED_SHAPE_PASS', validationA);
recordValidationCase('BASE_B_CONFORMS', 'PASS', 'SEP3004_CURRENT_REGISTERED_SHAPE_PASS', validationB);
recordValidationCase('OPTIONAL_ABSENT_CONFORMS', 'PASS', 'SEP3004_CURRENT_REGISTERED_SHAPE_PASS', validationA);
const optionalNullRecord = callerCase('session_id', null);
const optionalNullValidation = validateCallerGovernance(optionalNullRecord);
recordValidationCase('OPTIONAL_NULL_CONFORMS', 'PASS', 'SEP3004_CURRENT_REGISTERED_SHAPE_PASS', optionalNullValidation);
currentHeadCases.push({
  id: 'ABSENT_NULL_PROTECTED_BYTES_DISTINCT',
  expected: 'PASS',
  expectedReason: 'ABSENT_NULL_DISTINCT',
  actual: validationA.pass && optionalNullValidation.pass
    && !validationA.protectedBytes.equals(optionalNullValidation.protectedBytes)
    && recordA.event_hash !== optionalNullRecord.event_hash ? 'PASS' : 'REJECT',
  actualReason: 'ABSENT_NULL_DISTINCT',
  pass: validationA.pass && optionalNullValidation.pass
    && !validationA.protectedBytes.equals(optionalNullValidation.protectedBytes)
    && recordA.event_hash !== optionalNullRecord.event_hash,
});
recordValidationCase('FLAGGED_BOOLEAN_CONFORMS', 'PASS', 'SEP3004_CURRENT_REGISTERED_SHAPE_PASS', validateCallerGovernance(callerCase('flagged', false)));
recordValidationCase('FLAGGED_NULL_CONFORMS', 'PASS', 'SEP3004_CURRENT_REGISTERED_SHAPE_PASS', validateCallerGovernance(callerCase('flagged', null)));
recordValidationCase('FLAGGED_STRING_REJECTED', 'REJECT', 'FLAGGED_TYPE', validateCallerGovernance(callerCase('flagged', 'false')));
recordValidationCase('OPTIONAL_BOOLEAN_REJECTED', 'REJECT', 'OPTIONAL_VALUE_TYPE', validateCallerGovernance(callerCase('session_id', true)));
recordValidationCase('SOURCES_NULL_CONFORMS', 'PASS', 'SEP3004_CURRENT_REGISTERED_SHAPE_PASS', validateCallerGovernance(callerCase('sources_touched', null)));
recordValidationCase('SOURCES_SINGLETON_CONFORMS', 'PASS', 'SEP3004_CURRENT_REGISTERED_SHAPE_PASS', validateCallerGovernance(callerCase('sources_touched', '["db:primary"]')));
recordValidationCase('SOURCES_SORTED_UNICODE_CONFORMS', 'PASS', 'SEP3004_CURRENT_REGISTERED_SHAPE_PASS', validateCallerGovernance(callerCase('sources_touched', '["a","é"]')));
recordValidationCase('SOURCES_ARRAY_VALUE_REJECTED', 'REJECT', 'OPTIONAL_VALUE_TYPE', validateCallerGovernance(callerCase('sources_touched', ['db:primary'])));
recordValidationCase('SOURCES_BARE_DELIMITER_REJECTED', 'REJECT', 'SOURCES_TOUCHED_JSON_ARRAY', validateCallerGovernance(callerCase('sources_touched', 'db:primary,db:backup')));
recordValidationCase('SOURCES_EMPTY_ARRAY_STRING_REJECTED', 'REJECT', 'SOURCES_TOUCHED_EMPTY_SET_MUST_BE_NULL', validateCallerGovernance(callerCase('sources_touched', '[]')));
recordValidationCase('SOURCES_UNSORTED_REJECTED', 'REJECT', 'SOURCES_TOUCHED_NOT_CANONICAL', validateCallerGovernance(callerCase('sources_touched', '["b","a"]')));
recordValidationCase('SOURCES_DUPLICATE_REJECTED', 'REJECT', 'SOURCES_TOUCHED_NOT_CANONICAL', validateCallerGovernance(callerCase('sources_touched', '["a","a"]')));
recordValidationCase('SOURCES_EMPTY_ELEMENT_REJECTED', 'REJECT', 'SOURCES_TOUCHED_EMPTY_ELEMENT', validateCallerGovernance(callerCase('sources_touched', '[""]')));
recordValidationCase('SOURCES_NON_NFC_ELEMENT_REJECTED', 'REJECT', 'SOURCES_TOUCHED_ELEMENT_NON_NFC', validateCallerGovernance(callerCase('sources_touched', JSON.stringify(['e\u0301']))));
recordValidationCase('SOURCES_LONE_SURROGATE_REJECTED', 'REJECT', 'SOURCES_TOUCHED_ELEMENT_LONE_SURROGATE', validateCallerGovernance(callerCase('sources_touched', JSON.stringify(['\ud800']))));
recordValidationCase('UNREGISTERED_CALLER_FIELD_REJECTED', 'REJECT', 'UNREGISTERED_CALLER_GOVERNANCE_FIELD', extraFieldsValidation);
recordValidationCase('UNREGISTERED_EXTENSION_REJECTED', 'REJECT', 'UNREGISTERED_EXTENSION_TYPE', unregisteredExtensionValidation);
const invalidCalendarRecord = clone(recordA);
invalidCalendarRecord.occurred_at = '2026-02-30T12:00:00.000Z';
rehashRecord(invalidCalendarRecord);
recordValidationCase('INVALID_CALENDAR_TIMESTAMP_REJECTED', 'REJECT', 'TIMESTAMP_INVALID', validateCallerGovernance(invalidCalendarRecord));
const currentHeadCasesPass = currentHeadCases.every((item) => item.pass);

const mapping = [
  { projectedField: 'event_id', upstreamSection: 'SEP-3004 §2.1', upstreamField: 'event_id', sourceLines: '89' },
  { projectedField: 'occurred_at', upstreamSection: 'SEP-3004 §2.1/§2.3', upstreamField: 'occurred_at', sourceLines: '90,246-249' },
  { projectedField: 'principal_id', upstreamSection: 'SEP-3004 §2.1', upstreamField: 'principal_id', sourceLines: '91' },
  { projectedField: 'event_type', upstreamSection: 'SEP-3004 §2.1/§2.9', upstreamField: 'event_type', sourceLines: '92,369-378' },
  { projectedField: 'tool_name', upstreamSection: 'SEP-3004 §2.1', upstreamField: 'tool_name', sourceLines: '93' },
  { projectedField: 'outcome', upstreamSection: 'SEP-3004 §2.1.1', upstreamField: 'outcome', sourceLines: '94,105-121' },
  { projectedField: 'extensions.caller-governance.purpose_declared', upstreamSection: 'SEP-3004 §2.2', upstreamField: 'caller-governance.purpose_declared', sourceLines: '159-185' },
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
const gapSurvives = validationA.pass && validationB.pass && bytesA.equals(bytesB)
  && recordA.event_hash === recordB.event_hash && externalValidationA.verdict === 'PASS'
  && externalValidationB.verdict === 'PASS' && profileCanonical(decisionA) !== profileCanonical(decisionB)
  && commitmentA !== commitmentB && !extraFieldsValidation.pass
  && extraFieldsValidation.reason === 'UNREGISTERED_CALLER_GOVERNANCE_FIELD';
const report = {
  schemaVersion: 4,
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
    normativeRulesPresent,
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
  currentHeadRuleTests: {
    sourceLines: '159-185',
    cases: currentHeadCases,
    count: currentHeadCases.length,
    reasonTaxonomy: [...new Set(currentHeadCases.map((item) => item.actualReason))].sort(),
    allPass: currentHeadCasesPass,
  },
  currentExtensionRuleTest: {
    basis: [
      '§2.2 lines 139-157 requires registered extension type ids and typed registration fields.',
      '§2.2 lines 159-185 types caller-governance optionals and sources_touched but omits the authority-delta decision basis.',
      'C-REC-1 lines 522-525 requires registered type ids and data satisfying the registration.',
    ],
    extraCallerGovernanceFieldsAttempt: { pass: extraFieldsValidation.pass, reason: extraFieldsValidation.reason },
    unregisteredAuthorityDeltaExtensionAttempt: { pass: unregisteredExtensionValidation.pass, reason: unregisteredExtensionValidation.reason },
    conformingStructuredSolutionWithoutRegistrationChange: false,
    boundedInterpretation: 'The current registered caller-governance shape does not type the requested/hostAllowed/effective decision basis. A registration amendment or newly registered extension would be normative registry work; the hash-chain wire construction itself needs no change.',
  },
  classification: gapSurvives ? 'SCHEMA_BACKED_REPRESENTATION_GAP_CONFIRMED' : 'SCHEMA_BACKED_REPRESENTATION_GAP_CLOSED',
  patchScope: 'optional caller-governance registration fields or a separately registered extension; no new core field, chain, transport, or wire primitive',
  nonClaims: [
    'This is a counterfactual same-event comparison, not a SHA-256 collision claim.',
    'This does not prove every MCP implementation loses the decision basis outside SEP-3004 records.',
    'This does not select a normative representation or assert upstream acceptance.',
  ],
};
report.pass = head === EXPECTED_HEAD && clean && sourcePinMatched && normativeRulesPresent
  && currentHeadCasesPass && gapSurvives && validationA.pass && validationB.pass
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
