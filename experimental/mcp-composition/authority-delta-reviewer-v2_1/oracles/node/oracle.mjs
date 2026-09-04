import crypto from 'node:crypto';
import fs from 'node:fs';

const PROFILE = 'auec-authority-delta-decision-v2_1';
const C14N = 'auec-authority-delta-c14n-v2_1';
const SAFE = BigInt(Number.MAX_SAFE_INTEGER);
const SHA256_RE = /^sha256:[0-9a-f]{64}$/;
const RFC3339_MS_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const LIMITS = Object.freeze({
  documentBytes: 262144,
  depth: 64,
  nodes: 10000,
  stringBytes: 16384,
  totalStringBytes: 131072,
  integerDigits: 16,
  decimalDigits: 64,
});

class ProfileError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

function fail(code) { throw new ProfileError(code); }
function utf8(value) { return Buffer.from(value, 'utf8'); }
function compareUtf8(a, b) { return Buffer.compare(utf8(a), utf8(b)); }
function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
}
function hasLoneSurrogate(value) {
  for (let i = 0; i < value.length; i += 1) {
    const unit = value.charCodeAt(i);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      if (i + 1 >= value.length) return true;
      const next = value.charCodeAt(i + 1);
      if (next < 0xdc00 || next > 0xdfff) return true;
      i += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) return true;
  }
  return false;
}

function validateString(value, state) {
  if (hasLoneSurrogate(value)) fail('LONE_SURROGATE');
  if (value !== value.normalize('NFC')) fail('NON_NFC_STRING');
  const bytes = Buffer.byteLength(value, 'utf8');
  if (bytes > LIMITS.stringBytes) fail('LIMIT_STRING_BYTES');
  state.totalStringBytes += bytes;
  if (state.totalStringBytes > LIMITS.totalStringBytes) fail('LIMIT_TOTAL_STRING_BYTES');
}

function canonical(value) {
  const state = { nodes: 0, totalStringBytes: 0 };
  const walk = (item, depth) => {
    if (depth > LIMITS.depth) fail('LIMIT_DEPTH');
    state.nodes += 1;
    if (state.nodes > LIMITS.nodes) fail('LIMIT_NODES');
    if (item === null) return 'null';
    if (typeof item === 'boolean') return item ? 'true' : 'false';
    if (typeof item === 'number') {
      if (!Number.isSafeInteger(item)) fail('UNSAFE_INTEGER');
      return String(item);
    }
    if (typeof item === 'string') {
      validateString(item, state);
      return JSON.stringify(item);
    }
    if (Array.isArray(item)) return `[${item.map((entry) => walk(entry, depth + 1)).join(',')}]`;
    if (isPlainObject(item)) {
      const keys = Object.keys(item);
      for (const key of keys) validateString(key, state);
      keys.sort(compareUtf8);
      return `{${keys.map((key) => `${JSON.stringify(key)}:${walk(item[key], depth + 1)}`).join(',')}}`;
    }
    fail('UNSUPPORTED_JSON_TYPE');
  };
  return walk(value, 1);
}

function sha(value) {
  return `sha256:${crypto.createHash('sha256').update(canonical(value), 'utf8').digest('hex')}`;
}

function inspectRawJson(raw) {
  if (typeof raw !== 'string') fail('JSON_SYNTAX');
  if (Buffer.byteLength(raw, 'utf8') > LIMITS.documentBytes) fail('LIMIT_DOCUMENT_BYTES');
  let i = 0;
  const state = { nodes: 0, totalStringBytes: 0 };
  const whitespace = () => {
    while (i < raw.length && (raw[i] === ' ' || raw[i] === '\t' || raw[i] === '\r' || raw[i] === '\n')) i += 1;
  };
  const stringToken = () => {
    whitespace();
    if (raw[i] !== '"') fail('JSON_SYNTAX');
    const start = i;
    i += 1;
    while (i < raw.length) {
      const code = raw.charCodeAt(i);
      if (raw[i] === '\\') {
        i += 1;
        if (i >= raw.length) fail('JSON_SYNTAX');
        if (raw[i] === 'u') {
          if (!/^[0-9a-fA-F]{4}$/.test(raw.slice(i + 1, i + 5))) fail('JSON_SYNTAX');
          i += 5;
        } else {
          if (!'"\\/bfnrt'.includes(raw[i])) fail('JSON_SYNTAX');
          i += 1;
        }
        continue;
      }
      if (raw[i] === '"') {
        i += 1;
        let value;
        try { value = JSON.parse(raw.slice(start, i)); } catch { fail('JSON_SYNTAX'); }
        validateString(value, state);
        return value;
      }
      if (code < 0x20) fail('JSON_SYNTAX');
      i += 1;
    }
    fail('JSON_SYNTAX');
  };
  const numberToken = () => {
    whitespace();
    const match = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(raw.slice(i));
    if (!match) fail('JSON_SYNTAX');
    const token = match[0];
    i += token.length;
    if (/[.eE]/.test(token)) fail('FLOAT_NOT_ALLOWED');
    const magnitude = token.startsWith('-') ? token.slice(1) : token;
    if (magnitude.length > LIMITS.integerDigits) fail('LIMIT_INTEGER_DIGITS');
    if (BigInt(magnitude) > SAFE) fail('UNSAFE_INTEGER');
  };
  const value = (depth) => {
    if (depth > LIMITS.depth) fail('LIMIT_DEPTH');
    state.nodes += 1;
    if (state.nodes > LIMITS.nodes) fail('LIMIT_NODES');
    whitespace();
    const ch = raw[i];
    if (ch === '{') return object(depth);
    if (ch === '[') return array(depth);
    if (ch === '"') { stringToken(); return; }
    if (ch === '-' || (ch >= '0' && ch <= '9')) { numberToken(); return; }
    for (const literal of ['true', 'false', 'null']) {
      if (raw.startsWith(literal, i)) { i += literal.length; return; }
    }
    fail('JSON_SYNTAX');
  };
  const object = (depth) => {
    i += 1;
    const keys = new Set();
    whitespace();
    if (raw[i] === '}') { i += 1; return; }
    while (true) {
      const key = stringToken();
      if (keys.has(key)) fail('DUPLICATE_JSON_KEY');
      keys.add(key);
      whitespace();
      if (raw[i] !== ':') fail('JSON_SYNTAX');
      i += 1;
      value(depth + 1);
      whitespace();
      if (raw[i] === '}') { i += 1; return; }
      if (raw[i] !== ',') fail('JSON_SYNTAX');
      i += 1;
    }
  };
  const array = (depth) => {
    i += 1;
    whitespace();
    if (raw[i] === ']') { i += 1; return; }
    while (true) {
      value(depth + 1);
      whitespace();
      if (raw[i] === ']') { i += 1; return; }
      if (raw[i] !== ',') fail('JSON_SYNTAX');
      i += 1;
    }
  };
  value(1);
  whitespace();
  if (i !== raw.length) fail('JSON_SYNTAX');
}

function parseStrict(raw) {
  inspectRawJson(raw);
  let value;
  try { value = JSON.parse(raw); } catch { fail('JSON_SYNTAX'); }
  canonical(value);
  return value;
}

function reject(reason) { return { verdict: 'REJECT', reason }; }
function accept(reason = 'PROFILE_ACCEPT') { return { verdict: 'PASS', reason }; }
function exactObject(value, allowed, required = allowed) {
  if (!isPlainObject(value)) return 'SCHEMA_TYPE';
  const unknown = Object.keys(value).filter((key) => !allowed.includes(key));
  if (unknown.length) return 'SCHEMA_UNKNOWN_FIELD';
  if (required.some((key) => !Object.hasOwn(value, key))) return 'SCHEMA_REQUIRED_FIELD_MISSING';
  return null;
}
function nonempty(value) { return typeof value === 'string' && value.length > 0; }
function digest(value) { return typeof value === 'string' && SHA256_RE.test(value); }
function validRfc3339Ms(value) {
  if (typeof value !== 'string' || !RFC3339_MS_RE.test(value)) return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{3})Z$/.exec(value);
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  if (year === 0 || month < 1 || month > 12 || hour > 23 || minute > 59 || second > 59) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day >= 1 && day <= days[month - 1];
}
function extensionKeysNonempty(value) {
  if (Array.isArray(value)) return value.every(extensionKeysNonempty);
  if (!isPlainObject(value)) return true;
  return Object.entries(value).every(([key, child]) => key.length > 0 && extensionKeysNonempty(child));
}
function decimal(value) {
  if (typeof value !== 'string' || !/^(0|[1-9][0-9]*)$/.test(value) || value.length > LIMITS.decimalDigits) return null;
  return BigInt(value);
}
function sortedStringSet(value) {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string' || item.length === 0)) return false;
  if (new Set(value).size !== value.length) return false;
  const sorted = [...value].sort(compareUtf8);
  return value.every((item, index) => item === sorted[index]);
}
function arrayEquals(a, b) { return a.length === b.length && a.every((item, index) => item === b[index]); }

function commitmentForDecision(decision) { return sha(decision); }

function validateDecision(decision) {
  const keys = ['schemaVersion', 'canonicalization', 'decisionId', 'decidedAt', 'authorityEvaluator', 'policy',
    'principal', 'server', 'tool', 'actionDigest', 'declaration', 'admission', 'operations', 'budgets',
    'listState', 'anchor', 'idempotencyContractDigest', 'reasonCodes', 'extensions'];
  let error = exactObject(decision, keys);
  if (error) return error;
  if (decision.schemaVersion !== PROFILE || decision.canonicalization !== C14N) return 'DECISION_VERSION';
  if (!nonempty(decision.decisionId) || !nonempty(decision.authorityEvaluator)) return 'DECISION_IDENTITY_TYPE';
  if (!validRfc3339Ms(decision.decidedAt)) return 'INVALID_RFC3339_INSTANT';

  error = exactObject(decision.policy, ['id', 'revision']); if (error) return error;
  error = exactObject(decision.principal, ['id']); if (error) return error;
  error = exactObject(decision.server, ['id']); if (error) return error;
  error = exactObject(decision.tool, ['id']); if (error) return error;
  if (![decision.policy.id, decision.policy.revision, decision.principal.id, decision.server.id, decision.tool.id].every(nonempty)) return 'DECISION_IDENTITY_TYPE';
  if (!digest(decision.actionDigest)) return 'ACTION_DIGEST_TYPE';

  error = exactObject(decision.declaration, ['digest', 'authenticated']); if (error) return error;
  if (!digest(decision.declaration.digest)) return 'DECLARATION_DIGEST_TYPE';
  if (typeof decision.declaration.authenticated !== 'boolean') return 'DECLARATION_AUTH_TYPE';
  if (decision.declaration.authenticated !== true) return 'DECLARATION_UNAUTHENTICATED';

  error = exactObject(decision.admission, ['reference', 'digest', 'status']); if (error) return error;
  if (!nonempty(decision.admission.reference) || !digest(decision.admission.digest)) return 'ADMISSION_TYPE';
  if (decision.admission.status !== 'admitted') return 'SERVER_NOT_ADMITTED';

  error = exactObject(decision.operations, ['requested', 'hostAllowed', 'effective', 'denied', 'reduced']); if (error) return error;
  for (const key of ['requested', 'hostAllowed', 'effective', 'denied', 'reduced']) {
    if (!sortedStringSet(decision.operations[key])) return `${key.toUpperCase()}_SET_INVALID`;
  }
  const requested = decision.operations.requested;
  const allowedSet = new Set(decision.operations.hostAllowed);
  const effective = requested.filter((item) => allowedSet.has(item));
  const denied = requested.filter((item) => !allowedSet.has(item));
  const effectiveSet = new Set(effective);
  const reduced = requested.filter((item) => !effectiveSet.has(item));
  if (!arrayEquals(decision.operations.effective, effective)) return 'EFFECTIVE_NOT_EXACT_INTERSECTION';
  if (!arrayEquals(decision.operations.denied, denied)) return 'DENIED_SET_MISMATCH';
  if (!arrayEquals(decision.operations.reduced, reduced)) return 'REDUCED_SET_MISMATCH';

  error = exactObject(decision.budgets, ['unit', 'requested', 'hostAllowed', 'effective', 'denied', 'reduced']); if (error) return error;
  if (!nonempty(decision.budgets.unit)) return 'BUDGET_TYPE';
  const requestedBudget = decimal(decision.budgets.requested);
  const allowedBudget = decimal(decision.budgets.hostAllowed);
  const effectiveBudget = decimal(decision.budgets.effective);
  const deniedBudget = decimal(decision.budgets.denied);
  const reducedBudget = decimal(decision.budgets.reduced);
  if ([requestedBudget, allowedBudget, effectiveBudget, deniedBudget, reducedBudget].some((item) => item === null)) return 'BUDGET_TYPE';
  const exactEffective = requestedBudget < allowedBudget ? requestedBudget : allowedBudget;
  if (effectiveBudget !== exactEffective) return effectiveBudget > exactEffective ? 'BUDGET_INCREASE' : 'BUDGET_EFFECTIVE_NOT_EXACT_MIN';
  const exactDenied = requestedBudget > allowedBudget ? requestedBudget - allowedBudget : 0n;
  if (deniedBudget !== exactDenied) return 'BUDGET_DENIED_MISMATCH';
  if (reducedBudget !== requestedBudget - effectiveBudget) return 'BUDGET_REDUCED_MISMATCH';

  error = exactObject(decision.listState, ['epoch', 'digest', 'materialChange', 'regated']); if (error) return error;
  if (!nonempty(decision.listState.epoch) || !digest(decision.listState.digest)
      || typeof decision.listState.materialChange !== 'boolean' || typeof decision.listState.regated !== 'boolean') return 'LIST_STATE_TYPE';
  if (decision.listState.materialChange && !decision.listState.regated) return 'MATERIAL_CHANGE_REQUIRES_REGATE';

  error = exactObject(decision.anchor, ['id', 'generation', 'captureGeneration', 'settlementGeneration', 'state', 'deactivatedAfterBinding']); if (error) return error;
  if (![decision.anchor.id, decision.anchor.generation, decision.anchor.captureGeneration, decision.anchor.settlementGeneration].every(nonempty)
      || typeof decision.anchor.deactivatedAfterBinding !== 'boolean') return 'ANCHOR_TYPE';
  if (decision.anchor.state === 'deactivated-before-binding') return 'PREBINDING_INACTIVE';
  if (decision.anchor.state !== 'bound') return 'BINDING_STATE';
  if (decision.anchor.captureGeneration !== decision.anchor.generation) return 'FUTURE_CAPTURE_REJECTED';
  if (decision.anchor.settlementGeneration !== decision.anchor.generation) return 'HISTORICAL_BINDING_MISMATCH';
  if (!digest(decision.idempotencyContractDigest)) return 'IDEMPOTENCY_DIGEST_TYPE';
  if (!sortedStringSet(decision.reasonCodes)) return 'REASON_CODES_INVALID';
  if (!isPlainObject(decision.extensions)) return 'EXTENSIONS_TYPE';
  if (!extensionKeysNonempty(decision.extensions)) return 'EXTENSION_KEY';
  const reductionExists = decision.operations.denied.length > 0 || decision.operations.reduced.length > 0
    || deniedBudget > 0n || reducedBudget > 0n;
  if (reductionExists && decision.reasonCodes.length === 0) return 'REASON_CODES_REQUIRED';
  return null;
}

function validateDecisionEvidence(evidence, decision) {
  if (isPlainObject(evidence) && Object.hasOwn(evidence, 'form') && evidence.form !== 'structured+digest') {
    return 'UNSUPPORTED_PUBLIC_FORM';
  }
  const error = exactObject(evidence, ['form', 'algorithm', 'canonicalization', 'digest']);
  if (error) return error === 'SCHEMA_REQUIRED_FIELD_MISSING' ? 'DECISION_COMMITMENT_MISSING' : error;
  if (evidence.form !== 'structured+digest') return 'UNSUPPORTED_PUBLIC_FORM';
  if (evidence.algorithm !== 'sha-256') return 'DECISION_ALGORITHM_UNSUPPORTED';
  if (evidence.canonicalization !== C14N || !digest(evidence.digest)) return 'DECISION_COMMITMENT_TYPE';
  if (evidence.digest !== commitmentForDecision(decision)) return 'DECISION_COMMITMENT_SUBSTITUTED';
  return null;
}

function evaluate(record) {
  try { canonical(record); } catch (error) { return reject(error.code || error.message); }
  const error = exactObject(record, ['decision', 'decisionEvidence']);
  if (error) return reject(record && typeof record === 'object' ? error : 'RECORD_TYPE');
  const decisionError = validateDecision(record.decision);
  if (decisionError) return reject(decisionError);
  const evidenceError = validateDecisionEvidence(record.decisionEvidence, record.decision);
  if (evidenceError) return reject(evidenceError);
  return accept('PASS_STRUCTURED_DECISION');
}

function clone(value) { return JSON.parse(JSON.stringify(value)); }

const MUTATION_OPERATORS = [
  'unknown-top-level', 'unknown-decision-field', 'effective-escalation', 'denied-set-mismatch',
  'reduced-set-mismatch', 'budget-increase', 'budget-denied-mismatch', 'declaration-unauthenticated',
  'admission-denied', 'future-capture', 'material-list-not-regated', 'reason-codes-unsorted',
  'evidence-digest-substitution', 'algorithm-substitution', 'idempotency-digest-invalid', 'committed-extension-substitution',
];

const MUTATION_REASONS = [
  'SCHEMA_UNKNOWN_FIELD', 'SCHEMA_UNKNOWN_FIELD', 'EFFECTIVE_NOT_EXACT_INTERSECTION',
  'DENIED_SET_MISMATCH', 'REDUCED_SET_MISMATCH', 'BUDGET_INCREASE', 'BUDGET_DENIED_MISMATCH',
  'DECLARATION_UNAUTHENTICATED', 'SERVER_NOT_ADMITTED', 'FUTURE_CAPTURE_REJECTED',
  'MATERIAL_CHANGE_REQUIRES_REGATE', 'REASON_CODES_INVALID', 'DECISION_COMMITMENT_SUBSTITUTED',
  'DECISION_ALGORITHM_UNSUPPORTED', 'IDEMPOTENCY_DIGEST_TYPE', 'DECISION_COMMITMENT_SUBSTITUTED',
];

function mutateByOperator(record, operatorIndex, index) {
  const marker = `mutation-${operatorIndex}-${index}`;
  if (operatorIndex === 0) record[`unknown_${index}`] = marker;
  if (operatorIndex === 1) record.decision[`unknown_${index}`] = marker;
  if (operatorIndex === 2) { record.decision.extensions.mutationMarker = marker; record.decision.operations.effective.push(`write:${index}`); record.decision.operations.effective.sort(compareUtf8); }
  if (operatorIndex === 3) { record.decision.extensions.mutationMarker = marker; record.decision.operations.denied = [`denied:${index}`]; }
  if (operatorIndex === 4) { record.decision.extensions.mutationMarker = marker; record.decision.operations.reduced = [`reduced:${index}`]; }
  if (operatorIndex === 5) { record.decision.extensions.mutationMarker = marker; record.decision.budgets.effective = String(1000 + index); }
  if (operatorIndex === 6) { record.decision.extensions.mutationMarker = marker; record.decision.budgets.denied = String(1000 + index); }
  if (operatorIndex === 7) { record.decision.extensions.mutationMarker = marker; record.decision.declaration.authenticated = false; }
  if (operatorIndex === 8) { record.decision.extensions.mutationMarker = marker; record.decision.admission.status = 'denied'; }
  if (operatorIndex === 9) { record.decision.extensions.mutationMarker = marker; record.decision.anchor.captureGeneration = String(1000 + index); }
  if (operatorIndex === 10) { record.decision.extensions.mutationMarker = marker; record.decision.listState.epoch = `epoch-${index}`; record.decision.listState.materialChange = true; record.decision.listState.regated = false; }
  if (operatorIndex === 11) { record.decision.extensions.mutationMarker = marker; record.decision.reasonCodes = [`Z-${index}`, `A-${index}`]; }
  if (operatorIndex === 12) { record.decision.extensions.mutationMarker = marker; record.decisionEvidence.digest = `sha256:${index.toString(16).padStart(64, '0')}`; }
  if (operatorIndex === 13) { record.decision.extensions.mutationMarker = marker; record.decisionEvidence.algorithm = `unsupported-${index}`; }
  if (operatorIndex === 14) { record.decision.extensions.mutationMarker = marker; record.decision.idempotencyContractDigest = `invalid-${index}`; }
  if (operatorIndex === 15) record.decision.extensions.mutationMarker = marker;
  if ((operatorIndex >= 2 && operatorIndex <= 11) || operatorIndex === 14) {
    record.decisionEvidence.digest = commitmentForDecision(record.decision);
  }
}

function mutationSuite(base, count = 4096) {
  if (count !== 4096) fail('MUTATION_COUNT_MUST_BE_4096');
  const digests = [];
  const reasons = {};
  const operators = {};
  let unexpectedAcceptance = 0;
  let unexpectedReason = 0;
  for (let index = 0; index < count; index += 1) {
    const operatorIndex = Math.floor(index / 256);
    const operator = MUTATION_OPERATORS[operatorIndex];
    const instance = index % 256;
    const record = clone(base);
    mutateByOperator(record, operatorIndex, instance);
    const result = evaluate(record);
    if (result.verdict !== 'REJECT') unexpectedAcceptance += 1;
    if (result.verdict !== 'REJECT' || result.reason !== MUTATION_REASONS[operatorIndex]) unexpectedReason += 1;
    reasons[result.reason] = (reasons[result.reason] || 0) + 1;
    operators[operator] = (operators[operator] || 0) + 1;
    digests.push(sha({ operator, instance, record }));
  }
  return {
    count,
    unique: new Set(digests).size,
    operatorCount: MUTATION_OPERATORS.length,
    operators,
    corpusRoot: `sha256:${crypto.createHash('sha256').update(digests.join('\n'), 'utf8').digest('hex')}`,
    unexpectedAcceptance,
    unexpectedReason,
    semanticResealedCount: 2816,
    reasonCounts: Object.fromEntries(Object.entries(reasons).sort(([a], [b]) => compareUtf8(a, b))),
  };
}

function causalControls(base) {
  const cases = [
    ['effective-escalation', (r) => { r.decision.operations.effective.push('write'); return () => { r.decision.operations.effective.pop(); }; }],
    ['policy-revision-substitution', (r) => { const old = r.decision.policy.revision; r.decision.policy.revision = 'policy-other'; return () => { r.decision.policy.revision = old; }; }],
    ['anchor-id-substitution', (r) => { const old = r.decision.anchor.id; r.decision.anchor.id = 'anchor-other'; return () => { r.decision.anchor.id = old; }; }],
    ['extension-substitution', (r) => { r.decision.extensions.transient = 'changed'; return () => { delete r.decision.extensions.transient; }; }],
    ['action-digest-substitution', (r) => { const old = r.decision.actionDigest; r.decision.actionDigest = `sha256:${'f'.repeat(64)}`; return () => { r.decision.actionDigest = old; }; }],
  ];
  return cases.map(([id, perturb]) => {
    const record = clone(base);
    const identity = record;
    const beforeBytes = Buffer.from(canonical(record), 'utf8');
    const beforeDigest = sha(record);
    const green = evaluate(record);
    const restore = perturb(record);
    const red = evaluate(record);
    restore();
    const afterBytes = Buffer.from(canonical(record), 'utf8');
    const afterDigest = sha(record);
    const restored = evaluate(record);
    return {
      id, sameObject: record === identity, green, red, restored,
      beforeDigest, afterDigest, byteEquality: beforeBytes.equals(afterBytes),
      pass: record === identity && beforeBytes.equals(afterBytes) && beforeDigest === afterDigest
        && green.verdict === 'PASS' && red.verdict === 'REJECT' && restored.verdict === 'PASS',
    };
  });
}

function fileRestorationControl(base, outputPath) {
  const fixturePath = `${outputPath}.causal-restored.json`;
  const before = Buffer.from(`${canonical(base)}\n`, 'utf8');
  fs.writeFileSync(fixturePath, before);
  const mutated = clone(base);
  mutated.decision.extensions.fileMutation = 'same-path-red-control';
  fs.writeFileSync(fixturePath, `${canonical(mutated)}\n`, 'utf8');
  const red = evaluate(parseStrict(fs.readFileSync(fixturePath, 'utf8')));
  fs.writeFileSync(fixturePath, before);
  const after = fs.readFileSync(fixturePath);
  const restored = evaluate(parseStrict(after.toString('utf8')));
  return {
    path: `results/${fixturePath.replace(/\\/g, '/').split('/').pop()}`,
    samePath: true,
    beforeSha256: `sha256:${crypto.createHash('sha256').update(before).digest('hex')}`,
    afterSha256: `sha256:${crypto.createHash('sha256').update(after).digest('hex')}`,
    byteEquality: before.equals(after), red, restored,
    pass: before.equals(after) && red.verdict === 'REJECT' && restored.verdict === 'PASS',
  };
}

function knownAnswerTests(kats) {
  return kats.cases.map((item) => {
    let actualCanonical;
    let actualDigest;
    let error = null;
    try {
      actualCanonical = canonical(item.value);
      actualDigest = sha(item.value);
    } catch (caught) { error = caught.code || caught.message; }
    const actualHex = actualCanonical === undefined ? null : Buffer.from(actualCanonical, 'utf8').toString('hex');
    return {
      id: item.id, expectedCanonicalUtf8Hex: item.canonicalUtf8Hex, actualCanonicalUtf8Hex: actualHex,
      expectedDigest: item.digest, actualDigest, error,
      pass: !error && actualHex === item.canonicalUtf8Hex && actualDigest === item.digest,
    };
  });
}

function args() {
  const output = {};
  for (let i = 2; i < process.argv.length; i += 2) output[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
  return output;
}

function main() {
  const options = args();
  const corpus = parseStrict(fs.readFileSync(options.vectors, 'utf8'));
  const kats = parseStrict(fs.readFileSync(options.kats, 'utf8'));
  const vectors = corpus.vectors.map((vector) => {
    const actual = evaluate(vector.record);
    return { id: vector.id, kind: vector.kind, expected: vector.expected, ...actual,
      expectationMatched: actual.verdict === vector.expected.verdict && actual.reason === vector.expected.reason };
  });
  const parser = fs.readFileSync(options.parser, 'utf8').trim().split(/\r?\n/).filter(Boolean).map((line) => {
    const fixture = JSON.parse(line);
    let actual;
    try {
      const parsed = parseStrict(fixture.raw);
      actual = fixture.operation === 'parse-only' ? accept('PARSE_PASS') : evaluate(parsed);
    } catch (error) { actual = reject(error.code || error.message); }
    return { id: fixture.id, expected: fixture.expected, ...actual,
      expectationMatched: actual.verdict === fixture.expected.verdict && actual.reason === fixture.expected.reason };
  });
  const base = corpus.vectors.find((vector) => vector.id === 'BASE_STRUCTURED').record;
  const report = {
    schemaVersion: 3,
    profile: PROFILE,
    canonicalization: C14N,
    implementation: 'node-independent-v2_1',
    runtimeFamily: 'node',
    limits: LIMITS,
    vectorCount: vectors.length,
    kindCount: new Set(corpus.vectors.map((vector) => vector.kind)).size,
    vectors,
    parser,
    knownAnswerTests: knownAnswerTests(kats),
    mutations: mutationSuite(base),
    causalControls: causalControls(base),
  };
  report.fileRestorationControl = fileRestorationControl(base, options.output);
  report.pass = vectors.every((item) => item.expectationMatched)
    && parser.every((item) => item.expectationMatched)
    && report.knownAnswerTests.every((item) => item.pass)
    && report.mutations.count === 4096 && report.mutations.unique === 4096
    && report.mutations.operatorCount >= 16 && report.mutations.unexpectedAcceptance === 0
    && report.mutations.unexpectedReason === 0
    && report.causalControls.every((item) => item.pass) && report.fileRestorationControl.pass;
  fs.writeFileSync(options.output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify({ implementation: report.implementation, pass: report.pass, vectors: report.vectorCount,
    kinds: report.kindCount, parser: report.parser.length, kats: report.knownAnswerTests.length,
    mutations: report.mutations.count, operators: report.mutations.operatorCount }));
  if (!report.pass) process.exitCode = 1;
}

if (process.argv[1] && /oracle\.mjs$/i.test(process.argv[1])) main();

export { PROFILE, C14N, LIMITS, canonical, sha, parseStrict, evaluate, commitmentForDecision,
  mutationSuite, causalControls, compareUtf8, clone };
