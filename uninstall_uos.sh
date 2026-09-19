#!/bin/bash
# ==========================================================
# Youqian-PingView - 统信 UOS 一键彻底卸载与清理脚本
# 彻底清除系统应用、快捷方式与残留配置
# ==========================================================

if [ "$EUID" -ne 0 ]; then
    echo "[提示] 卸载需要管理员权限，请使用 sudo 运行: sudo ./uninstall_uos.sh"
    exit 1
fi

echo "=========================================================="
echo "        正在彻底清理并卸载 Youqian-PingView...           "
echo "=========================================================="

# 1. 尝试从 dpkg 卸载 (支持新旧包名)
dpkg -r --force-all youqian-pingview 2>/dev/null || true
dpkg -r --force-all uospingview 2>/dev/null || true

# 2. 清理系统部署文件
rm -rf /opt/youqian-pingview /opt/uos_pingview
rm -f /usr/bin/youqian-pingview /usr/bin/uospingview
rm -f /usr/share/applications/youqian-pingview.desktop /usr/share/applications/uospingview.desktop
rm -f /usr/share/pixmaps/youqian-pingview.svg /usr/share/pixmaps/uospingview.svg

# 3. 清理桌面快捷方式
CURRENT_USER="${SUDO_USER:-$USER}"
USER_HOME=$(eval echo "~${CURRENT_USER}")
if [ -d "${USER_HOME}/Desktop" ]; then
    rm -f "${USER_HOME}/Desktop/youqian-pingview.desktop"
    rm -f "${USER_HOME}/Desktop/uospingview.desktop"
fi

# 4. 刷新系统桌面应用数据库
if which update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi

echo "=========================================================="
echo " [完成] Youqian-PingView 已彻底从您的统信系统中清理卸载干净！"
echo "=========================================================="
