"""citation_grounding.py / citation_guard.mjs: values a report cites must come from the evidence (synthetic case only)."""
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import citation_grounding as cg  # noqa: E402

CLI = ROOT / "scripts" / "citation_grounding.py"
GUARD = ROOT / "scripts" / "citation_guard.mjs"

CHAT = (
    "2014-12-04 13:05:22 김민수: 내일 회의 자료 보내 주세요\n"
    "2014-12-04 13:07:01 이지은: 비\u200b밀번호는 따로 보낼게요\n"
    "송금 내역 3,500,000원, 이체 12건\n"
)
ACCESS_LOG = "2026-03-12T05:09:00Z login user=admin src=10.0.0.7\n"
MANIFEST = {"files": [{"path": "C:\\Cases\\demo\\memo.docx", "sha256": "9f2c1a7b3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8"}]}
DOCX_XML = (
    "<w:document><w:body>"
    "<w:p><w:r><w:t>계약 해지 </w:t></w:r><w:r><w:t>통보</w:t></w:r><w:r><w:t>서</w:t></w:r></w:p>"
    "<w:p><w:r><w:t>담당 박서연</w:t></w:r></w:p>"
    "</w:body></w:document>"
)

GROUNDED = """# 분석 보고서

- 작성일: 2026-11-27
- chat.txt SHA-256: {chat_sha} (직접 계산)
- chat.txt 해시 약칭 `{chat_sha_short}…`
- 매니페스트 해시 `9f2c1a7b…c6d7e8`
- 2014. 12. 4. 13:05에 김민수 씨가 "내일 회의 자료 보내 주세요"라고 말했다.
- 2014년 12월 4일 이지은 씨는 '비밀번호는 따로 보낼게요'라고 답했다.
- 관리자 접속은 2026-03-12 14:09 KST이다.
- memo.docx에 「계약 해지 통보서」가 있다. 「개인정보 보호법」 제17조 참조.
- 원본 경로 C:\\Cases\\demo\\memo.docx
- 송금 3,500,000원, 이체 12건, chat.txt 크기 {chat_size} bytes.

| 일시 | 담당자 |
| --- | --- |
| 2014-12-04 | 박서연 |
"""


def build_case(tmp_path: Path) -> tuple[Path, str]:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "chat.txt").write_bytes(CHAT.encode("utf-8"))
    (evidence / "access.log").write_text(ACCESS_LOG, encoding="utf-8")
    (evidence / "manifest.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    with zipfile.ZipFile(evidence / "memo.docx", "w") as zf:
        zf.writestr("word/document.xml", DOCX_XML)
    raw = (evidence / "chat.txt").read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    report = GROUNDED.format(chat_sha=sha, chat_sha_short=sha[:10], chat_size=len(raw))
    return evidence, report


def check(tmp_path: Path, report: str) -> dict:
    evidence = tmp_path / "evidence"
    path = tmp_path / "보고서.md"
    path.write_text(report, encoding="utf-8")
    return cg.check_report(path, [evidence])


def unsupported(result: dict) -> list[tuple[str, str]]:
    return [(i["kind"], i["value"]) for i in result["items"] if i["status"] == "unsupported"]


def test_grounded_report_has_no_unsupported_values(tmp_path):
    _, report = build_case(tmp_path)
    result = check(tmp_path, report)
    assert unsupported(result) == [], result["items"]
    kinds = {i["kind"] for i in result["items"]}
    assert {"hash", "date", "quote", "file", "number", "person"} <= kinds
    assert result["cited"] >= 15


@pytest.mark.parametrize("line,kind", [
    ("- 원본 해시 deadbeef00112233445566778899aabbccddeeff00112233445566778899aabb", "hash"),
    ("- 접속 일시 2015-01-09 09:30", "date"),
    ("- 최하준 과장이 반출을 승인했다.", "person"),
    ("- 송금은 모두 4,200,000원이다.", "number"),
    ("- 삭제된 메시지 7건이 복구되었다.", "number"),
    ('- 김민수는 "자료를 모두 지워라"라고 지시했다.', "quote"),
    ("- 반출 파일 secret_plan.xlsx", "file"),
    ("- FTK Imager로 이미징했다.", "tool"),
])
def test_planted_invented_value_is_reported(tmp_path, line, kind):
    _, report = build_case(tmp_path)
    result = check(tmp_path, report + "\n" + line + "\n")
    assert [k for k, _ in unsupported(result)] == [kind], result["items"]
    assert result["unsupported_by_kind"] == {kind: 1}


@pytest.mark.parametrize("line", [
    "- 대화 시작 2014. 12. 4.",
    "- 대화 시작 2014년 12월 4일 오후 1시 5분",
    "- 대화 시작 12/04/2014 13:05",
    "- 접속 2026-03-12 14:09:00 (KST, UTC+9)",
    "- 접속 시각(한국시간) 14:09",
    "- 송금 총액 350만 원",
    "- chat.txt 크기 0.2 KB",
])
def test_reformatted_and_converted_values_are_not_flagged(tmp_path, line):
    _, report = build_case(tmp_path)
    result = check(tmp_path, report + "\n" + line + "\n")
    bad = unsupported(result)
    assert bad == [], result["items"]


def test_kst_conversion_is_marked_computed(tmp_path):
    _, report = build_case(tmp_path)
    result = check(tmp_path, report)
    kst = [i for i in result["items"] if i["value"].startswith("2026-03-12 14:09")]
    assert kst and kst[0]["status"] == "computed" and "9 h" in kst[0]["via"]


def test_computed_hashes_and_sizes_are_marked_computed(tmp_path):
    _, report = build_case(tmp_path)
    result = check(tmp_path, report)
    by_kind = {(i["kind"], i["status"]) for i in result["items"]}
    assert ("hash", "computed") in by_kind
    sha_item = next(i for i in result["items"] if i["kind"] == "hash" and len(i["value"]) == 64)
    assert sha_item["via"].startswith("sha256(") and "chat.txt" in sha_item["via"]
    size_item = next(i for i in result["items"] if i["kind"] == "number" and "bytes" in i["value"])
    assert size_item["status"] == "computed"


def test_docx_member_text_and_zero_width_text_are_grounded(tmp_path):
    _, report = build_case(tmp_path)
    result = check(tmp_path, report)
    quotes = {i["value"]: i for i in result["items"] if i["kind"] == "quote"}
    assert quotes["계약 해지 통보서"]["status"] == "grounded"
    assert "memo.docx!word/document.xml" in quotes["계약 해지 통보서"]["via"]
    assert quotes["비밀번호는 따로 보낼게요"]["status"] == "grounded"
    # Zero-width characters in the report are ignored too.
    again = check(tmp_path, "- '비밀\u200c번호는 따로 보낼게요'\n")
    assert unsupported(again) == []


def test_labelled_computed_and_hedged_values_are_not_unsupported(tmp_path):
    _, report = build_case(tmp_path)
    extra = ("- 두 송금의 합산 금액 7,000,000원(계산값)\n"
             "- 접속 일시 2015-01-09 09:30 [미확인]\n"
             "- \"보이스피싱\"이라는 단어는 자료에 없음\n"
             "- 합산 해시 deadbeef00112233445566778899aabbccddeeff00112233445566778899aabb (변조 흔적 없음)\n")
    result = check(tmp_path, report + extra)
    status = {i["value"]: i["status"] for i in result["items"]}
    assert status["7,000,000원"] == "labelled"
    assert status["2015-01-09 09:30"] == "hedged" and status["보이스피싱"] == "hedged"
    # A hash can always be recomputed, so labelling it "computed" does not excuse it.
    assert unsupported(result) == [("hash", "deadbeef00112233445566778899aabbccddeeff00112233445566778899aabb")]


def test_quote_gap_and_legal_titles_are_not_quotes(tmp_path):
    _, report = build_case(tmp_path)
    extra = ("- 키워드 '회의', '자료'를 검색했다.\n"
             "- 문구 ', 그리고 다음'은 인용이 아니다.\n"
             "- 「전자금융거래법」과 (이하 \"이 사건 계약\"이라 한다)\n")
    result = check(tmp_path, report + extra)
    assert unsupported(result) == [], result["items"]


def test_windows_paths_in_reports_and_evidence(tmp_path):
    _, report = build_case(tmp_path)
    extra = ("- 원본 위치 C:\\Cases\\demo\\memo.docx에서 확인\n"
             "- 반출 경로 D:\\Exports\\payroll_2026.xlsx\n")
    result = check(tmp_path, report + extra)
    files = {i["value"]: i["status"] for i in result["items"] if i["kind"] == "file"}
    assert files["C:\\Cases\\demo\\memo.docx"] == "grounded"
    assert files["D:\\Exports\\payroll_2026.xlsx"] == "unsupported"


def test_cli_prints_table_and_json(tmp_path):
    _, report = build_case(tmp_path)
    path = tmp_path / "보고서.md"
    path.write_text(report + "- 최하준 과장\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(CLI), str(path), "--evidence", str(tmp_path / "evidence")],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    table, _, payload = proc.stdout.partition("\n\n{")
    assert table.splitlines()[0].split()[:3] == ["line", "kind", "status"]
    assert "unsupported 1" in table and "최하준" in table
    assert json.loads("{" + payload)["unsupported"] == 1
    strict = subprocess.run([sys.executable, str(CLI), str(path), "--evidence", str(tmp_path / "evidence"), "--json", "--strict"],
                            capture_output=True, text=True, encoding="utf-8")
    assert strict.returncode == 1 and json.loads(strict.stdout)["unsupported_by_kind"] == {"person": 1}
    missing = subprocess.run([sys.executable, str(CLI), str(path), "--evidence", str(tmp_path / "nope")], capture_output=True, text=True)
    assert missing.returncode == 2


# --- hook ---------------------------------------------------------------------------------------

@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))  # os.homedir() on Windows
    monkeypatch.setenv("LAZYNEON_WS_PYTHON", sys.executable)
    monkeypatch.setenv("LAZYNEON_OFFLINE", "1")
    monkeypatch.delenv("LAZYNEON_WS_CITATION_STRICT", raising=False)
    (tmp_path / "home").mkdir()
    return tmp_path


def hook(ctx: Path, report: str, name: str = "보고서.md", env: dict | None = None, script: Path = GUARD, *args: str):
    (ctx / name).write_text(report, encoding="utf-8")
    payload = {"workspacePaths": [str(ctx)], "conversationId": "cite", "toolCall": {"name": "write_file", "args": {"TargetFile": str(ctx / name)}}}
    return subprocess.run(["node", str(script), *args], input=json.dumps(payload), capture_output=True, text=True,
                          encoding="utf-8", env={**os.environ, **(env or {})}, timeout=60)


def test_hook_passes_grounded_report(ctx):
    _, report = build_case(ctx)
    r = hook(ctx, report)
    assert r.returncode == 0 and json.loads(r.stdout) == {"status": "PASS"}, r.stderr


def test_hook_default_mode_warns_and_never_blocks(ctx):
    _, report = build_case(ctx)
    r = hook(ctx, report + "- 최하준 과장이 승인했다.\n- 접속 2015-01-09 09:30\n")
    assert r.returncode == 0 and json.loads(r.stdout) == {"status": "WARN"}
    assert "[CITATION GUARD] WARN" in r.stderr and "person: 최하준" in r.stderr and "date: 2015-01-09 09:30" in r.stderr


def test_hook_strict_mode_blocks_unsupported_citations(ctx):
    _, report = build_case(ctx)
    strict = {"LAZYNEON_WS_CITATION_STRICT": "1"}
    r = hook(ctx, report + "- 최하준 과장이 승인했다.\n", env=strict)
    verdict = json.loads(r.stdout)
    assert r.returncode == 1 and verdict["status"] == "FAIL" and verdict["decision"] == "block"
    ok = hook(ctx, report, env=strict)
    assert ok.returncode == 0 and json.loads(ok.stdout) == {"status": "PASS"}


def test_hook_without_python_is_unchecked_and_blocks_only_in_strict(ctx):
    _, report = build_case(ctx)
    missing = {"LAZYNEON_WS_PYTHON": str(ctx / "no-python")}
    r = hook(ctx, report, env=missing)
    assert r.returncode == 0 and json.loads(r.stdout)["status"] == "NOT_CHECKED"
    r = hook(ctx, report, env={**missing, "LAZYNEON_WS_CITATION_STRICT": "1"})
    assert r.returncode == 1 and json.loads(r.stdout)["decision"] == "block"


def test_hook_skips_reports_without_evidence_and_non_reports(ctx):
    r = hook(ctx, "# 보고서\n- 최하준 과장\n")
    assert r.returncode == 0 and json.loads(r.stdout) == {"status": "NOT_APPLICABLE"}
    build_case(ctx)
    r = hook(ctx, "x = 1\n", name="script.py")
    assert json.loads(r.stdout) == {"status": "NOT_APPLICABLE"}


def test_relay_records_warn_by_default_and_fail_in_strict(ctx):
    _, report = build_case(ctx)
    relay = ROOT / "scripts" / "domain_feedback.mjs"
    feedback = ctx / "home" / ".lazyneon-workspace" / "feedback"

    def rows():
        out = [json.loads(line) for p in feedback.glob("*.jsonl") for line in p.read_text(encoding="utf-8").splitlines()]
        for p in feedback.glob("*.jsonl"):
            p.unlink()
        return [(r["guard"], r["kind"]) for r in out]

    r = hook(ctx, report + "- 최하준 과장\n", "보고서.md", None, relay, "batch", "citation_guard.mjs")
    assert r.returncode == 0 and r.stdout.strip() == "{}"
    assert rows() == [("citation_guard.mjs", "warn")]
    hook(ctx, report + "- 최하준 과장\n", "보고서.md", {"LAZYNEON_WS_CITATION_STRICT": "1"}, relay, "batch", "citation_guard.mjs")
    assert rows() == [("citation_guard.mjs", "fail")]
