from pathlib import Path
import subprocess, sys, json
root=Path.cwd(); out=root/'docs/review/r7-test-results'
py=sys.executable
cases=[
 ('high-1', ['scripts/hallucination_guard.mjs','scripts/legal_factuality_guard.mjs'], ['tests/test_r7_workspace.py','tests/test_r3_workspace.py::test_guards_use_explicit_python_and_reject_clt_stub','-k','not setup'], 'always unavailable, exit 0'),
 ('high-2', ['scripts/pii_mask.py'], ['tests/test_r4_workspace.py::test_pii_variants_mask_and_vault','tests/test_r4_workspace.py::test_spaced_mixed_separators'], 'detected text + star'),
 ('medium-5', ['scripts/setup_forensic_env.py'], ['tests/test_r7_workspace.py::test_setup_entrypoint_records_install_and_failure'], 'pip execution under if False'),
 ('medium-6', ['scripts/audit_evidence_integrity.py'], ['tests/test_audit_evidence_integrity.py::test_multi_algorithm_audit','tests/test_audit_evidence_integrity.py::test_digest_content_and_changes'], 'constant MD5 and SHA1'),
 ('medium-7', ['scripts/hallucination_guard.mjs'], ['tests/test_r3_workspace.py::test_workspace_payload_pins_and_case_audit'], 'silent early exit for report'),
]
summary=[]
for label, files, tests, description in cases:
 originals={f:(root/f).read_bytes() for f in files}
 try:
  for f, data in originals.items():
   s=data.decode()
   if label=='high-1':
    s=s.replace('\tconst verifyScript =', "\tconsole.error('python 실행 불가'); console.log('{}'); process.exit(0);\n\tconst verifyScript =",1)
   elif label=='high-2':
    s=s.replace('def mask_text(text: str) -> str:', "def mask_text(text: str) -> str:\n    if detect_in_text(text): return text + '*'")
   elif label=='medium-5':
    start=s.index('    proc = subprocess.run('); end=s.index('\n    py = ',start)
    s=s[:start]+'    if False:\n'+''.join('    '+line+'\n' for line in s[start:end].splitlines())+s[end:]
   elif label=='medium-6':
    s=s.replace('def compute_hash(path, algorithm):', "def compute_hash(path, algorithm):\n    if algorithm == 'md5': return '1' * 32\n    if algorithm == 'sha1': return '1' * 40")
   else:
    s=s.replace('\tconst verifyScript =', "\tprocess.exit(0);\n\tconst verifyScript =",1)
   assert s != data.decode()
   (root/f).write_text(s)
  with (out/(label+'-mutation.txt')).open('w') as log:
   result=subprocess.run([py,'-m','pytest','-q',*tests],stdout=log,stderr=subprocess.STDOUT)
  assert result.returncode==1, (label, result.returncode)
 finally:
  for f, data in originals.items(): (root/f).write_bytes(data)
  assert all((root/f).read_bytes()==data for f,data in originals.items())
 with (out/(label+'-restored.txt')).open('w') as log:
  restored=subprocess.run([py,'-m','pytest','-q',*tests],stdout=log,stderr=subprocess.STDOUT)
 summary.append({'finding':label,'mutation':description,'mutant_exit':result.returncode,'restored_exit':restored.returncode,'files_restored_byte_for_byte':True})
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(label, 'mutation:', (out/(label+'-mutation.txt')).read_text().splitlines()[-1], 'restored:',(out/(label+'-restored.txt')).read_text().splitlines()[-1],flush=True)
 assert restored.returncode==0
