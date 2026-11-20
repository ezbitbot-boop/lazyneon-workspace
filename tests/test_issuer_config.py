"""Issuer exemptions must be explicit, local and empty by default."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import mask_korean_pii as mk
import pii_patterns as patterns


@pytest.mark.parametrize('vault', [False, True])
@pytest.mark.parametrize('phone', ['02-0000-0000', '02 0000 0000', '0200000000'])
def test_issuer_phone_requires_config(tmp_path, vault, phone):
    config = tmp_path / 'issuer.json'
    mask = mk.PiiVault().tokenize_text if vault else mk.mask_text
    types = {'phone', 'landline_nodelim'}
    masked, stats = mask(phone, types, issuer_config=config)
    assert masked != phone and stats['phone'] == 1
    config.write_text(json.dumps({'organization': '가상법무법인', 'phone': '02-0000-0000'}))
    masked, stats = mask(phone, types, issuer_config=config)
    assert masked == phone and stats['phone'] == 0
    config.unlink()
    masked, stats = mask(phone, types, issuer_config=config)
    assert masked != phone and stats['phone'] == 1


@pytest.mark.parametrize('content', ['{}', '{"phone": ""}', '[]', '{"phone": 123}', '{bad'])
def test_empty_or_invalid_issuer_never_exempts(tmp_path, content):
    config = tmp_path / 'issuer.json'
    config.write_text(content)
    masked, stats = mk.mask_text('02-0000-0000', {'phone'}, issuer_config=config)
    assert masked == '02-0000-****' and stats['phone'] == 1


def test_issuer_example_and_default_path():
    assert patterns.ISSUER_CONFIG_PATH == ROOT / 'config/issuer.json'
    assert json.loads((ROOT / 'config/issuer.example.json').read_text()) == dict.fromkeys(
        ['organization', 'address', 'phone', 'account', 'author', 'seal_image'], '')
    assert '/config/issuer.json' in (ROOT / '.gitignore').read_text().splitlines()


def test_legal_recipient_fixture_is_fictional():
    source = (ROOT / 'tests/test_generate_legal_draft.py').read_text()
    assert '"recipient": "가상법무법인"' in source
    assert 'assert "수    신: 가상법무법인" in md' in source


def test_video_auditor_description_is_organization_neutral():
    source = (ROOT / 'skills/forensic-video/scripts/forensic_video_audit.py').read_text()
    assert 'Forensic Video Metadata & Frame Integrity Auditor.' in source
