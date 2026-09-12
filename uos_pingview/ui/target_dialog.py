"""
目标录入与编辑对话框
"""

from ..qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QPushButton, QLabel, QFileDialog, QMessageBox
)
from ..core.target_parser import parse_targets_text, TargetItem
from typing import List


SAMPLE_TEXT = """# ==========================================
# 在下方输入需要探测的 IP 地址或主机名列表
# 支持以下常用格式 (每行一个目标，可带描述)：
# 1. 普通IP:        192.168.1.1
# 2. IP与描述:      192.168.1.1 核心交换机网关
# 3. 域名解析:      www.baidu.com 百度外网连通性
# 4. CIDR网段:      192.168.1.0/29 财务室子网 (自动展开)
# 5. IP连续范围:    192.168.1.10-192.168.1.20 打印机集群
# 6. TCP端口探测:   192.168.1.200:80 内网Web服务
# ==========================================
127.0.0.1 本机环回
223.5.5.5 阿里公共DNS
114.114.114.114 114公共DNS
"""


class TargetDialog(QDialog):
    def __init__(self, current_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("输入 Ping 目标地址列表")
        self.resize(680, 520)
        self.parsed_items: List[TargetItem] = []
        self.init_ui(current_text or SAMPLE_TEXT)

    def init_ui(self, initial_text: str):
        layout = QVBoxLayout(self)

        tip_label = QLabel("请输入 IP 地址、主机名或 CIDR 网段列表 (支持空格隔开添加中文描述，支持 # 注释行)：")
        tip_label.setStyleSheet("color: #475569; font-weight: bold; margin-bottom: 4px;")
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

    def get_text(self) -> str:
        return self.text_edit.toPlainText()
