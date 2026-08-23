import fs from 'node:fs';
import path from 'node:path';

const [, , root, output] = process.argv;
const runtimeFiles = [
  'oracles/node/oracle.mjs',
  'oracles/python/oracle.py',
  'oracles/verify-parity-and-collision.mjs',
  'oracles/sep3004-current-head-projection.mjs',
  'oracles/verify-independence.mjs',
  'vectors/generate-corpus.mjs',
  'demo/run-review.ps1',
  'build/build_reviewer.py',
];
const unrelatedProfileToken = ['cha', '2a'].join('');
const tokenPrefixA = ['gh', 'p_'].join('');
const tokenPrefixB = ['github', '_pat_'].join('');
const findings = [];
for (const relative of runtimeFiles) {
  const text = fs.readFileSync(path.join(root, relative), 'utf8');
  const lower = text.toLowerCase();
  findings.push({
    file: relative,
    externalProfileDependencyReference: lower.includes(unrelatedProfileToken),
    outboundNetworkPrimitive: /(?:from|require\s*\()\s*['"]node:https?|\brequests\.(?:get|post|put|patch|delete)\s*\(|\burllib\.request\b|\bfetch\s*\(|\binvoke-webrequest\b|\binvoke-restmethod\b|\bcurl(?:\.exe)?\b/.test(lower),
    remoteWriteCommand: /\b(?:git\s+push|gh\s+(?:pr|issue|api)|npm\s+publish|twine\s+upload)\b/.test(lower),
    secretLikeToken: lower.includes(tokenPrefixA) || lower.includes(tokenPrefixB)
      || /\bbearer\s+[a-z0-9._-]{12,}/i.test(text),
  });
}
const report = {
  schemaVersion: 3,
  runtimeInputs: [
    'vectors/corpus.json',
    'vectors/parser-hostile.jsonl',
    'vectors/canonicalization-kats.json',
    'byte-pinned current-head SEP-3004 source',
  ],
  sourceChecks: findings,
  externalProfileDependencyCount: findings.filter((item) => item.externalProfileDependencyReference).length,
  outboundNetworkPrimitiveCount: findings.filter((item) => item.outboundNetworkPrimitive).length,
  remoteWriteCommandCount: findings.filter((item) => item.remoteWriteCommand).length,
  secretLikeTokenCount: findings.filter((item) => item.secretLikeToken).length,
  remoteWrites: 0,
};
report.pass = report.externalProfileDependencyCount === 0
  && report.outboundNetworkPrimitiveCount === 0
  && report.remoteWriteCommandCount === 0
  && report.secretLikeTokenCount === 0;
fs.writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({
  pass: report.pass,
  externalProfileDependencyCount: report.externalProfileDependencyCount,
  outboundNetworkPrimitiveCount: report.outboundNetworkPrimitiveCount,
  remoteWriteCommandCount: report.remoteWriteCommandCount,
  secretLikeTokenCount: report.secretLikeTokenCount,
}));
if (!report.pass) process.exitCode = 1;
