import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { C14N, PROFILE, sha, commitmentForDecision, clone } from '../oracles/node/oracle.mjs';

const here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/(?:[A-Za-z]:)/, (match) => match.slice(1)));
const zero = (char = '0') => `sha256:${char.repeat(64)}`;
const payload = { capabilities: ['read', 'write'], name: 'files.read', version: '2026-08-23' };
const action = { arguments: { encoding: 'utf-8', path: '/review/example.txt' }, tool: 'files.read' };
const admission = { server: 'mcp://review-server', policy: 'admission-policy-7' };
const list = { entries: ['files.read'], epoch: 'list-7' };

const baseDecision = {
  schemaVersion: PROFILE,
  canonicalization: C14N,
  decisionId: 'decision-20260823-0001',
  decidedAt: '2026-08-23T12:00:00.000Z',
  authorityEvaluator: 'auec-local-reviewer-v2_1',
  policy: { id: 'authority-policy', revision: 'policy-7' },
  principal: { id: 'did:example:alice' },
  server: { id: 'mcp://review-server' },
  tool: { id: 'files.read' },
  actionDigest: sha(action),
  declaration: { digest: sha(payload), authenticated: true },
  admission: { reference: 'admission-7', digest: sha(admission), status: 'admitted' },
  operations: {
    requested: ['read', 'write'], hostAllowed: ['read'], effective: ['read'], denied: ['write'], reduced: ['write'],
  },
  budgets: { unit: 'calls', requested: '100', hostAllowed: '80', effective: '80', denied: '20', reduced: '20' },
  listState: { epoch: 'list-7', digest: sha(list), materialChange: false, regated: false },
  anchor: {
    id: 'anchor-7', generation: '7', captureGeneration: '7', settlementGeneration: '7',
    state: 'bound', deactivatedAfterBinding: false,
  },
  idempotencyContractDigest: sha({ contract: 'single-effect-idempotent', profile: PROFILE }),
  reasonCodes: ['AUTHORITY_REDUCED', 'SERVER_ADMITTED'],
  extensions: { profileStatus: 'external-review-profile', tenantId: 'tenant-a' },
};

function seal(record) {
  record.decisionEvidence = {
    form: 'structured+digest',
    algorithm: 'sha-256',
    canonicalization: C14N,
    digest: commitmentForDecision(record.decision),
  };
}

function noReduction(record) {
  record.decision.operations = {
    requested: ['read'], hostAllowed: ['read', 'write'], effective: ['read'], denied: [], reduced: [],
  };
  record.decision.budgets = {
    unit: 'calls', requested: '80', hostAllowed: '100', effective: '80', denied: '0', reduced: '0',
  };
  record.decision.reasonCodes = [];
}

const vectors = [];
function add(id, kind, expected, mutate = () => {}, afterSeal = () => {}) {
  const record = { decision: clone(baseDecision), decisionEvidence: null };
  mutate(record);
  seal(record);
  afterSeal(record);
  vectors.push({ id, kind, record, expected });
}
const pass = { verdict: 'PASS', reason: 'PASS_STRUCTURED_DECISION' };
const reject = (reason) => ({ verdict: 'REJECT', reason });

add('BASE_STRUCTURED', 'public-form', pass);
add('BASE_NO_REDUCTION', 'public-form', pass, noReduction);
add('DIGEST_ONLY_FORM', 'public-form', reject('UNSUPPORTED_PUBLIC_FORM'), () => {}, (r) => {
  r.decisionEvidence.form = 'digest-only';
});
add('EVIDENCE_REF_FORM', 'public-form', reject('UNSUPPORTED_PUBLIC_FORM'), () => {}, (r) => {
  r.decisionEvidence.form = 'digest+evidenceRef';
  r.decisionEvidence.evidenceRef = 'https://review.example.edu/evidence/decision-0001.json';
});
add('EFFECT_FIELD', 'public-form', reject('SCHEMA_UNKNOWN_FIELD'), () => {}, (r) => {
  r.effect = { disposition: 'not-observed' };
});
add('MODE_FIELD', 'public-form', reject('SCHEMA_UNKNOWN_FIELD'), () => {}, (r) => { r.mode = 'B'; });

add('DECLARATION_CONTROL', 'declaration', pass);
add('DECLARATION_UNAUTHENTICATED', 'declaration', reject('DECLARATION_UNAUTHENTICATED'), (r) => {
  r.decision.declaration.authenticated = false;
});
add('DECLARATION_DIGEST_TYPE', 'declaration', reject('DECLARATION_DIGEST_TYPE'), (r) => {
  r.decision.declaration.digest = 'not-a-digest';
});
add('DECLARATION_AUTH_TYPE', 'declaration', reject('DECLARATION_AUTH_TYPE'), (r) => {
  r.decision.declaration.authenticated = 'true';
});

add('ADMISSION_CONTROL', 'admission', pass);
add('ADMISSION_DENIED', 'admission', reject('SERVER_NOT_ADMITTED'), (r) => { r.decision.admission.status = 'denied'; });
add('ADMISSION_REFERENCE_EMPTY', 'admission', reject('ADMISSION_TYPE'), (r) => { r.decision.admission.reference = ''; });

add('OPERATIONS_EXACT', 'operation-delta', pass);
add('OPERATIONS_ESCALATION', 'operation-delta', reject('EFFECTIVE_NOT_EXACT_INTERSECTION'), (r) => {
  r.decision.operations.effective = ['read', 'write'];
});
add('OPERATIONS_UNDERSTATEMENT', 'operation-delta', reject('EFFECTIVE_NOT_EXACT_INTERSECTION'), (r) => {
  r.decision.operations.effective = [];
});
add('OPERATIONS_DENIED_MISMATCH', 'operation-delta', reject('DENIED_SET_MISMATCH'), (r) => {
  r.decision.operations.denied = [];
});
add('OPERATIONS_REDUCED_MISMATCH', 'operation-delta', reject('REDUCED_SET_MISMATCH'), (r) => {
  r.decision.operations.reduced = [];
});
add('OPERATIONS_SET_CONTROL', 'operation-set', pass);
add('OPERATIONS_REQUESTED_UNSORTED', 'operation-set', reject('REQUESTED_SET_INVALID'), (r) => {
  r.decision.operations.requested = ['write', 'read'];
});
add('OPERATIONS_REQUESTED_DUPLICATE', 'operation-set', reject('REQUESTED_SET_INVALID'), (r) => {
  r.decision.operations.requested = ['read', 'read'];
});

add('BUDGET_EXACT', 'budget-delta', pass);
add('BUDGET_INCREASE', 'budget-delta', reject('BUDGET_INCREASE'), (r) => { r.decision.budgets.effective = '81'; });
add('BUDGET_UNDERSTATEMENT', 'budget-delta', reject('BUDGET_EFFECTIVE_NOT_EXACT_MIN'), (r) => {
  r.decision.budgets.effective = '79';
});
add('BUDGET_DENIED_MISMATCH', 'budget-delta', reject('BUDGET_DENIED_MISMATCH'), (r) => {
  r.decision.budgets.denied = '19';
});
add('BUDGET_REDUCED_MISMATCH', 'budget-delta', reject('BUDGET_REDUCED_MISMATCH'), (r) => {
  r.decision.budgets.reduced = '19';
});
add('BUDGET_BOOLEAN', 'numeric-domain', reject('BUDGET_TYPE'), (r) => { r.decision.budgets.effective = true; });
add('BUDGET_LARGE_DECIMAL_STRING', 'numeric-domain', pass, (r) => {
  const requested = 900719925474099300000000000000n;
  const allowed = 80n;
  r.decision.budgets.requested = String(requested);
  r.decision.budgets.hostAllowed = String(allowed);
  r.decision.budgets.effective = String(allowed);
  r.decision.budgets.denied = String(requested - allowed);
  r.decision.budgets.reduced = String(requested - allowed);
});

add('IDENTITY_CONTROL', 'identity-binding', pass);
add('POLICY_REVISION_EMPTY', 'identity-binding', reject('DECISION_IDENTITY_TYPE'), (r) => {
  r.decision.policy.revision = '';
});
add('PRINCIPAL_EMPTY', 'identity-binding', reject('DECISION_IDENTITY_TYPE'), (r) => { r.decision.principal.id = ''; });
add('DECISION_ID_EMPTY', 'identity-binding', reject('DECISION_IDENTITY_TYPE'), (r) => { r.decision.decisionId = ''; });
add('ACTION_DIGEST_INVALID', 'identity-binding', reject('ACTION_DIGEST_TYPE'), (r) => {
  r.decision.actionDigest = 'sha256:1234';
});

add('RFC3339_CONTROL', 'rfc3339', pass, (r) => { r.decision.decidedAt = '2028-02-29T23:59:59.999Z'; });
add('INVALID_MONTH_DAY_TIME_VECTOR', 'rfc3339', reject('INVALID_RFC3339_INSTANT'), (r) => {
  r.decision.decidedAt = '2026-13-40T25:61:61.999Z';
});
add('INVALID_NONLEAP_DAY_VECTOR', 'rfc3339', reject('INVALID_RFC3339_INSTANT'), (r) => {
  r.decision.decidedAt = '2025-02-29T12:00:00.000Z';
});
add('RFC3339_FORMAT_INVALID', 'rfc3339', reject('INVALID_RFC3339_INSTANT'), (r) => {
  r.decision.decidedAt = '2026-08-23';
});

add('ANCHOR_BOUND', 'generation-binding', pass);
add('ANCHOR_PREBINDING_INACTIVE', 'generation-binding', reject('PREBINDING_INACTIVE'), (r) => {
  r.decision.anchor.state = 'deactivated-before-binding';
});
add('ANCHOR_FUTURE_CAPTURE', 'generation-binding', reject('FUTURE_CAPTURE_REJECTED'), (r) => {
  r.decision.anchor.captureGeneration = '8';
});
add('ANCHOR_SETTLEMENT_SUBSTITUTED', 'generation-binding', reject('HISTORICAL_BINDING_MISMATCH'), (r) => {
  r.decision.anchor.settlementGeneration = '8';
});
add('ANCHOR_POST_BINDING_DEACTIVATED', 'generation-binding', pass, (r) => {
  r.decision.anchor.deactivatedAfterBinding = true;
});

add('LIST_MATERIAL_REGATED', 'list-regating', pass, (r) => {
  r.decision.listState.materialChange = true;
  r.decision.listState.regated = true;
  r.decision.listState.epoch = 'list-8';
});
add('LIST_MATERIAL_NOT_REGATED', 'list-regating', reject('MATERIAL_CHANGE_REQUIRES_REGATE'), (r) => {
  r.decision.listState.materialChange = true;
  r.decision.listState.regated = false;
});
add('LIST_DIGEST_INVALID', 'list-regating', reject('LIST_STATE_TYPE'), (r) => { r.decision.listState.digest = 'bad'; });

add('IDEMPOTENCY_CONTROL', 'idempotency', pass);
add('IDEMPOTENCY_DIGEST_INVALID', 'idempotency', reject('IDEMPOTENCY_DIGEST_TYPE'), (r) => {
  r.decision.idempotencyContractDigest = 'bad';
});

add('REASON_CODES_SORTED', 'reason-codes', pass);
add('REASON_CODES_UNSORTED', 'reason-codes', reject('REASON_CODES_INVALID'), (r) => {
  r.decision.reasonCodes = ['Z_REASON', 'A_REASON'];
});
add('REASON_CODES_DUPLICATE', 'reason-codes', reject('REASON_CODES_INVALID'), (r) => {
  r.decision.reasonCodes = ['A_REASON', 'A_REASON'];
});
add('REASON_CODES_EMPTY_WITH_REDUCTION', 'reason-codes', reject('REASON_CODES_REQUIRED'), (r) => {
  r.decision.reasonCodes = [];
});
add('REASON_CODES_EMPTY_NO_REDUCTION', 'reason-codes', pass, noReduction);

add('ROOT_EXACT_CONTROL', 'closed-root', pass);
add('UNKNOWN_TOP_LEVEL', 'closed-root', reject('SCHEMA_UNKNOWN_FIELD'), () => {}, (r) => { r.tenantId = 'tenant-b'; });
add('MISSING_DECISION', 'closed-root', reject('SCHEMA_REQUIRED_FIELD_MISSING'), () => {}, (r) => { delete r.decision; });
add('DECISION_EXACT_CONTROL', 'closed-decision', pass);
add('UNKNOWN_DECISION_FIELD', 'closed-decision', reject('SCHEMA_UNKNOWN_FIELD'), (r) => {
  r.decision.retry = { attempt: 1 };
});
add('UNKNOWN_NESTED_POLICY_FIELD', 'closed-decision', reject('SCHEMA_UNKNOWN_FIELD'), (r) => {
  r.decision.policy.tenantId = 'tenant-b';
});
add('MISSING_ANCHOR_ID', 'closed-decision', reject('SCHEMA_REQUIRED_FIELD_MISSING'), (r) => {
  delete r.decision.anchor.id;
});
add('EXTENSIONS_NOT_OBJECT', 'closed-decision', reject('EXTENSIONS_TYPE'), (r) => { r.decision.extensions = []; });

add('COMMITTED_EXTENSION_TENANT_A', 'extension-commitment', pass, (r) => { r.decision.extensions.tenantId = 'tenant-a'; });
add('COMMITTED_EXTENSION_TENANT_B', 'extension-commitment', pass, (r) => { r.decision.extensions.tenantId = 'tenant-b'; });
add('EXTENSION_KEY_CONTROL', 'extension-key', pass, (r) => { r.decision.extensions.nested = { key: 'value' }; });
add('EMPTY_EXTENSION_KEY_VECTOR', 'extension-key', reject('EXTENSION_KEY'), (r) => { r.decision.extensions[''] = 'invalid'; });
add('NESTED_EMPTY_EXTENSION_KEY', 'extension-key', reject('EXTENSION_KEY'), (r) => {
  r.decision.extensions.nested = { '': 'invalid' };
});

add('COMMITMENT_CONTROL', 'decision-commitment', pass);
add('COMMITMENT_SUBSTITUTED', 'decision-commitment', reject('DECISION_COMMITMENT_SUBSTITUTED'), () => {}, (r) => {
  r.decisionEvidence.digest = zero('1');
});
add('COMMITMENT_ALGORITHM_UNKNOWN', 'decision-commitment', reject('DECISION_ALGORITHM_UNSUPPORTED'), () => {}, (r) => {
  r.decisionEvidence.algorithm = 'sha-512';
});
add('COMMITMENT_CANONICALIZATION_UNKNOWN', 'decision-commitment', reject('DECISION_COMMITMENT_TYPE'), () => {}, (r) => {
  r.decisionEvidence.canonicalization = 'unknown-c14n';
});
add('COMMITMENT_MISSING_DIGEST', 'decision-commitment', reject('DECISION_COMMITMENT_MISSING'), () => {}, (r) => {
  delete r.decisionEvidence.digest;
});

const parserFixtures = [];
function fixture(id, raw, verdict, reason, operation = 'parse-only') {
  parserFixtures.push({ id, operation, raw, expected: { verdict, reason } });
}
const rawVector = (id) => JSON.stringify(vectors.find((item) => item.id === id).record);
fixture('PARSER_SAFE_OBJECT', '{"a":1,"b":[true,null,"é"]}', 'PASS', 'PARSE_PASS');
fixture('PARSER_UTF8_KEY_ORDER', '{"😀":"astral","":"bmp"}', 'PASS', 'PARSE_PASS');
fixture('DUPLICATE_KEY', '{"a":1,"a":2}', 'REJECT', 'DUPLICATE_JSON_KEY');
fixture('LONE_SURROGATE', '{"x":"\\ud800"}', 'REJECT', 'LONE_SURROGATE');
fixture('PARSER_VALID_SURROGATE_PAIR', '{"x":"\\ud83d\\ude00"}', 'PASS', 'PARSE_PASS');
fixture('OVERLONG_INTEGER', `{"x":${'9'.repeat(5000)}}`, 'REJECT', 'LIMIT_INTEGER_DIGITS');
fixture('PARSER_UNSAFE_INTEGER', '{"x":9007199254740992}', 'REJECT', 'UNSAFE_INTEGER');
fixture('PARSER_FLOAT', '{"x":1.5}', 'REJECT', 'FLOAT_NOT_ALLOWED');
fixture('OVER_DEPTH', `${'['.repeat(1200)}0${']'.repeat(1200)}`, 'REJECT', 'LIMIT_DEPTH');
fixture('PARSER_DEPTH_63_ARRAYS', `${'['.repeat(63)}0${']'.repeat(63)}`, 'PASS', 'PARSE_PASS');
fixture('PARSER_DEPTH_64_ARRAYS', `${'['.repeat(64)}0${']'.repeat(64)}`, 'REJECT', 'LIMIT_DEPTH');
fixture('PARSER_NODE_LIMIT_CONTROL', `[${new Array(9999).fill('0').join(',')}]`, 'PASS', 'PARSE_PASS');
fixture('PARSER_NODE_LIMIT_EXCEEDED', `[${new Array(10000).fill('0').join(',')}]`, 'REJECT', 'LIMIT_NODES');
fixture('PARSER_STRING_LIMIT_EXCEEDED', JSON.stringify('x'.repeat(16385)), 'REJECT', 'LIMIT_STRING_BYTES');
fixture('PARSER_TOTAL_STRING_LIMIT_EXCEEDED', JSON.stringify(new Array(9).fill('x'.repeat(15000))), 'REJECT', 'LIMIT_TOTAL_STRING_BYTES');
fixture('PARSER_DOCUMENT_LIMIT_EXCEEDED', JSON.stringify('x'.repeat(262145)), 'REJECT', 'LIMIT_DOCUMENT_BYTES');
fixture('PARSER_NON_NFC', JSON.stringify({ x: 'e\u0301' }), 'REJECT', 'NON_NFC_STRING');
fixture('PARSER_NFC_CONTROL', JSON.stringify({ x: 'é' }), 'PASS', 'PARSE_PASS');
fixture('PARSER_BOOLEAN_CONTROL', 'true', 'PASS', 'PARSE_PASS');
fixture('PARSER_INVALID_SYNTAX', '{"x":}', 'REJECT', 'JSON_SYNTAX');
fixture('INVALID_MONTH_DAY_TIME', rawVector('INVALID_MONTH_DAY_TIME_VECTOR'), 'REJECT', 'INVALID_RFC3339_INSTANT', 'evaluate');
fixture('INVALID_NONLEAP_DAY', rawVector('INVALID_NONLEAP_DAY_VECTOR'), 'REJECT', 'INVALID_RFC3339_INSTANT', 'evaluate');
fixture('EMPTY_EXTENSION_KEY', rawVector('EMPTY_EXTENSION_KEY_VECTOR'), 'REJECT', 'EXTENSION_KEY', 'evaluate');
fixture('PARSER_NESTED_EMPTY_EXTENSION_KEY', rawVector('NESTED_EMPTY_EXTENSION_KEY'), 'REJECT', 'EXTENSION_KEY', 'evaluate');
fixture('PARSER_DIGEST_ONLY_FORM', rawVector('DIGEST_ONLY_FORM'), 'REJECT', 'UNSUPPORTED_PUBLIC_FORM', 'evaluate');
fixture('PARSER_EVIDENCE_REF_FORM', rawVector('EVIDENCE_REF_FORM'), 'REJECT', 'UNSUPPORTED_PUBLIC_FORM', 'evaluate');
fixture('PARSER_EFFECT_FIELD', rawVector('EFFECT_FIELD'), 'REJECT', 'SCHEMA_UNKNOWN_FIELD', 'evaluate');

const katCases = [
  {
    id: 'UTF8_ORDER_ASTRAL_BMP',
    value: { '😀': 'astral', '': 'bmp' },
    canonicalUtf8Hex: '7b22ee8080223a22626d70222c22f09f9880223a2261737472616c227d',
    digest: 'sha256:4874d36535a1b5dfdad7f2b3af83f87debd2f0795ae7d2d09447e17223c42dd0',
  },
  {
    id: 'SCALAR_ARRAY_CONTROL',
    value: { z: 0, a: [true, null, 'é'] },
    canonicalUtf8Hex: '7b2261223a5b747275652c6e756c6c2c22c3a9225d2c227a223a307d',
    digest: 'sha256:c3def2e9f3389c01aaa26f79114911addc9fbcfbb4130c412bd98ea9c38a33bb',
  },
  {
    id: 'NESTED_EXTENSION_ORDER',
    value: { tenantId: 'tenant-a', anchor: { id: 'a', generation: '7' } },
    canonicalUtf8Hex: '7b22616e63686f72223a7b2267656e65726174696f6e223a2237222c226964223a2261227d2c2274656e616e744964223a2274656e616e742d61227d',
    digest: 'sha256:07d218356e1b853f5b80e57c55bd5118ca182b2f36540d008d95ac8c578bd7e3',
  },
];

const corpus = { schemaVersion: 3, profile: PROFILE, canonicalization: C14N, publicForm: 'structured+digest', vectors };
const corpusText = `${JSON.stringify(corpus, null, 2)}\n`;
const parserText = `${parserFixtures.map((item) => JSON.stringify(item)).join('\n')}\n`;
const kats = { schemaVersion: 1, canonicalization: C14N, cases: katCases };
const katsText = `${JSON.stringify(kats, null, 2)}\n`;
fs.writeFileSync(path.join(here, 'corpus.json'), corpusText, 'utf8');
fs.writeFileSync(path.join(here, 'parser-hostile.jsonl'), parserText, 'utf8');
fs.writeFileSync(path.join(here, 'canonicalization-kats.json'), katsText, 'utf8');

const fileHash = (text) => `sha256:${crypto.createHash('sha256').update(text, 'utf8').digest('hex')}`;
const extensionA = vectors.find((item) => item.id === 'COMMITTED_EXTENSION_TENANT_A').record;
const extensionB = vectors.find((item) => item.id === 'COMMITTED_EXTENSION_TENANT_B').record;
const requiredRegressions = {
  INVALID_MONTH_DAY_TIME: 'REJECT_INVALID_RFC3339_INSTANT',
  INVALID_NONLEAP_DAY: 'REJECT_INVALID_RFC3339_INSTANT',
  LONE_SURROGATE: 'REJECT_LONE_SURROGATE',
  DUPLICATE_KEY: 'REJECT_DUPLICATE_JSON_KEY',
  OVER_DEPTH: 'REJECT_LIMIT_DEPTH',
  OVERLONG_INTEGER: 'REJECT_LIMIT_INTEGER_DIGITS',
  EMPTY_EXTENSION_KEY: 'REJECT_EXTENSION_KEY',
  DIGEST_ONLY_FORM: 'REJECT_UNSUPPORTED_PUBLIC_FORM',
  EVIDENCE_REF_FORM: 'REJECT_UNSUPPORTED_PUBLIC_FORM',
  EFFECT_FIELD: 'REJECT_SCHEMA_UNKNOWN_FIELD',
};
const manifest = {
  schemaVersion: 3,
  exactSet: true,
  publicForm: 'closed structured decision object + sha-256 commitment',
  vectorCount: vectors.length,
  kindCount: new Set(vectors.map((item) => item.kind)).size,
  parserFixtureCount: parserFixtures.length,
  canonicalizationKatCount: katCases.length,
  uniqueVectorIds: new Set(vectors.map((item) => item.id)).size === vectors.length,
  uniqueParserIds: new Set(parserFixtures.map((item) => item.id)).size === parserFixtures.length,
  corpusSha256: fileHash(corpusText),
  parserHostileSha256: fileHash(parserText),
  canonicalizationKatsSha256: fileHash(katsText),
  requiredRegressions,
  extensionCommitmentCollisionControl: {
    tenantA: extensionA.decisionEvidence.digest,
    tenantB: extensionB.decisionEvidence.digest,
    distinct: extensionA.decisionEvidence.digest !== extensionB.decisionEvidence.digest,
  },
  vectorIds: vectors.map((item) => item.id),
  parserIds: parserFixtures.map((item) => item.id),
};
fs.writeFileSync(path.join(here, 'EXACT_SET_MANIFEST.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({
  vectorCount: manifest.vectorCount,
  kindCount: manifest.kindCount,
  parserFixtureCount: manifest.parserFixtureCount,
  katCount: manifest.canonicalizationKatCount,
  extensionDigestsDistinct: manifest.extensionCommitmentCollisionControl.distinct,
}));

export { baseDecision, seal };
