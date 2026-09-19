#!/bin/bash
# ==========================================================
# Youqian-PingView - 统信 UOS Desktop V25 一键系统安装脚本
# 支持双引擎容错部署，免除 401 商业源鉴权限制
# ==========================================================

set -e

if [ "$EUID" -ne 0 ]; then
    echo "[提示] 安装需要管理员权限，请使用 sudo 运行: sudo ./install_uos.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/youqian-pingview"

echo "=========================================================="
echo "    正在将 Youqian-PingView 安装至统信 UOS 系统中...     "
echo "=========================================================="

# 1. 尝试安装 PyQt5 或 python3-tk 组件
echo "[1/4] 检测与安装系统组件..."
set +e
if ! python3 -c "import PyQt5" &>/dev/null; then
    echo "[提示] 未检测到 PyQt5，尝试通过 apt 安装 python3-pyqt5..."
    if apt update -qq && apt install -y python3-pyqt5; then
        echo "[提示] python3-pyqt5 安装成功。"
    else
        echo "[提示] python3-pyqt5 安装未完成。若当前网络源受限或离线，程序将自动回退到 Tkinter 原生引擎。"
        if ! python3 -c "import tkinter" &>/dev/null; then
            echo "[提示] 尝试安装 python3-tk 作为后备图形引擎..."
            apt install -y python3-tk || true
        fi
    fi
else
    echo "[提示] 系统已就绪 PyQt5 现代图形环境。"
fi
set -e

# 2. 部署程序到 /opt/youqian-pingview
echo "[2/4] 部署文件到 ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}/youqian_pingview"
cp -r "${SCRIPT_DIR}/youqian_pingview/"* "${INSTALL_DIR}/youqian_pingview/"

# 创建引导 main.py
cat << 'EOF' > "${INSTALL_DIR}/main.py"
#!/usr/bin/env python3
import sys
import os

_base = os.path.dirname(os.path.abspath(__file__))
if _base not in sys.path:
    sys.path.insert(0, _base)

from youqian_pingview.main import main

if __name__ == "__main__":
    main()
EOF
chmod -R 755 "${INSTALL_DIR}"

# 3. 创建命令行执行软链接 /usr/bin/youqian-pingview
cat << 'EOF' > /usr/bin/youqian-pingview
#!/bin/bash
export PYTHONPATH="/opt/youqian-pingview:${PYTHONPATH}"
exec /usr/bin/python3 /opt/youqian-pingview/main.py "$@"
EOF
chmod 755 /usr/bin/youqian-pingview

# 4. 注册系统快捷方式
echo "[3/4] 注册系统应用启动器..."
cat << 'EOF' > /usr/share/applications/youqian-pingview.desktop
[Desktop Entry]
Name=Youqian-PingView
Name[zh_CN]=YouQian 批量网络监控工具
GenericName=Ping Monitor
GenericName[zh_CN]=网络连通性探测
Comment=Multi-Host Ping Monitor for Linux Desktop
Comment[zh_CN]=YouQian 批量多目标网络连通性监控工具
Exec=/usr/bin/youqian-pingview %F
Icon=network-wired
Terminal=false
Type=Application
Categories=Network;System;Utility;
Keywords=ping;network;icmp;uos;monitor;youqian;
StartupNotify=true
EOF
chmod 644 /usr/share/applications/youqian-pingview.desktop

# 5. 创建桌面快捷方式
CURRENT_USER="${SUDO_USER:-$USER}"
USER_HOME=$(eval echo "~${CURRENT_USER}")
if [ -d "${USER_HOME}/Desktop" ]; then
    echo "[4/4] 正在为您创建桌面快捷方式..."
    cp /usr/share/applications/youqian-pingview.desktop "${USER_HOME}/Desktop/"
    chmod +x "${USER_HOME}/Desktop/youqian-pingview.desktop"
    chown "${CURRENT_USER}:${CURRENT_USER}" "${USER_HOME}/Desktop/youqian-pingview.desktop"
fi

# 刷新桌面应用缓存
if which update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi

echo "=========================================================="
echo " [完成] Youqian-PingView 安装成功！"
echo " 您可以在统信 UOS 的【启动器菜单】或【桌面】上直接双击打开！"
echo "=========================================================="
