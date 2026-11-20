"""Explicit non-report artifact envelope; body changes invalidate its classification."""
try:
    from scripts.workspace_provenance import workspace_provenance, provenance_text
except ModuleNotFoundError:
    from workspace_provenance import workspace_provenance, provenance_text
import hashlib

def mark_artifact(body, generator):
    body = body + '\n\n' + provenance_text() + '\n'
    digest=hashlib.sha256(body.encode('utf-8')).hexdigest()
    return f'<!-- lazyneon-artifact:v1 kind=non-report generator={generator} sha256={digest} -->\n'+body
