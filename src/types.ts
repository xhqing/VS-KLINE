/** 后端子进程状态。 */
export type BackendState = 'stopped' | 'starting' | 'running' | 'crashed';

/** 后端就绪后的连接端点。 */
export interface BackendEndpoints {
  httpBase: string;
  wsUrl: string;
  port: number;
}

/** 双面板默认标的（替代浏览器版 URL 参数 ?c1=&k1=&c2=&k2=）。 */
export interface DefaultSymbols {
  c1: string;
  k1: string;
  c2: string;
  k2: string;
}

/** 扩展配置（从 contributes.configuration 读取并类型化）。 */
export interface VskConfig {
  pythonPath: string;
  host: string;
  port: number;
  defaultSymbols: DefaultSymbols;
  opendHost: string;
  opendPort: number;
  retainContextWhenHidden: boolean;
  stopOnClose: boolean;
  autoRestart: boolean;
}
