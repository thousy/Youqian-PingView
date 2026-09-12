#!/bin/bash
# ==========================================================
# UOSPingView - 统信 UOS Desktop V25 一键启动脚本
# ==========================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 规范显示环境变量
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb;wayland}"

# 启动应用 (支持 PyQt5 优先与零依赖 Tkinter 自动回退)
python3 -m uos_pingview.main "$@"
