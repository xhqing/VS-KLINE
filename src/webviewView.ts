import * as vscode from 'vscode';
import { BackendManager } from './backend';
import { readConfig } from './config';
import { renderHtml } from './webview';

/**
 * 活动栏看盘入口：注册为 WebviewView，点活动栏 vs-kline 图标即在侧边栏显示看盘页。
 *
 * resolveWebviewView 在用户首次展开该 view 时触发：拉起后端 + 渲染。
 */
export class KlineViewProvider implements vscode.WebviewViewProvider {
  constructor(
    private readonly ext: vscode.ExtensionContext,
    private readonly backend: BackendManager,
  ) {}

  async resolveWebviewView(view: vscode.WebviewView): Promise<void> {
    view.webview.options = { enableScripts: true, localResourceRoots: [this.ext.extensionUri] };

    let ep;
    try {
      ep = await this.backend.start();
    } catch (e) {
      view.webview.html = this.errorHtml(e);
      return;
    }
    view.webview.html = renderHtml(view.webview, this.ext.extensionUri, this.ext.extensionPath, ep, readConfig());

    // 后端 restart 后端口变化 → 重渲染重连
    this.backend.onEndpointsChange(ep2 => {
      if (view.visible) {
        view.webview.html = renderHtml(view.webview, this.ext.extensionUri, this.ext.extensionPath, ep2, readConfig());
      }
    });
  }

  private errorHtml(e: unknown): string {
    const msg = (e instanceof Error ? e.message : String(e))
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return `<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="font:13px -apple-system,'PingFang SC',sans-serif;color:#cdd3dc;background:#0e1116;padding:16px">
<h3 style="margin-top:0">vs-kline 后端启动失败</h3>
<pre style="white-space:pre-wrap;word-break:break-all">${msg}</pre>
<p>详见 Output 面板「vs-kline」通道。修复后点活动栏图标重试。</p>
</body></html>`;
  }
}
