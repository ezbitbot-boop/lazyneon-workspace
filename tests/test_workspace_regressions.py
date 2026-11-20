"""Independent offline regressions for the curated workspace contract."""
import pytest
import shutil
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


def test_grounding_metadata_does_not_exempt_document_prose():
    pytest.importorskip('kiwipiepy', reason='Grounded metadata success requires the real morphology engine')
    from verify_legal_factuality import verify_legal_text
    source = '2024년 1월 16일 금 10,000,000원을 입금하였다. 원고는 피고에게 대여하였습니다.'
    body = '# 소장\n## 청구원인\n<evidence>' + source + '</evidence>\n'
    good = verify_legal_text(body + '*입증방법: 갑 제1호증, 차용증*\n', source_text=source, high_fidelity=True)
    bad = verify_legal_text(body + '차용증에는 가압류 담보설정 연대보증인의 채무승계 특약사항이 기재되어 있다.\n', source_text=source, high_fidelity=True)
    assert good['verdict'] != 'FAIL'
    assert bad['verdict'] == 'FAIL'


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required to generate and extract a real video frame; consent is tested independently")
def test_local_video_extracts_real_frame_without_upload(tmp_path):
    video = tmp_path / 'synthetic.mp4'
    made = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x120:r=5', '-t', '1', '-c:v', 'mpeg4', str(video)], capture_output=True, text=True)
    assert made.returncode == 0, made.stderr
    proc = subprocess.run([sys.executable, str(ROOT / 'skills/forensic-video/scripts/watch.py'), str(video), '--detail', 'balanced', '--max-frames', '1', '--out-dir', str(tmp_path / 'out'), '--json'], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result['transcript'] == []
    assert 'Uploading' not in proc.stderr
    assert len(result['frames']) == 1
    assert Path(result['frames'][0]['path']).is_file()
    assert result['metadata']['width'] == 160


def test_modality_restoration_and_gate_reject_new_number(tmp_path):
    from restore_modality import restore
    before = '이 분석 결과는 추가 확인이 필요할 것으로 판단된다.'
    after = '이 분석 결과는 추가 확인이 필요하다.'
    restored, changes, skipped = restore(before, after)
    assert changes and not skipped
    assert '판단된다' in restored
    src = tmp_path / 'before.txt'; target = tmp_path / 'after.txt'
    src.write_text('조사 결과 파일은 12개이며 손상은 발견되지 않았다.\n', encoding='utf8')
    target.write_text('조사 결과 파일은 99개이며 손상은 발견되지 않았다.\n', encoding='utf8')
    proc = subprocess.run([sys.executable, str(ROOT / 'scripts/verify_gates.py'), '--before', str(src), '--after', str(target), '--json'],capture_output=True,text=True)
    assert proc.returncode in (1, 2), proc.stdout + proc.stderr
