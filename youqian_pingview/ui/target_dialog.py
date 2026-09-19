"""
目标录入与编辑对话框
"""

try:
    from youqian_pingview.qt_compat import (
        QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
        QPushButton, QLabel, QFileDialog, QMessageBox
    )
    from youqian_pingview.core.target_parser import parse_targets_text, TargetItem
    from youqian_pingview.core.constants import SAMPLE_TEXT
except (ImportError, ModuleNotFoundError, ValueError):
    from qt_compat import (
        QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
        QPushButton, QLabel, QFileDialog, QMessageBox
    )
    from core.target_parser import parse_targets_text, TargetItem
    from core.constants import SAMPLE_TEXT
from typing import List


class TargetDialog(QDialog):
    def __init__(self, current_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("输入 Ping 目标地址列表")
        self.resize(680, 520)
        self.parsed_items: List[TargetItem] = []
        self.init_ui(current_text or SAMPLE_TEXT)

    def init_ui(self, initial_text: str):
        layout = QVBoxLayout(self)

        tip_label = QLabel(
            "<b>📌 目标输入格式：</b>每行一个地址，格式为 <code>IP/域名 [描述]</code>（如 <code>192.168.1.1 核心网关</code>，支持 <code>:80</code> 端口与 <code>/24</code> 网段）<br>"
            "<b>📁 分组设置方法：</b>单独起一行输入 <b><span style='color:#1d4ed8; background:#dbeafe; padding:1px 4px; border-radius:3px;'>Group: 分组名</span></b> 或 <b><span style='color:#1d4ed8; background:#dbeafe; padding:1px 4px; border-radius:3px;'>分组: 分组名</span></b>，下方地址自动归入该组（主界面表格支持双击分组折叠与展开）"
        )
        tip_label.setWordWrap(True)
        tip_label.setStyleSheet("""
            QLabel {
                background-color: #f8fafc;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 8px 12px;
                color: #334155;
                font-size: 12px;
                line-height: 140%;
                margin-bottom: 4px;
            }
        """)
        layout.addWidget(tip_label)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlainText(initial_text)
        self.text_edit.setStyleSheet("""
            QPlainTextEdit {
                font-family: 'Consolas', 'Courier New', 'Fira Code', monospace;
                font-size: 13px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 8px;
                background-color: #fafafa;
            }
        """)
        layout.addWidget(self.text_edit)

        # 按钮栏
        btn_bar = QHBoxLayout()

        btn_load = QPushButton("从文件载入...")
        btn_load.clicked.connect(self.load_from_file)
        btn_bar.addWidget(btn_load)

        btn_insert_group = QPushButton("➕ 插入分组模板")
        btn_insert_group.setToolTip("在当前光标处快速插入 Group: 分组名")
        btn_insert_group.clicked.connect(self.insert_group_template)
        btn_bar.addWidget(btn_insert_group)

        btn_clear = QPushButton("清空内容")
        btn_clear.clicked.connect(self.text_edit.clear)
        btn_bar.addWidget(btn_clear)

        btn_bar.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_bar.addWidget(btn_cancel)

        btn_confirm = QPushButton("解析并确认")
        btn_confirm.setStyleSheet("background-color: #2563eb; color: white; padding: 6px 18px; border-radius: 4px; font-weight: bold;")
        btn_confirm.clicked.connect(self.on_confirm)
        btn_bar.addWidget(btn_confirm)

        layout.addLayout(btn_bar)

    def load_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择包含目标列表的文本文件", "", "文本文件 (*.txt *.ini *.csv);;所有文件 (*)"
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                self.text_edit.setPlainText(content)
            except Exception as e:
                QMessageBox.critical(self, "读取失败", f"无法读取文件: {e}")

    def on_confirm(self):
        raw_text = self.text_edit.toPlainText().strip()
        if not raw_text:
            QMessageBox.warning(self, "提示", "请输入至少一个有效的 IP 地址或主机名！")
            return

        items = parse_targets_text(raw_text)
        if not items:
            QMessageBox.warning(self, "提示", "未能从输入内容中解析出有效的主机地址，请检查格式！")
            return

        self.parsed_items = items
        self.accept()

    def insert_group_template(self):
        """在当前光标位置插入分组模板行"""
        cursor = self.text_edit.textCursor()
        prefix = "\n" if cursor.position() > 0 and not self.text_edit.toPlainText().endswith("\n") else ""
        cursor.insertText(f"{prefix}Group: 新分组名称\n")
        self.text_edit.setTextCursor(cursor)
        self.text_edit.setFocus()

    def get_text(self) -> str:
        return self.text_edit.toPlainText()

