#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UOSPingView - 统信 UOS 桌面操作系统 V25 批量 Ping 网络监控工具
主程序入口：支持 PyQt5 高清引擎与 Python 原生 Tkinter 零依赖双引擎自适应
"""

import sys
import os

# 确保项目根路径加入 sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

# 优先尝试导入 PyQt5/PySide6
USE_QT = False
try:
    if "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "xcb;wayland"

    from uos_pingview.qt_compat import QT_BINDING
    if QT_BINDING:
        from uos_pingview.qt_compat import QApplication, Qt, QFont
        from uos_pingview.ui.main_window import MainWindow
        USE_QT = True
except Exception:
    USE_QT = False


def run_qt_app():
    """使用 PyQt5/PySide6 豪华现代引擎启动"""
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("UOSPingView")
    app.setApplicationDisplayName("统信 UOS 批量网络监控工具")

    # 字体与 QSS
    font = QFont()
    font.setFamily("Noto Sans CJK SC, HarmonyOS Sans SC, Microsoft YaHei, sans-serif")
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        try:
            with open(sys.argv[1], "r", encoding="utf-8", errors="ignore") as f:
                window.load_initial_targets(f.read())
        except Exception:
            pass

    window.show()
    sys.exit(app.exec_())


def run_tk_app():
    """当系统无 PyQt5 且统信商业源受限时，使用 Python 原生零依赖 Tkinter 引擎启动"""
    try:
        from uos_pingview.ui.tk_window import launch_tk_ui
        launch_tk_ui()
    except Exception as e:
        print(f"启动失败: {e}", file=sys.stderr)
        try:
            from uos_pingview.qt_compat import notify_missing_dependency
            notify_missing_dependency()
        except Exception:
            pass
        sys.exit(1)


def main():
    if USE_QT:
        try:
            run_qt_app()
            return
        except Exception as e:
            # 若 Qt 启动过程因显示平台等异常崩溃，自动回退到 Tkinter
            print(f"[警告] Qt 引擎启动异常: {e}，正在无缝切换至原生保障引擎...", file=sys.stderr)
            run_tk_app()
    else:
        # 直接使用零依赖原生引擎
        run_tk_app()


if __name__ == "__main__":
    main()
