#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Youqian-PingView - 统信 UOS 桌面操作系统 V25 批量 Ping 网络监控工具
主程序入口：支持 PyQt5 高清引擎与 Python 原生 Tkinter 零依赖双引擎自适应
"""

import sys
import os

# 确保项目根路径与模块路径加入 sys.path (根目录优先以完整包导入)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(1, BASE_DIR)

# 清理任何外部传入的非法带分号 QT_QPA_PLATFORM 环境变量 (Qt 不支持分号)
if "QT_QPA_PLATFORM" in os.environ and ";" in os.environ["QT_QPA_PLATFORM"]:
    del os.environ["QT_QPA_PLATFORM"]

# 优先探测 PyQt5/PySide6/PyQt6 绑定
USE_QT = False
try:
    try:
        from youqian_pingview.qt_compat import QT_BINDING, QApplication, Qt, QFont
        from youqian_pingview.ui.main_window import MainWindow
        if QT_BINDING:
            USE_QT = True
    except (ImportError, ModuleNotFoundError, ValueError):
        from qt_compat import QT_BINDING, QApplication, Qt, QFont
        from ui.main_window import MainWindow
        if QT_BINDING:
            USE_QT = True
except Exception:
    USE_QT = False


def run_qt_app():
    """使用 PyQt5/PySide6 豪华现代引擎启动"""
    try:
        from youqian_pingview.qt_compat import QApplication, Qt, QFont
        from youqian_pingview.ui.main_window import MainWindow
        from youqian_pingview.core.constants import APP_NAME
    except (ImportError, ModuleNotFoundError, ValueError):
        from qt_compat import QApplication, Qt, QFont
        from ui.main_window import MainWindow
        from core.constants import APP_NAME

    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

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


def run_tk_app(qt_error=None):
    """当系统无 PyQt5 且统信商业源受限时，使用 Python 原生零依赖 Tkinter 引擎启动"""
    try:
        try:
            from youqian_pingview.ui.tk_window import launch_tk_ui
        except (ImportError, ModuleNotFoundError, ValueError):
            from ui.tk_window import launch_tk_ui
        launch_tk_ui()
    except Exception as e:
        import traceback
        print(f"[错误] 原生 Tkinter 引擎启动失败: {e}", file=sys.stderr)
        traceback.print_exc()
        try:
            try:
                from youqian_pingview.qt_compat import notify_missing_dependency
            except (ImportError, ModuleNotFoundError, ValueError):
                from qt_compat import notify_missing_dependency
            notify_missing_dependency(qt_error=qt_error, tk_error=e)
        except Exception:
            pass
        sys.exit(1)


def main():
    if USE_QT:
        try:
            run_qt_app()
            return
        except Exception as e:
            import traceback
            print(f"[警告] Qt 引擎启动异常: {e}，正在无缝切换至原生保障引擎...", file=sys.stderr)
            traceback.print_exc()
            run_tk_app(qt_error=e)
    else:
        # 直接使用零依赖原生引擎
        run_tk_app()


if __name__ == "__main__":
    main()
