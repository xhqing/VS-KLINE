import * as cp from 'child_process';
import * as vscode from 'vscode';
import { readConfig } from './config';
import { resolvePython } from './pythonFinder';
import type { BackendEndpoints, BackendState } from './types';

type EndpointsListener = (ep: BackendEndpoints) => void;

/**
 * 管理 Python FastAPI 后端子进程：spawn / 动态端口解析 / 健康检查 / 重启 / 杀进程。
 *
 * - 端口：配置 port=0（默认，动态）→ 传 --port 0 给 uvicorn，解析启动日志拿实际端口；
 *        port>0 固定。
 * - 健康检查：轮询 GET /health，检查 opend 字段（OpenD 登录态）。
 * - 生命周期：deactivate / stop 命令 / VSCode 退出 时 SIGTERM→SIGKILL；崩溃可自动重启。
 */
export class BackendManager implements vscode.Disposable {
  private proc?: cp.ChildProcess;
  private state: BackendState = 'stopped';
  private port?: number;
  private startPromise?: Promise<BackendEndpoints>;
  private stopping = false;
  private lastErr = '';
  private readonly listeners = new Set<EndpointsListener>();
  private readonly disposables: vscode.Disposable[] = [];

  constructor(
    private readonly extDir: string,
    private readonly out: vscode.OutputChannel,
  ) {
    // VSCode 退出兜底杀进程（deactivate 不一定触发）
    const onExit = () => { void this.stop(); };
    process.on('exit', onExit);
    this.disposables.push({ dispose: () => process.off('exit', onExit) });
  }

  onEndpointsChange(listener: EndpointsListener): vscode.Disposable {
    this.listeners.add(listener);
    return { dispose: () => { this.listeners.delete(listener); } };
  }

  /** 幂等：并发调用复用同一次启动。 */
  async start(): Promise<BackendEndpoints> {
    if (this.startPromise) return this.startPromise;
    this.startPromise = this._start().finally(() => { this.startPromise = undefined; });
    return this.startPromise;
  }

  private async _start(): Promise<BackendEndpoints> {
    const cfg = readConfig();
    const python = await resolvePython(this.extDir, cfg.pythonPath);
    const wantPort = cfg.port > 0 ? cfg.port : 0; // 0 = dynamic

    const args = [
      '-m', 'uvicorn', 'backend.server:app',
      '--host', cfg.host, '--port', String(wantPort), '--workers', '1',
    ];
    const env = {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      VSKLINE_OPEND_HOST: cfg.opendHost,
      VSKLINE_OPEND_PORT: String(cfg.opendPort),
    };

    this.setState('starting');
    this.out.appendLine(`[vs-kline] spawn ${python} ${args.join(' ')}`);
    this.proc = cp.spawn(python, args, { cwd: this.extDir, env });
    this.pipe(this.proc.stdout, 'stdout');
    this.pipe(this.proc.stderr, 'stderr');
    this.proc.on('exit', (code, sig) => this.onExit(code, sig));
    this.proc.on('error', err => {
      this.lastErr = String(err);
      this.out.appendLine(`[vs-kline] spawn error: ${err}`);
    });

    const actualPort = wantPort > 0 ? wantPort : await this.waitPortFromLogs(20000);
    await this.waitHealth(cfg.host, actualPort, 30000);
    this.port = actualPort;
    this.setState('running');

    const ep: BackendEndpoints = {
      httpBase: `http://${cfg.host}:${actualPort}`,
      wsUrl: `ws://${cfg.host}:${actualPort}/ws`,
      port: actualPort,
    };
    this.out.appendLine(`[vs-kline] backend ready ${ep.httpBase}`);
    for (const l of this.listeners) l(ep);
    return ep;
  }

  /** 从 uvicorn 启动日志解析动态端口（日志默认走 stderr）。 */
  private waitPortFromLogs(timeoutMs: number): Promise<number> {
    const rx = /Uvicorn running on https?:\/\/[\d.]+:(\d+)/;
    return new Promise<number>((resolve, reject) => {
      const to = setTimeout(
        () => reject(new Error('端口发现超时：未在日志中找到 Uvicorn 启动行')),
        timeoutMs,
      );
      const onData = (b: Buffer): void => {
        const s = b.toString();
        this.lastErr += s.slice(-1024);
        const m = s.match(rx);
        if (m) { clearTimeout(to); resolve(Number(m[1])); }
      };
      this.proc?.stdout?.on('data', onData);
      this.proc?.stderr?.on('data', onData);
    });
  }

  private async waitHealth(host: string, port: number, timeoutMs: number): Promise<void> {
    const url = `http://${host}:${port}/health`;
    const deadline = Date.now() + timeoutMs;
    let lastState = "connecting";
    while (Date.now() < deadline) {
      let failed = false;
      let failMsg = "";
      try {
        const r = await fetch(url);
        if (r.ok) {
          const j = (await r.json()) as { opend_state?: string; opend_message?: string };
          lastState = j.opend_state ?? "connecting";
          if (j.opend_message) this.lastErr = j.opend_message;
          if (j.opend_state === "connected") return;
          if (j.opend_state === "failed") {
            failed = true;
            failMsg = j.opend_message || "OpenD 连接失败";
          }
        }
      } catch { /* 后端尚未起来，继续等 */ }
      if (failed) throw new Error(failMsg);
      await new Promise(r => setTimeout(r, 500));
    }
    throw new Error(
      `OpenD 连接超时（最后状态: ${lastState}）：请确认富途 OpenD 已启动并登录行情（${host}:11111）`,
    );
  }

  async stop(): Promise<void> {
    this.stopping = true;
    const proc = this.proc;
    this.proc = undefined;
    this.port = undefined;
    this.setState('stopped');
    if (!proc) { this.stopping = false; return; }
    try { proc.kill('SIGTERM'); } catch { /* ignore */ }
    await waitForExit(proc, 3000).catch(() => {
      try { proc.kill('SIGKILL'); } catch { /* ignore */ }
    });
    this.stopping = false;
    this.out.appendLine('[vs-kline] backend stopped');
  }

  async restart(): Promise<BackendEndpoints> {
    await this.stop();
    return this.start();
  }

  status(): { state: BackendState; port?: number; pid?: number } {
    return { state: this.state, port: this.port, pid: this.proc?.pid };
  }

  private onExit(code: number | null, sig: NodeJS.Signals | null): void {
    const intentional = this.stopping || this.state === 'stopped';
    this.proc = undefined;
    this.port = undefined;
    if (intentional) return;
    this.setState('crashed');
    if (/address already in use/i.test(this.lastErr)) {
      vscode.window.showErrorMessage('vs-kline: 后端端口被占用，建议将 vs-kline.port 设为 0（动态分配）。');
    } else {
      vscode.window.showWarningMessage(`vs-kline 后端异常退出 (code=${code} sig=${sig})，详见 Output 面板。`);
    }
    if (readConfig().autoRestart) {
      this.out.appendLine('[vs-kline] autoRestart → 3s 后重启');
      setTimeout(() => { void this.start().catch(() => {}); }, 3000);
    }
  }

  private pipe(s: NodeJS.ReadableStream | null, tag: string): void {
    s?.on('data', (b: Buffer) => this.out.appendLine(`[${tag}] ${b.toString().trimEnd()}`));
  }

  private setState(s: BackendState): void {
    this.state = s;
  }

  dispose(): void {
    void this.stop();
    for (const d of this.disposables) d.dispose();
  }
}

function waitForExit(proc: cp.ChildProcess, ms: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const to = setTimeout(() => reject(new Error('timeout')), ms);
    proc.once('exit', () => { clearTimeout(to); resolve(); });
  });
}
