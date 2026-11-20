import path from 'node:path';

// Host workspace is authoritative. Never infer a case from the plugin/caller cwd.
export function resolveWorkspace(payload = {}) {
  if (!payload || typeof payload !== 'object') return null;
  for (const value of [payload.workspacePaths?.[0], payload.cwd, payload.workspace]) {
    if (typeof value === 'string' && path.isAbsolute(value)) return path.normalize(value);
  }
  return null;
}
export function workspaceFromSources(sources) {
  for (const source of sources) {
    const workspace = resolveWorkspace(source.parsed);
    if (workspace) return workspace;
  }
  return null;
}
export function resolveTarget(target, workspace) {
  if (!target) return '';
  return path.isAbsolute(target) ? path.normalize(target) : workspace ? path.resolve(workspace, target) : '';
}
export async function readHookStdin(timeout = 1500) {
  if (process.stdin.isTTY) return '';
  return new Promise((resolve) => {
    let text = '';
    let idle;
    const done = () => {
      clearTimeout(timer);
      clearTimeout(idle);
      process.stdin.removeListener('data', data);
      process.stdin.removeListener('end', done);
      process.stdin.removeListener('error', done);
      process.stdin.pause();
      resolve(text);
    };
    const data = chunk => {
      text += chunk;
      clearTimeout(idle);
      try { JSON.parse(text); done(); return; } catch {}
      idle = setTimeout(done, 75);
    };
    const timer = setTimeout(done, timeout);
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', data).once('end', done).once('error', done);
    process.stdin.resume();
  });
}
