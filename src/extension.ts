import * as vscode from 'vscode';
import { BackendManager } from './backend';
import { isBackendAffectingChange, readConfig } from './config';
import { WebviewController } from './webview';
import { KlineViewProvider } from './webviewView';

/**
 * vs-kline 扩展入口。
 *
 * - 活动栏入口：点 vs-kline 图标 → 侧边栏直接显示看盘 webview（主入口，一键开）
 * - 命令 vs-kline.open：打开居中大面板（看盘大屏）
 * - start/stop/restart/status：管理后端子进程
 * - 配置热应用：影响后端的配置变更提示 restart
 */
export function activate(context: vscode.ExtensionContext) {
  const output = vscode.window.createOutputChannel('vs-kline');
  context.subscriptions.push(output);

  const backend = new BackendManager(context.extensionPath, output);
  const webview = new WebviewController(context, backend);
  context.subscriptions.push(backend, webview);

  // 活动栏入口：注册 WebviewView，点图标即在侧边栏看盘
  const viewProvider = new KlineViewProvider(context, backend);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('vs-kline.view', viewProvider, {
      webviewOptions: { retainContextWhenHidden: readConfig().retainContextWhenHidden },
    }),
  );

  const showError = (e: unknown): void => {
    vscode.window.showErrorMessage(`vs-kline: ${e instanceof Error ? e.message : String(e)}`);
  };

  context.subscriptions.push(
    vscode.commands.registerCommand('vs-kline.open', async () => {
      try { await webview.open(); } catch (e) { showError(e); }
    }),
    vscode.commands.registerCommand('vs-kline.start', async () => {
      try {
        const ep = await backend.start();
        vscode.window.showInformationMessage(`vs-kline 后端就绪 ${ep.httpBase}`);
      } catch (e) { showError(e); }
    }),
    vscode.commands.registerCommand('vs-kline.stop', () => { void backend.stop(); }),
    vscode.commands.registerCommand('vs-kline.restart', async () => {
      try {
        const ep = await backend.restart();
        vscode.window.showInformationMessage(`vs-kline 后端已重启 ${ep.httpBase}`);
      } catch (e) { showError(e); }
    }),
    vscode.commands.registerCommand('vs-kline.status', () => {
      const s = backend.status();
      output.show();
      output.appendLine(`[status] state=${s.state} port=${s.port ?? '-'} pid=${s.pid ?? '-'}`);
    }),
  );

  // 配置热应用：影响后端的配置变更，提示是否 restart
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration(e => {
      if (isBackendAffectingChange(e) && backend.status().state === 'running') {
        vscode.window.showWarningMessage('vs-kline: 配置已变更，需重启后端生效。', '立即重启')
          .then(choice => {
            if (choice === '立即重启') { void backend.restart().catch(() => {}); }
          });
      }
    }),
  );

  console.log('[vs-kline] extension activated');
}

export function deactivate(): void {
  // backend / webview 经 subscriptions 自动 dispose
}
