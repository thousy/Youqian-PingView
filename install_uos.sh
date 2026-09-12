#!/bin/bash
# ==========================================================
# UOSPingView - 统信 UOS Desktop V25 一键系统安装脚本
# 支持双引擎容错部署，免除 401 商业源鉴权限制
# ==========================================================

if [ "$EUID" -ne 0 ]; then
    echo "[提示] 安装需要管理员权限，请使用 sudo 运行: sudo ./install_uos.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/uos_pingview"

echo "=========================================================="
echo "      正在将 UOSPingView 安装至统信 UOS 系统应用程序中...     "
echo "=========================================================="

# 1. 尝试安装 PyQt5 (若因源 401 失败则自动跳过，不阻断安装)
echo "[1/4] 检测与安装系统组件..."
if ! python3 -c "import PyQt5" &>/dev/null; then
    echo "[提示] 正在尝试通过官方源安装 python3-pyqt5..."
    apt update -qq 2>/dev/null && apt install -y python3-pyqt5 2>/dev/null || {
        echo "[提示] 统信商业源暂时受限(401)，程序将自动启用内置零依赖原生图形引擎，不影响正常使用！"
    }
fi

# 2. 部署程序到 /opt/uos_pingview
echo "[2/4] 部署文件到 ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"
cp -r "${SCRIPT_DIR}/uos_pingview/"* "${INSTALL_DIR}/"
chmod -R 755 "${INSTALL_DIR}"

# 3. 创建命令行执行软链接 /usr/bin/uospingview
cat << 'EOF' > /usr/bin/uospingview
#!/bin/bash
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb;wayland}"
exec /usr/bin/python3 /opt/uos_pingview/main.py "$@"
EOF
chmod 755 /usr/bin/uospingview

# 4. 注册系统快捷方式
echo "[3/4] 注册系统应用启动器..."
cat << 'EOF' > /usr/share/applications/uospingview.desktop
[Desktop Entry]
Name=UOSPingView
Name[zh_CN]=批量网络监控工具 (PingInfoView)
GenericName=Ping Monitor
GenericName[zh_CN]=网络连通性探测
Comment=Multi-Host Ping Monitor for UOS Desktop
Comment[zh_CN]=统信 UOS 批量多目标网络连通性监控工具
Exec=/usr/bin/uospingview %F
Icon=network-wired
Terminal=false
Type=Application
Categories=Network;System;Utility;
Keywords=ping;network;icmp;uos;monitor;
StartupNotify=true
EOF
chmod 644 /usr/share/applications/uospingview.desktop

# 5. 创建桌面快捷方式
CURRENT_USER="${SUDO_USER:-$USER}"
USER_HOME=$(eval echo "~${CURRENT_USER}")
if [ -d "${USER_HOME}/Desktop" ]; then
    echo "[4/4] 正在为您创建桌面快捷方式..."
    cp /usr/share/applications/uospingview.desktop "${USER_HOME}/Desktop/"
    chmod +x "${USER_HOME}/Desktop/uospingview.desktop"
    chown "${CURRENT_USER}:${CURRENT_USER}" "${USER_HOME}/Desktop/uospingview.desktop"
fi

# 刷新桌面应用缓存
if which update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi

echo "=========================================================="
echo " [完成] UOSPingView 安装成功！"
echo " 您可以在统信 UOS 的【启动器菜单】或【桌面】上直接双击打开！"
echo "=========================================================="
