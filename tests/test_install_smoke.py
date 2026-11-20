"""플러그인 설치 스모크 — install.sh / install.ps1 의 2대 통합 플러그인 목록 정합성."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

















def test_extracted_skills_not_stale_in_lazyothers():
    """분리된 스킬이 lazyneon-workspace에 중복으로 남아 있지 않아야 한다."""
    skills_dir = REPO_ROOT / "skills"
    assert not (skills_dir / "diagram-design").exists(), (
        "diagram-design must live only in the core plugin repo"
    )


def test_local_skills_have_skill_md():
    """남은 스킬 디렉터리는 SKILL.md를 갖춰야 한다(플러그인 매니페스트 무결성)."""
    for skill in sorted((REPO_ROOT / "skills").iterdir()):
        if skill.is_dir() and not skill.name.startswith("."):
            assert (skill / "SKILL.md").is_file(), f"{skill.name} lacks SKILL.md"
