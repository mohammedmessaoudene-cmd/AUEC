# SPDX-License-Identifier: Apache-2.0
"""Defensive regression of our own validator, no provider or remote calls."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

TARGET=Path(__file__).resolve().parents[1]/'sep3004_cleanroom.py'
spec=importlib.util.spec_from_file_location('auec_validator_under_test', TARGET)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def body():
    return {'event_id':'77777777-7777-7777-7777-777777777777',
            'occurred_at':'2026-09-04T12:00:00.000Z','principal_id':'did:example:alice',
            'event_type':'tool_call','tool_name':'files.read','outcome':'allowed',
            'extensions':{'caller-governance':{'purpose_declared':'local defensive test'}},
            'previous_hash':None}

def sealed(b):
    return {**copy.deepcopy(b),'event_hash':m.compute_event_hash(b)}

class Boundaries(unittest.TestCase):
    def test_valid_caller(self): self.assertEqual([],m.verify_record(sealed(body())))
    def test_valid_runtime(self):
        b=body(); b['extensions']={'runtime-security':{'drift_status':'none','severity':'info',
            'quarantine_decision':'release','policy_id':'example:policy'}}
        self.assertEqual([],m.verify_record(sealed(b)))
    def test_null_caller_rejected(self):
        b=body(); b['extensions']={'caller-governance':None}
        self.assertIn('caller-governance must be an object',m.verify_record(sealed(b)))
    def test_null_runtime_rejected(self):
        b=body(); b['extensions']={'runtime-security':None}
        self.assertIn('runtime-security must be an object',m.verify_record(sealed(b)))
    def test_null_alongside_valid_rejected(self):
        b=body(); b['extensions']['runtime-security']=None
        self.assertIn('runtime-security must be an object',m.verify_record(sealed(b)))
    def test_missing_required(self):
        b=body(); b['extensions']={'caller-governance':{}}
        self.assertIn('caller-governance purpose_declared is required',m.verify_record(sealed(b)))
    def test_extension_container_types(self):
        for name in ('caller-governance','runtime-security'):
            for value in ([],True,'text',1):
                with self.subTest(name=name,value=value):
                    self.assertIn(name+' must be an object',m.validate_extensions({'extensions':{name:value}}))
    def test_outcome_types(self):
        for value in ([],{},True,None,1):
            with self.subTest(value=value):
                b=sealed(body()); b['outcome']=value
                self.assertIn('outcome is outside the closed disposition vocabulary',m.validate_skeleton(b))
    def test_runtime_enum_types(self):
        for name in ('drift_status','severity','quarantine_decision'):
            for value in ([],{},True,None,1):
                with self.subTest(name=name,value=value):
                    fields={'drift_status':'none','severity':'info','quarantine_decision':'release','policy_id':'p'}
                    fields[name]=value
                    self.assertIn('runtime-security '+name+' is invalid',m.validate_extensions({'extensions':{'runtime-security':fields}}))
    def test_wrong_hash_rejected(self):
        b=sealed(body()); b['event_hash']='0'*64
        self.assertIn('event_hash does not match the protected body',m.verify_record(b))
    def test_normalization_profile(self):
        a=body(); a['extensions']['caller-governance']['purpose_declared']=' é '
        b=body(); b['extensions']['caller-governance']['purpose_declared']='e\u0301'
        self.assertEqual(m.compute_event_hash(a),m.compute_event_hash(b))
    def test_specific_string_errors(self):
        for value, diagnostic in (('\ud800','unpaired surrogate'),('a\u0085b','control character'),('😀'*4097,'8192 UTF-16')):
            with self.subTest(diagnostic=diagnostic):
                b=body(); b['extensions']['caller-governance']['purpose_declared']=value
                with self.assertRaisesRegex(m.Sep3004Error,diagnostic): m.compute_event_hash(b)

if __name__=='__main__': unittest.main(verbosity=2)
