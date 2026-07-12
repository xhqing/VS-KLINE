#!/usr/bin/env bash
# 安装 vs-kline：生成 launchd plist + symlink CLI 到 /usr/local/bin
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LABEL="com.xhq.vs-kline.backend"
PLIST_SRC="$PROJECT_DIR/deploy/launchd/${LABEL}.plist"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$HOME/Library/Logs/vs-kline"
BIN_SRC="$PROJECT_DIR/bin/vs-kline"
BIN_DST="$HOME/.local/bin/vs-kline"

echo "=== 安装 vs-kline ==="

# 1. 生成 plist（替换路径占位符）
mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" -e "s|__HOME__|$HOME|g" "$PLIST_SRC" > "$PLIST_DST"
echo "✅ plist → $PLIST_DST"

# 2. CLI 可执行
chmod +x "$BIN_SRC"

# 3. symlink 到 ~/.local/bin（在 PATH、免 sudo）
mkdir -p "$(dirname "$BIN_DST")"
ln -sf "$BIN_SRC" "$BIN_DST"
echo "✅ CLI → $BIN_DST"

echo ""
echo "=== 安装完成。启动: vs-kline start ==="
