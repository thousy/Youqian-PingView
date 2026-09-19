"""
Qt 库自适应兼容层：自动按优先级适配 PyQt5、PySide6、PyQt6
解决在不同统信 UOS / Linux 发行版环境下依赖库命名与安装差异问题
"""

import sys
import subprocess
import os

QT_BINDING = None

try:
    from PyQt5 import QtCore, QtGui, QtWidgets
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal as Signal, QObject, QPointF, QRectF, QPoint
    from PyQt5.QtGui import QColor, QBrush, QPen, QFont, QIcon, QPixmap, QPainter, QPolygonF, QCursor
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QSplitter, QTableWidget, QTableWidgetItem, QHeaderView, QToolBar,
        QAction, QStatusBar, QLabel, QLineEdit, QComboBox, QMenu,
        QMessageBox, QFileDialog, QAbstractItemView, QDialog, QFormLayout,
        QSpinBox, QCheckBox, QPushButton, QGroupBox, QPlainTextEdit, QGridLayout,
        QFontDialog, QSystemTrayIcon, QActionGroup
    )
    QT_BINDING = "PyQt5"
except ImportError:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPointF, QRectF, QPoint
        from PySide6.QtGui import QColor, QBrush, QPen, QFont, QIcon, QPixmap, QPainter, QPolygonF, QAction, QCursor, QActionGroup
        from PySide6.QtWidgets import (
            QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
            QSplitter, QTableWidget, QTableWidgetItem, QHeaderView, QToolBar,
            QStatusBar, QLabel, QLineEdit, QComboBox, QMenu,
            QMessageBox, QFileDialog, QAbstractItemView, QDialog, QFormLayout,
            QSpinBox, QCheckBox, QPushButton, QGroupBox, QPlainTextEdit, QGridLayout,
            QFontDialog, QSystemTrayIcon
        )
        QT_BINDING = "PySide6"
    except ImportError:
        try:
            from PyQt6 import QtCore, QtGui, QtWidgets
            from PyQt6.QtCore import Qt, QTimer, pyqtSignal as Signal, QObject, QPointF, QRectF, QPoint
            from PyQt6.QtGui import QColor, QBrush, QPen, QFont, QIcon, QPixmap, QPainter, QPolygonF, QAction, QCursor, QActionGroup
            from PyQt6.QtWidgets import (
                QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                QSplitter, QTableWidget, QTableWidgetItem, QHeaderView, QToolBar,
                QStatusBar, QLabel, QLineEdit, QComboBox, QMenu,
                QMessageBox, QFileDialog, QAbstractItemView, QDialog, QFormLayout,
                QSpinBox, QCheckBox, QPushButton, QGroupBox, QPlainTextEdit, QGridLayout,
                QFontDialog, QSystemTrayIcon
            )
            QT_BINDING = "PyQt6"
        except ImportError:
            QT_BINDING = None

if QT_BINDING is None:
    class _DummyQtMeta(type):
        def __getattr__(cls, name):
            return _DummyQt()

    class _DummyQt(metaclass=_DummyQtMeta):
        def __init__(self, *args, **kwargs):
            pass
        def __getattr__(self, name):
            return _DummyQt()
        def __call__(self, *args, **kwargs):
            return _DummyQt()
        def __int__(self):
            return 0
        def __index__(self):
            return 0

    def Signal(*args, **kwargs):
        class _DummySignal:
            def connect(self, *a, **kw): pass
            def emit(self, *a, **kw): pass
        return _DummySignal()

    QtCore = QtGui = QtWidgets = _DummyQt()
    Qt = QTimer = QObject = QPoint = QPointF = QRectF = _DummyQt
    QColor = QBrush = QPen = QFont = QIcon = QPixmap = QPainter = QPolygonF = QAction = QCursor = _DummyQt
    QApplication = QMainWindow = QWidget = QVBoxLayout = QHBoxLayout = _DummyQt
    QSplitter = QTableWidget = QTableWidgetItem = QHeaderView = QToolBar = _DummyQt
    QStatusBar = QLabel = QLineEdit = QComboBox = QMenu = _DummyQt
    QMessageBox = QFileDialog = QAbstractItemView = QDialog = QFormLayout = QGridLayout = _DummyQt
    QSpinBox = QCheckBox = QPushButton = QGroupBox = QPlainTextEdit = _DummyQt
    QFontDialog = QSystemTrayIcon = QActionGroup = _DummyQt


def notify_missing_dependency(qt_error=None, tk_error=None):
    """根据实际失败原因，给出醒目直观的中文桌面弹窗提示"""
    if QT_BINDING is not None and qt_error:
        title = "Youqian-PingView 启动异常"
        msg = (
            "【Youqian-PingView 图形引擎异常】\n\n"
            f"检测到已安装 {QT_BINDING}，但在初始化窗口时遇到异常：\n"
            f"{qt_error}\n\n"
            "解决方法：\n"
            "请在终端中运行以下命令以查看详细错误排查：\n"
            "./run_uos.sh\n"
        )
    else:
        title = "Youqian-PingView 依赖缺失提示"
        msg = (
            "【Youqian-PingView 启动失败】\n\n"
            "检测到当前统信 UOS 操作系统尚未安装图形界面库 (PyQt5 或 PySide6)。\n\n"
            "解决方法：\n"
            "请打开统信 UOS 终端，依次执行以下命令安装依赖：\n\n"
            "sudo apt update\n"
            "sudo apt install -y python3-pyqt5\n\n"
            "安装完成后再次双击本软件即可正常打开。"
        )

    # 1. 第一优先尝试 Python 自带原生弹窗 (若环境具备 tkinter)
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, msg)
        root.destroy()
        return
    except Exception:
        pass

    # 2. 尝试调用 Linux 常见桌面弹窗工具 (严格携带 --no-markup 杜绝 Pango 转义异常)
    dialog_tools = [
        ["zenity", "--error", "--no-markup", f"--title={title}", "--text", msg, "--width=480"],
        ["kdialog", "--error", msg, "--title", title],
        ["notify-send", "-u", "critical", title, msg[:120]]
    ]
    for cmd in dialog_tools:
        try:
            subprocess.run(cmd, check=True)
            return
        except Exception:
            continue

    # 3. 回退到终端输出
    print(msg, file=sys.stderr)
