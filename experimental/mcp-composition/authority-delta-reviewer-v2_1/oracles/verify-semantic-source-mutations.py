# SPDX-License-Identifier: Apache-2.0
"""Local rule-by-rule mutation tests for AUEC, with exact diagnostics.

Source mutations exist only in memory. No remote operations or source writes.
Node/Python share test cases here; this is not organizational independence.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PY=ROOT/'oracles/python/oracle.py'
JS=ROOT/'oracles/node/oracle.mjs'
EXPECTED={2:'EFFECTIVE_NOT_EXACT_INTERSECTION',3:'DENIED_SET_MISMATCH',4:'REDUCED_SET_MISMATCH',
 5:'BUDGET_INCREASE',6:'BUDGET_DENIED_MISMATCH',7:'DECLARATION_UNAUTHENTICATED',8:'SERVER_NOT_ADMITTED',
 9:'FUTURE_CAPTURE_REJECTED',10:'MATERIAL_CHANGE_REQUIRES_REGATE',11:'REASON_CODES_INVALID',14:'IDEMPOTENCY_DIGEST_TYPE'}

class DisableRule(ast.NodeTransformer):
    def __init__(self,reason): self.reason=reason;self.hits=0
    def visit_If(self,node):
        if len(node.body)==1 and isinstance(node.body[0],ast.Return):
            literals=[n.value for n in ast.walk(node.body[0]) if isinstance(n,ast.Constant)]
            if self.reason in literals:
                node.test=ast.Constant(False);self.hits+=1
                return node
        return self.generic_visit(node)

def run():
    if not __debug__:
        raise RuntimeError('This assertion-based test gate requires Python without -O or PYTHONOPTIMIZE')
    source=PY.read_text(encoding='utf-8');js=JS.read_text(encoding='utf-8')
    before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (PY,JS)]
    spec=importlib.util.spec_from_file_location('auec_rule_reference',PY)
    reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)
    base=next(v['record'] for v in json.loads((ROOT/'vectors/corpus.json').read_text(encoding='utf-8'))['vectors'] if v['id']=='BASE_STRUCTURED')
    assert reference.evaluate(base)['verdict']=='PASS'
    benign=copy.deepcopy(base);benign['decision']['extensions']['localTestMarker']='benign'
    benign['decisionEvidence']['digest']=reference.commitment_for_decision(benign['decision'])
    assert reference.evaluate(benign)['verdict']=='PASS'
    rows=[];node_cases=[]
    for index,reason in EXPECTED.items():
        case=copy.deepcopy(base);reference.mutate_by_operator(case,index,0)
        if index==5:
            # Isolate the ceiling rule while keeping the independent reduced
            # arithmetic valid; otherwise that second rule masks this mutant.
            effective=int(base['decision']['budgets']['effective'])+1
            requested=int(base['decision']['budgets']['requested'])
            assert effective<=requested
            case['decision']['budgets']['effective']=str(effective)
            case['decision']['budgets']['reduced']=str(requested-effective)
        # Keep this independent of whether the data-mutation helper reseals.
        case['decisionEvidence']['digest']=reference.commitment_for_decision(case['decision'])
        expected={'verdict':'REJECT','reason':reason}
        assert reference.evaluate(case)==expected
        transform=DisableRule(reason);tree=transform.visit(ast.parse(source));ast.fix_missing_locations(tree)
        assert transform.hits==1,(reason,transform.hits)
        namespace={'__name__':'auec_deliberately_broken_rule','__file__':str(PY)}
        exec(compile(tree,str(PY),'exec'),namespace)
        assert namespace['evaluate'](case)['verdict']=='PASS',(reason,namespace['evaluate'](case))
        assert namespace['evaluate'](base)['verdict']=='PASS'
        assert reference.evaluate(case)==expected
        # One conditional return line per rule in the independently written Node oracle.
        lines=[line for line in js.splitlines() if line.lstrip().startswith('if (') and f"'{reason}'" in line and ') return ' in line]
        assert len(lines)==1,(reason,len(lines))
        line=lines[0];replacement=line.replace('if (','if (false && (',1).replace(') return ', ')) return ',1)
        node_cases.append({'reason':reason,'record':case,'oldLine':line,'newLine':replacement})
        rows.append({'reason':reason,'python':{'reference':'REJECT_ASSIGNED_REASON','mutant':'PASS',
          'restored':'REJECT_ASSIGNED_REASON','changed_conditions':1,
          'mutant_source_sha256':hashlib.sha256(ast.unparse(tree).encode()).hexdigest()}})
    script="""
import fs from 'node:fs';
import crypto from 'node:crypto';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const load=async s=>await import('data:text/javascript;base64,'+Buffer.from(s).toString('base64'));
const ref=await load(input.source);
const assert=(p,m)=>{if(!p)throw Error(m)};
assert(ref.evaluate(input.base).verdict==='PASS','base');
assert(ref.evaluate(input.benign).verdict==='PASS','benign');
const result=[];
for(const c of input.cases){
  assert(input.source.split(c.oldLine).length===2,'unique line');
  const before=ref.evaluate(c.record);
  assert(before.verdict==='REJECT'&&before.reason===c.reason,'assigned diagnostic');
  const mutantSource=input.source.replace(c.oldLine,c.newLine);
  const broken=await load(mutantSource);
  assert(broken.evaluate(c.record).verdict==='PASS','rule ablation');
  assert(broken.evaluate(input.base).verdict==='PASS','positive control');
  const restored=await load(input.source);
  assert(restored.evaluate(c.record).reason===c.reason,'restoration');
  result.push({reason:c.reason,reference:'REJECT_ASSIGNED_REASON',mutant:'PASS',restored:'REJECT_ASSIGNED_REASON',
    changed_conditions:1,mutant_source_sha256:crypto.createHash('sha256').update(mutantSource).digest('hex')});
}
console.log(JSON.stringify(result));
"""
    proc=subprocess.run(['node','--input-type=module','-e',script],input=json.dumps({'source':js,'base':base,'benign':benign,'cases':node_cases}),capture_output=True,text=True,encoding='utf-8',timeout=60)
    if proc.returncode:raise RuntimeError(proc.stderr)
    node=json.loads(proc.stdout)
    for row,n in zip(rows,node,strict=True):
        assert row['reason']==n['reason'];row['node']=n
    after=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (PY,JS)]
    assert before==after
    return {'pass':True,'semanticRules':len(rows),'sourceMutants':2*len(rows),'positiveControlsPerOracle':2,
      'sourceHashesBefore':before,'sourceHashesAfter':after,'sameSourceBytes':True,'rules':rows,
      'scope':'11 selected semantic rules per implementation, not all possible source mutations; shared fixture family',
      'remoteWrites':0}

if __name__=='__main__':
    report=run()
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'pass':report['pass'],'semanticRules':report['semanticRules'],'sourceMutants':report['sourceMutants']}))
