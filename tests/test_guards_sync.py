"""test_guards_sync.py — lazyothers 동기화 가드(markdown_structure_guard, stop_claim_guard, legal_factuality_guard) 검증."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = "node"


def run_node_script(script_name, args=(), stdin_payload=None, env=None, cwd=None):
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        [NODE, str(ROOT / "scripts" / script_name), *args],
        input=stdin_payload,
        text=True, encoding="utf-8", errors="replace",
        capture_output=True,
        env=e,
        cwd=str(cwd or ROOT),
    )












def _turn_transcript(tmp_path, outputs, calls=1):
    steps: list[dict[str, object]] = [{"type": "USER_INPUT", "content": "질문"}]
    for o in outputs:
        steps.append({"type": "PLANNER_RESPONSE", "content": "", "tool_calls": [{"name": "run_command", "args": {}}] * calls})
        steps.append({"type": "GENERIC", "content": o})
    tp = tmp_path / "transcript_full.jsonl"
    tp.write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in steps), encoding="utf-8")
    return str(tp)
















def _one_call_transcript(tmp_path, user, name, args, output):
    steps = [{"type": "USER_INPUT", "content": user},
             {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": name, "args": args}]},
             {"type": "GENERIC", "step_index": 2, "content": output}]
    tp = tmp_path / "transcript_full.jsonl"
    tp.write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in steps), encoding="utf-8")
    return str(tp)






_READ_OK = "Created At: 2026-11-02T07:00:00+09:00\nCompleted At: 2026-11-02T07:00:00+09:00\nShowing lines 1-2 of 2\n1: def f():\n2:     raise KeyError('key not found')"














_RF_FAIL = "Created At: x\nCompleted At: x\nEncountered error in step execution: file does not exist"
















def test_legal_factuality_guard_blocks_fake_statute(tmp_path):
    bad = tmp_path / "소장_초안.md"
    bad.write_text("# 소장\n원고는 민법 제1500조에 기하여 청구한다.", encoding="utf-8")
    payload = json.dumps({"tool_input": {"file_path": str(bad)}})
    proc = run_node_script("legal_factuality_guard.mjs", stdin_payload=payload)
    assert proc.returncode == 1
    assert "LEGAL FACTUALITY GUARD" in proc.stderr
    assert "민법" in proc.stderr


def test_legal_factuality_guard_passes_clean_legal_doc(tmp_path):
    clean = tmp_path / "소장_초안.md"
    clean.write_text("# 소장\n원고는 민법 제750조에 기하여 청구한다. 변호사 검토 필수.", encoding="utf-8")
    payload = json.dumps({"tool_input": {"file_path": str(clean)}})
    proc = run_node_script("legal_factuality_guard.mjs", stdin_payload=payload)
    assert proc.returncode == 0






def test_hallucination_guard_checks_any_text_file_next_to_evidence(tmp_path):
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "chat.txt").write_text("2026년 3월 12일 오후 2:09, 김철수 : 내일 꼭 줄게\n", encoding="utf-8")
    note = tmp_path / "김철수_정리.md"
    note.write_text('# 정리\n김철수는 "돈을 이미 보냈다"라고 했다.\n', encoding="utf-8")
    payload = json.dumps({"toolCall": {"name": "write_to_file", "args": {"TargetFile": str(note)}}})
    proc = run_node_script("hallucination_guard.mjs", stdin_payload=payload)
    assert proc.returncode == 1
    assert "원본에 없는 인용" in proc.stderr


def test_hallucination_guard_skips_files_inside_source_folder(tmp_path):
    src = tmp_path / "evidence"
    src.mkdir()
    raw = src / "unified_log.txt"
    raw.write_text('2026-10-31 09:00:00 | loginwindow "사건 보고서 작성용 원본"\n', encoding="utf-8")
    payload = json.dumps({"toolCall": {"name": "write_to_file", "args": {"TargetFile": str(raw), "CodeContent": "보고서"}}}, ensure_ascii=False)
    proc = run_node_script("hallucination_guard.mjs", stdin_payload=payload)
    assert proc.returncode == 0, proc.stderr
    assert "FAIL" not in proc.stderr


def test_hooks_json_contains_legal_guard():
    hooks_data = json.loads((ROOT / "hooks.json").read_text(encoding="utf-8"))
    ptu = hooks_data.get("hooks", {}).get("PostToolUse", [])
    commands = [h["command"] for entry in ptu for h in entry.get("hooks", [])]
    assert any("legal_factuality_guard.mjs" in c for c in commands)


def test_hooks_matchers_cover_write_file_and_shell():
    hooks_data = json.loads((ROOT / "hooks.json").read_text(encoding="utf-8"))
    ptu = hooks_data["hooks"]["PostToolUse"]
    write_m = ptu[0]["matcher"]
    shell_m = ptu[1]["matcher"] if len(ptu) > 1 else ptu[0]["matcher"]
    for token in ("write_file", "WriteToFile", "WriteFile", "MultiEdit", "SearchReplace"):
        assert __import__("re").search(write_m, token)
    for token in ("Bash", "bash", "Shell", "shell", "execute_command"):
        assert __import__("re").search(shell_m, token)
    post_cmds = [h["command"] for grp in ptu for h in grp["hooks"]]
    assert len(post_cmds) == len(set(post_cmds))


def test_mcp_config_covers_bundled_servers(tmp_path):
    config = json.loads((ROOT / "mcp_config.json").read_text(encoding="utf-8"))
    registered = set(config.get("mcpServers", {}))
    bundled = {entry.name for entry in (ROOT / "mcp").iterdir() if entry.is_dir()}
    for tool in bundled:
        assert tool in registered

