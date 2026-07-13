import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';
import { BackendManager } from './backend';
import { readConfig } from './config';
import type { BackendEndpoints, VskConfig } from './types';

/**
 * 渲染看盘 webview HTML：注入 CSP / nonce / 资源 URI / ws 地址 / 默认标的。
 * WebviewPanel（居中大面板）与 WebviewView（侧边栏）共用此函数。
 */
export function renderHtml(
  webview: vscode.Webview,
  extensionUri: vscode.Uri,
  extensionPath: string,
  ep: BackendEndpoints,
  cfg: VskConfig,
): string {
  const nonce = crypto.randomBytes(16).toString('base64');
  const chartUri = webview.asWebviewUri(
    vscode.Uri.joinPath(extensionUri, 'webview', 'vendor', 'lightweight-charts.standalone.production.js'),
  );
  const csp = [
    "default-src 'none'",
    `img-src ${webview.cspSource} https: data:`,
    `style-src ${webview.cspSource} 'unsafe-inline'`,
    `script-src 'nonce-${nonce}' ${webview.cspSource}`,
    `connect-src ${webview.cspSource} ${ep.httpBase} ${ep.wsUrl}`,
  ].join('; ');

  const htmlPath = path.join(extensionPath, 'webview', 'index.html');
  const html = fs.readFileSync(htmlPath, 'utf8');
  return html
    .replaceAll('__CSP__', csp)
    .replaceAll('__NONCE__', nonce)
    .replaceAll('__CHART_URI__', chartUri.toString())
    .replaceAll('__WS_URL__', JSON.stringify(ep.wsUrl))
    .replaceAll('__DEFAULTS__', JSON.stringify(cfg.defaultSymbols));
}

/**
 * WebviewPanel 控制器：命令 vs-kline.open 打开的居中大面板（看盘大屏）。
 */
export class WebviewController implements vscode.Disposable {
  private panel?: vscode.WebviewPanel;
  private readonly disposables: vscode.Disposable[] = [];

  constructor(
    private readonly ext: vscode.ExtensionContext,
    private readonly backend: BackendManager,
  ) {}

  async open(): Promise<void> {
    if (this.panel) { this.panel.reveal(vscode.ViewColumn.Active, true); return; }

    const ep = await this.backend.start();
    const cfg = readConfig();
    const panel = vscode.window.createWebviewPanel(
      'vs-kline',
      'vs-kline',
      vscode.ViewColumn.Active,
      {
        enableScripts: true,
        retainContextWhenHidden: cfg.retainContextWhenHidden,
        localResourceRoots: [this.ext.extensionUri],
      },
    );
    panel.iconPath = vscode.Uri.joinPath(this.ext.extensionUri, 'media', 'icon.svg');
    panel.webview.html = renderHtml(panel.webview, this.ext.extensionUri, this.ext.extensionPath, ep, cfg);

    panel.onDidDispose(() => {
      this.panel = undefined;
      if (readConfig().stopOnClose) { void this.backend.stop(); }
    }, null, this.disposables);

    this.backend.onEndpointsChange(ep2 => {
      if (this.panel) {
        this.panel.webview.html = renderHtml(this.panel.webview, this.ext.extensionUri, this.ext.extensionPath, ep2, readConfig());
      }
    });

    this.panel = panel;
  }

  dispose(): void {
    this.panel?.dispose();
    for (const d of this.disposables) d.dispose();
  }
}
