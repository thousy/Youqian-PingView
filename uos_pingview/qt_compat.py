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
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal as Signal, QObject, QPointF, QRectF
    from PyQt5.QtGui import QColor, QBrush, QPen, QFont, QIcon, QPixmap, QPainter, QPolygonF
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QSplitter, QTableWidget, QTableWidgetItem, QHeaderView, QToolBar,
        QAction, QStatusBar, QLabel, QLineEdit, QComboBox, QMenu,
        QMessageBox, QFileDialog, QAbstractItemView, QDialog, QFormLayout,
        QSpinBox, QCheckBox, QPushButton, QGroupBox, QPlainTextEdit
    )
    QT_BINDING = "PyQt5"
except ImportError:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPointF, QRectF
        from PySide6.QtGui import QColor, QBrush, QPen, QFont, QIcon, QPixmap, QPainter, QPolygonF, QAction
        from PySide6.QtWidgets import (
            QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
            QSplitter, QTableWidget, QTableWidgetItem, QHeaderView, QToolBar,
            QStatusBar, QLabel, QLineEdit, QComboBox, QMenu,
            QMessageBox, QFileDialog, QAbstractItemView, QDialog, QFormLayout,
            QSpinBox, QCheckBox, QPushButton, QGroupBox, QPlainTextEdit
        )
        QT_BINDING = "PySide6"
    except ImportError:
        try:
            from PyQt6 import QtCore, QtGui, QtWidgets
            from PyQt6.QtCore import Qt, QTimer, pyqtSignal as Signal, QObject, QPointF, QRectF
            from PyQt6.QtGui import QColor, QBrush, QPen, QFont, QIcon, QPixmap, QPainter, QPolygonF, QAction
            from PyQt6.QtWidgets import (
                QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                QSplitter, QTableWidget, QTableWidgetItem, QHeaderView, QToolBar,
                QStatusBar, QLabel, QLineEdit, QComboBox, QMenu,
                QMessageBox, QFileDialog, QAbstractItemView, QDialog, QFormLayout,
                QSpinBox, QCheckBox, QPushButton, QGroupBox, QPlainTextEdit
            )
            QT_BINDING = "PyQt6"
        except ImportError:
            QT_BINDING = None


def notify_missing_dependency():
    """当系统缺失 Qt 依赖库时，给出醒目的中文桌面弹窗提示而不是无反应静默退出"""
    msg = (
        "【UOSPingView 启动失败】\n\n"
        "检测到当前统信 UOS 操作系统尚未安装图形界面库 (PyQt5 或 PySide6)。\n\n"
        "解决方法：\n"
        "请打开统信 UOS 终端，执行以下命令安装依赖：\n\n"
        "sudo apt update && sudo apt install -y python3-pyqt5\n\n"
        "安装完成后再次双击本软件即可正常打开。"
    )
    # 尝试调用 Linux 常见对话框工具
    dialog_tools = [
        ["zenity", "--error", "--title=UOSPingView 依赖缺失提示", f"--text={msg}", "--width=450"],
        ["kdialog", "--error", msg, "--title", "UOSPingView 依赖缺失提示"],
        ["notify-send", "-u", "critical", "UOSPingView 启动失败", "缺少 python3-pyqt5 依赖，请在终端执行: sudo apt install python3-pyqt5"]
    ]
    for cmd in dialog_tools:
        try:
            subprocess.run(cmd, check=True)
            return
        except Exception:
            continue

    # 回退到终端输出
    print(msg, file=sys.stderr)
