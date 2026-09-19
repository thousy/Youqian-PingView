#!/bin/bash
# ==========================================================
# Youqian-PingView - 统信 UOS Desktop V25 一键启动脚本
# ==========================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 规范 Python 模块搜索路径
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}"

# 启动应用 (统一通过免安装引导入口安全加载)
exec python3 "${SCRIPT_DIR}/run.py" "$@"
