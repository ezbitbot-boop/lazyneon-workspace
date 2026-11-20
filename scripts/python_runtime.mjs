import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export function pythonCandidates(root) {
  // An explicit interpreter is authoritative; do not silently run a different environment.
  const override = process.env.LAZYNEON_WS_PYTHON || process.env.LAZYNEON_WS_LEGACY_PYTHON;
  if (override) return [{cmd: override, pre: []}];
  const candidates = [];
  for (const base of [path.join(root, '.venv'), path.join(os.homedir(), '.lazyneon-workspace', 'venv')]) {
    for (const suffix of ['bin/python', 'Scripts/python.exe']) {
      const cmd = path.join(base, suffix);
      if (fs.existsSync(cmd)) candidates.push({cmd, pre: []});
    }
  }
  return [...candidates, ...['python3', 'python', 'py'].map(cmd => ({cmd, pre: cmd === 'py' ? ['-3'] : []}))];
}
export function isPythonLauncherStub(result) {
  return result.status !== 0 && (result.status === 9009 ||
    /Python was not found|No Python installation|^Python\s*$|Microsoft Store|WindowsApps|AppExecutionAlias|xcode-select:.*(?:No developer tools|invalid developer)|xcrun:.*invalid active developer path/i.test((result.stderr || '').trim()));
}
