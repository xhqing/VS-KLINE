import * as vscode from 'vscode';
import type { VskConfig, DefaultSymbols } from './types';

/** 读取并类型化 vs-kline.* 配置。 */
export function readConfig(): VskConfig {
  const cfg = vscode.workspace.getConfiguration('vs-kline');
  const ds = cfg.get<Partial<DefaultSymbols>>('defaultSymbols', {});
  const defaultSymbols: DefaultSymbols = {
    c1: ds.c1 ?? 'HK.02800',
    k1: ds.k1 ?? 'K_5M',
    c2: ds.c2 ?? 'US.AAPL',
    k2: ds.k2 ?? 'K_15M',
  };
  return {
    pythonPath: cfg.get<string>('pythonPath', ''),
    host: cfg.get<string>('host', '127.0.0.1'),
    port: cfg.get<number>('port', 0),
    defaultSymbols,
    opendHost: cfg.get<string>('opendHost', '127.0.0.1'),
    opendPort: cfg.get<number>('opendPort', 11111),
    retainContextWhenHidden: cfg.get<boolean>('retainContextWhenHidden', true),
    stopOnClose: cfg.get<boolean>('stopOnClose', true),
    autoRestart: cfg.get<boolean>('autoRestart', false),
  };
}

/** 影响后端的配置项（变更需 restart 生效）。 */
const BACKEND_AFFECTING = [
  'vs-kline.pythonPath',
  'vs-kline.host',
  'vs-kline.port',
  'vs-kline.opendHost',
  'vs-kline.opendPort',
];

export function isBackendAffectingChange(e: vscode.ConfigurationChangeEvent): boolean {
  return BACKEND_AFFECTING.some(k => e.affectsConfiguration(k));
}
