import * as cp from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';

// mac/linux: .venv/bin/python；windows: .venv/Scripts/python.exe
const VENV_BIN_DIRS = ['bin', 'Scripts'];
const VENV_NAMES = ['python', 'python3', 'python.exe'];

/**
 * 探测可 `import futu, fastapi, uvicorn` 的 Python 解释器。
 *
 * 候选顺序：配置 pythonPath → 扩展目录 .venv → workspace .venv → PATH python3/python。
 * 每个候选 spawnSync 校验 import，首个通过者胜出。
 * （futu-api 用 setup.py install，pip 进普通 venv 会装坏，必须校验。）
 */
export async function resolvePython(extDir: string, configuredPath: string): Promise<string> {
  const candidates: string[] = [];
  if (configuredPath) candidates.push(configuredPath);
  pushVenv(candidates, extDir);
  const ws = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (ws) pushVenv(candidates, ws);
  const onPath = await which('python3');
  if (onPath) candidates.push(onPath);
  const onPathPy = await which('python');
  if (onPathPy) candidates.push(onPathPy);

  const seen = new Set<string>();
  for (const py of candidates) {
    if (!py || seen.has(py)) continue;
    seen.add(py);
    if (await canImportFutu(py)) return py;
  }

  throw new Error(
    '未找到可 import futu 的 Python 解释器。请创建 venv（mac 需 --system-site-packages，见 README）'
    + '或在设置中配置 vs-kline.pythonPath。',
  );
}

function pushVenv(out: string[], root: string): void {
  for (const bin of VENV_BIN_DIRS) {
    for (const name of VENV_NAMES) {
      out.push(path.join(root, '.venv', bin, name));
    }
  }
}

function which(cmd: string): Promise<string | undefined> {
  return new Promise(resolve => {
    cp.execFile('which', [cmd], { encoding: 'utf8' }, (err, stdout) => {
      if (err) return resolve(undefined);
      const p = stdout.trim().split('\n')[0];
      resolve(p || undefined);
    });
  });
}

function canImportFutu(py: string): Promise<boolean> {
  return new Promise(resolve => {
    if (!fs.existsSync(py)) return resolve(false);
    try {
      const r = cp.spawnSync(py, ['-c', 'import futu, fastapi, uvicorn'], {
        encoding: 'utf8',
        timeout: 10000,
      });
      resolve(r.status === 0);
    } catch {
      resolve(false);
    }
  });
}
