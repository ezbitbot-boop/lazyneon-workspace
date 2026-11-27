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
// Domain guards (evidence, hallucination, legal_factuality, slop, citation) share this reader.
// The host writes JSON and closes the pipe; a complete JSON document resolves at once,
// so the limit only matters when the host is slow. 50ms dropped late input and let it
// pass (fail-open), hence 1500ms. fstat().size is not used: it is 0 for pipes on Linux/Windows.
export const GUARD_STDIN_WAIT_MS = 1500;
export function readGuardStdin(limitMs = GUARD_STDIN_WAIT_MS) {
	const stdin = process.stdin;
	return new Promise((resolve) => {
		if (stdin.isTTY) {
			resolve('');
			return;
		}
		const chunks = [];
		let settled = false;
		const finish = (value) => {
			if (settled) return;
			settled = true;
			clearTimeout(timer);
			try { stdin.pause(); } catch {}
			stdin.removeAllListeners();
			resolve(value);
		};
		const timer = setTimeout(() => finish(Buffer.concat(chunks).toString('utf8')), limitMs);
		if (typeof timer.unref === 'function') timer.unref();
		stdin.on('data', (chunk) => {
			chunks.push(chunk);
			const acc = Buffer.concat(chunks).toString('utf8').trim();
			if ((acc.startsWith('{') && acc.endsWith('}')) || (acc.startsWith('[') && acc.endsWith(']'))) {
				try {
					JSON.parse(acc);
					finish(acc);
				} catch {}
			}
		});
		stdin.on('end', () => finish(Buffer.concat(chunks).toString('utf8')));
		stdin.on('error', () => finish(''));
	});
}
