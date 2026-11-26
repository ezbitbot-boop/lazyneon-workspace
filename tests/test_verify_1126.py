"""Regressions for the 2026-11-26 verification defects (offline, temp dirs only)."""
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
import pytest
from test_r6_workspace import ctx, run, event, ROOT


def guard(ctx, command):
    return run('evidence_guard.mjs', event(ctx, {'command': command}, 'exec_command'), 'pre-tool-use')


@pytest.mark.parametrize('command', [
    'rm ev*/chat.txt',
    'rm -f e?idence/chat.txt',
    'node -e "require(\'fs\').unlinkSync(\'evid\'+\'ence/chat.txt\')"',
    'python3 -c "import os; os.remove(\'evid\'+\'ence/chat.txt\')"',
    'ffmpeg -i in.mp4 -y evidence/a.mp4 out.wav',
    'ffmpeg -loglevel error -i in.mp4 -y evidence/a.mp4 out.wav',
])
def test_guard_denies_glob_inline_and_ffmpeg_middle_output(ctx, command):
    (ctx/'evidence').mkdir(); (ctx/'evidence'/'chat.txt').write_text('x'); (ctx/'evidence'/'a.mp4').write_text('x')
    r = guard(ctx, command)
    assert r.returncode == 1, (command, r.stdout, r.stderr)
    assert '"deny"' in r.stdout


@pytest.mark.parametrize('command', [
    'rm *.log', 'rm -rf reports/*', 'python3 -c "import json; print(1)"',
    'ffmpeg -i evidence/a.mp4 -t 0.5 clip.wav', 'cat evidence/chat.txt',
])
def test_guard_still_allows_unrelated_globs_and_reads(ctx, command):
    (ctx/'evidence').mkdir(); (ctx/'evidence'/'chat.txt').write_text('x'); (ctx/'evidence'/'a.mp4').write_text('x')
    r = guard(ctx, command)
    assert r.returncode == 0, (command, r.stdout, r.stderr)
