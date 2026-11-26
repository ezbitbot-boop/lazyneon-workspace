import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
MAX_DESCRIPTION = 280
VISIBLE_SKILL_CAP = 21

# 라이선스 검증을 끝내지 못해 본 레포에서 제거된 제3자 트리 (NOTICE 참고)
REMOVED_TREES = [
    "mengto-skills",
    "design-systems",
    "vendor",
    "skills/slopslap",
    "skills/ui-studio",
    "skills/design-system",
    "skills/frontend-ui-ux",
]


def skill_md_files():
    return sorted(SKILLS.rglob("SKILL.md"))


def frontmatter_description(text):
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end < 0:
        return ""
    block = text[3:end]
    match = re.search(r"^description:\s*(.+)$", block, re.MULTILINE)
    if match is None:
        return ""
    return match.group(1).strip().strip("\"'")


class GeminiCatalogTests(unittest.TestCase):
    def test_visible_skill_count_is_bounded(self):
        # given skills/ is the Antigravity picker root
        files = skill_md_files()
        # then the catalog stays inside the Flash picker budget
        self.assertEqual(len(files), VISIBLE_SKILL_CAP)
        names = {path.parent.name for path in files}
        self.assertIn("lazyforensic", names)
        self.assertNotIn("infographic-syntax-creator", names)
        self.assertNotIn("manim-video", names)

    def test_removed_unlicensed_trees_stay_removed(self):
        # NOTICE 약속: 무라이선스 제3자 트리는 재유입되지 않는다
        for rel in REMOVED_TREES:
            self.assertFalse((ROOT / rel).exists(), rel)

    def test_no_dangling_references_to_removed_trees(self):
        # 남은 문서/스크립트가 제거된 트리를 '라이브 참조'하지 않는다
        offenders = []
        for base in ["GEMINI.md", "README.md", "docs", "skills", "scripts", "templates"]:
            p = Path(ROOT / base)
            files = [p] if p.is_file() else list(p.rglob("*")) if p.exists() else []
            for f in files:
                if not f.is_file() or f.suffix not in {".md", ".mjs", ".py", ".json"}:
                    continue
                text = f.read_text(encoding="utf-8")
                for token in ["mengto-skills/", "design-systems/", "vendor/antv", "skills/slopslap", "ui-studio/SKILL.md"]:
                    if token in text and "제거" not in text:
                        offenders.append(f"{f}: {token}")
        self.assertEqual(offenders, [])

    def test_descriptions_fit_flash_picker(self):
        # given every visible SKILL.md
        for path in skill_md_files():
            desc = frontmatter_description(path.read_text(encoding="utf-8"))
            # then description is short enough to stay in Gemini skill catalog
            self.assertTrue(desc, path)
            self.assertLessEqual(len(desc), MAX_DESCRIPTION, f"{path}: {len(desc)} {desc}")

    def test_visible_skill_descriptions_omit_foreign_apis(self):
        # given picker descriptions (always in Gemini context)
        for path in skill_md_files():
            desc = frontmatter_description(path.read_text(encoding="utf-8"))
            # then do not advertise foreign tools as capabilities
            self.assertNotIn("model_tier", desc, path)
            self.assertNotIn("CLAUDE_PLUGIN_ROOT", desc, path)
            self.assertNotIn("subagent_type", desc, path)

    def test_plugin_wires_hooks_and_gemini_default(self):
        data = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertNotIn("skills", data)
        self.assertTrue((ROOT / "skills").is_dir())
        self.assertEqual(data["hooks"], "./hooks.json")
        self.assertIn("Gemini 4 Neon", data["description"])
        hooks = json.loads((ROOT / "hooks.json").read_text(encoding="utf-8"))
        ss0 = hooks["hooks"]["SessionStart"][0]
        command = ss0["command"] if "command" in ss0 else ss0["hooks"][0]["command"]
        self.assertIn("session_start.mjs", command)

    def test_session_start_injects_gemini_md(self):
        # given SessionStart stdin
        payload = json.dumps({"hook_event_name": "SessionStart"})
        # when
        proc = subprocess.run(
            ["node", str(ROOT / "scripts" / "session_start.mjs")],
            input=payload,
            text=True,

            encoding="utf-8",
            capture_output=True,
            check=False,
            cwd=str(ROOT),
        )
        # then
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        ctx = out["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertEqual(list(out), ["injectSteps"])
        self.assertIn("모델 라우팅", ctx)
        self.assertIn("실패 폐쇄", ctx)
        self.assertIn("Antigravity", ctx)
        self.assertIn("증거 오디오", ctx)
        self.assertIn("외부 MCP·호스트 훅의 실연동 상태는 미확인", ctx)
        self.assertNotIn("LAW_OC=", ctx)
        # 모델명이 없으면 unknown — 추정하지 않는다
        self.assertIn("세션 모델: 미확인", ctx)
        self.assertIn("범위 잠금", ctx)
        # 정적 GEMINI.md 가 런타임 블록보다 앞에 온다(캐시 접두 안정성)
        self.assertLess(ctx.index("실패 폐쇄"), ctx.index("\n## 런타임\n"))

    def test_session_start_quotes_host_model_name(self):
        payload = json.dumps({"hook_event_name": "SessionStart", "modelName": "gemini-4-neon"})
        env = dict(os.environ)
        env.pop("ANTIGRAVITY_MODEL_NAME", None)
        proc = subprocess.run(
            ["node", str(ROOT / "scripts" / "session_start.mjs")],
            input=payload, text=True, encoding="utf-8", capture_output=True, check=False, cwd=str(ROOT), env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ctx = json.loads(proc.stdout)["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("세션 모델: gemini-4-neon", ctx)
        self.assertNotIn("Argon이라고 가정하지 말 것", ctx)

    def test_session_start_leaves_pins_to_core(self):
        # Contract (adv-r6 low-3): the LazyNeon core injects .lazyneon/pins.md at SessionStart; the workspace must not
        # inject it a second time, but it still runs cleanly when the file exists.
        with tempfile.TemporaryDirectory() as tmp:
            pins_dir = Path(tmp) / ".lazyneon"
            pins_dir.mkdir()
            (pins_dir / "pins.md").write_text("- 원본 SHA-256: " + "c" * 64 + " (audit.json)\n", encoding="utf-8")
            proc = subprocess.run(
                ["node", str(ROOT / "scripts" / "session_start.mjs")],
                input=json.dumps({"workspacePaths": [tmp]}), text=True, encoding="utf-8", capture_output=True, check=False, cwd=tmp,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            ctx = json.loads(proc.stdout)["injectSteps"][0]["systemMessage"]["systemMessage"]
            self.assertNotIn("c" * 64, ctx)
            self.assertIn("LazyNeon Workspace", ctx)

    def test_manim_reference_stays_unregistered(self):
        self.assertTrue((ROOT / "experimental" / "video-editor" / "manim-video" / "REFERENCE.md").is_file())
        self.assertFalse((ROOT / "experimental" / "video-editor" / "manim-video" / "SKILL.md").exists())



    def test_distribution_notice_matches_removed_trees(self):
        notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
        self.assertIn("korean-law-mcp/LICENSE", notice)
        self.assertIn("REMOVED", notice)
        self.assertIn("skills/slopslap/", notice)
        self.assertIn("mengto-skills/", notice)

        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("timeline_report.html", ignored)
        self.assertIn("korean-law-mcp/", ignored)
        self.assertIn(".env", ignored)

    def test_session_start_does_not_leak_law_key(self):
        env = os.environ.copy()
        env["LAW_OC"] = "secret-law-key-should-not-appear"
        payload = json.dumps({"hook_event_name": "SessionStart"})
        proc = subprocess.run(
            ["node", str(ROOT / "scripts" / "session_start.mjs")],
            input=payload,
            text=True,

            encoding="utf-8",
            capture_output=True,
            check=False,
            cwd=str(ROOT),
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("secret-law-key-should-not-appear", proc.stdout)
        self.assertNotIn("secret-law-key-should-not-appear", proc.stderr)
        ctx = json.loads(proc.stdout)["injectSteps"][0]["systemMessage"]["systemMessage"]
        self.assertIn("외부 MCP·호스트 훅의 실연동 상태는 미확인", ctx)


    def test_plugin_version_and_lane_copy(self):
        data = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(data["version"], "0.2.2")
        self.assertIn("independent", data["interface"]["longDescription"].lower())
        self.assertIn("not a forensic acquisition or court-admissibility suite", json.dumps(data, ensure_ascii=False).lower())
        self.assertTrue((ROOT / "docs" / "GAPS.md").is_file())

    def test_help_guide_is_routed_without_expanding_picker(self):
        guide = (ROOT / "docs" / "USER_GUIDE.md").read_text(encoding="utf-8")
        router = (SKILLS / "lazyforensic" / "SKILL.md").read_text(encoding="utf-8")
        gemini = (ROOT / "GEMINI.md").read_text(encoding="utf-8")
        self.assertIn("설명서", guide)
        self.assertIn("보고서 완성 워크플로", guide)
        self.assertIn("인라인 CSS", guide)
        self.assertIn("generate_timeline.py --input", guide)
        self.assertIn("docs/USER_GUIDE.md", router)
        self.assertIn("docs/USER_GUIDE.md", gemini)
        self.assertEqual(len(skill_md_files()), VISIBLE_SKILL_CAP)


if __name__ == "__main__":
    unittest.main()
