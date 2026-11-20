"""Real-engine grounding and repeated-call state regressions."""
import pytest
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_custom_statute_load_diagnostics_do_not_contaminate_verification(tmp_path, monkeypatch):
    from scripts import verify_legal_factuality as legal
    # Restore diagnostics even on the pre-fix failure.
    monkeypatch.setattr(legal, '_LOAD_WARNINGS', list(legal._LOAD_WARNINGS))
    before = legal.verify_legal_text('민법 제750조에 따른 청구.')
    legal._load_statute_bounds(custom_path=tmp_path / 'missing.json')
    assert any('파일 부재' in warning for warning in legal._LOAD_WARNINGS)
    assert legal.verify_legal_text('민법 제750조에 따른 청구.') == before


@pytest.mark.parametrize('script,source_flag', [
    ('verify_report.py', '--evidence'),
    ('verify_legal_factuality.py', '--source'),
])
def test_real_engine_absence_blocks_identical_grounded_text(tmp_path, script, source_flag):
    source = tmp_path / 'source.txt'
    source.write_text('원고와 피고는 계약을 체결하였다.', encoding='utf-8')
    result = subprocess.run([
        sys.executable, '-S', str(ROOT / 'tests/morph_without_engine.py'),
        str(ROOT / 'scripts' / script), str(source), source_flag, str(source),
        '--morph-grounding', '--json',
    ], capture_output=True, text=True)
    assert result.returncode == 1, result.stderr
    data = json.loads(result.stdout)
    assert data['verdict'] == 'FAIL'
    assert 'MORPH_UNAVAILABLE' in data['status_codes']
    assert any('[미확인]' in error for error in data['errors'])


def test_compensation_noun_forms_share_grounding_without_exempting_claims():
    pytest.importorskip('kiwipiepy', reason='Checks real Kiwi compensation noun segmentation')
    from scripts.korean_morph_grounding import calculate_grounding_overlap
    source = '원고와 피고는 민법 제750조에 의하여 손해배상을 청구하였다.'
    target = '【주 문】\n피고는 원고에게 손해배상금을 지급하라.\n【이 유】\n민법 제750조에 근거한다.'
    result = calculate_grounding_overlap(source, target, threshold=0.65, filter_procedural=True)
    assert result['is_grounded'], result
    bad = calculate_grounding_overlap(source, target + '\n횡령 사기 협박 갈취.', threshold=0.65, filter_procedural=True)
    assert not bad['is_grounded']
    assert {'횡령', '사기', '협박', '갈취'} <= set(bad['unsupported_terms'])


def test_legal_grounding_repeated_calls_do_not_leak_results():
    pytest.importorskip('kiwipiepy', reason='Checks real engine singleton across alternating verification calls')
    from scripts.verify_legal_factuality import verify_legal_text
    source = '원고와 피고는 계약을 체결하였다.'
    good = verify_legal_text(source, source_text=source, morph_grounding=True)
    assert good['verdict'] in ('PASS', 'WARN')
    bad = verify_legal_text('횡령 사기 협박 갈취.', source_text=source, morph_grounding=True)
    assert bad['verdict'] == 'FAIL'
    missing = verify_legal_text(source, morph_grounding=True)
    assert missing['verdict'] == 'FAIL'
    assert verify_legal_text(source, source_text=source, morph_grounding=True) == good
