"""
属性对话框模块：1:1 复刻原版 PingInfoView 经典属性查看窗口
"""

try:
    from youqian_pingview.qt_compat import (
        QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
        QPushButton, QLabel, QFont, Qt
    )
    from youqian_pingview.core.pinger import HostStat
except (ImportError, ModuleNotFoundError, ValueError):
    from qt_compat import (
        QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
        QPushButton, QLabel, QFont, Qt
    )
    from core.pinger import HostStat


class PropertiesDialog(QDialog):
    def __init__(self, host: HostStat, parent=None):
        super().__init__(parent)
        self.host = host
        self.setWindowTitle("属性")
        self.setFixedWidth(440)
        self.init_ui()

    def _create_readonly_edit(self, text: str) -> QLineEdit:
        edit = QLineEdit(text)
        edit.setReadOnly(True)
        edit.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                color: #000088;
                border: 1px solid #7a7a7a;
                border-radius: 1px;
                padding: 2px 4px;
                font-family: 'Segoe UI', 'SimSun', 'Microsoft YaHei', sans-serif;
                font-size: 12px;
            }
        """)
        return edit

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(4)

        # 映射属性值
        h = self.host
        latency_str = f"{h.last_latency_ms:.3f}" if h.last_latency_ms is not None else ""
        avg_str = f"{h.avg_latency_ms:.3f}" if h.avg_latency_ms is not None else ""
        min_str = f"{h.min_latency_ms:.3f}" if h.min_latency_ms is not None else ""
        max_str = f"{h.max_latency_ms:.3f}" if h.max_latency_ms is not None else ""
        ttl_str = str(h.last_ttl) if h.last_ttl is not None else ""

        fields = [
            ("主机名:", f"{h.target}:{h.port}" if h.port else h.target),
            ("IP 地址:", h.resolved_ip or h.target),
            ("响应 IP 地址:", h.reply_ip or h.resolved_ip or h.target),
            ("成功次数:", str(h.success_count)),
            ("失败次数:", str(h.failed_count)),
            ("连续失败次数:", str(h.consecutive_failures) if h.consecutive_failures > 0 else ""),
            ("最大连续失败次数:", str(h.max_consecutive_failures) if h.max_consecutive_failures > 0 else ""),
            ("最大连续失败时间:", h.max_consecutive_failure_time or ""),
            ("失败率(%):", f"{h.failure_rate:.0f}%" if h.total_sent > 0 else ""),
            ("总计发送Pings数:", str(h.total_sent)),
            ("最后 Ping 状态:", h.last_status),
            ("最后 Ping 时间:", latency_str),
            ("最后 Ping TTL:", ttl_str),
            ("平均 Ping 时间:", avg_str),
            ("描述:", h.description or ""),
            ("最后成功时间:", h.last_success_time or ""),
            ("最后失败时间:", h.last_failed_time or ""),
            ("最小Ping时间:", min_str),
            ("序号:", str(h.index)),
            ("所属分组:", h.group or "默认分组"),
            ("禁用:", "是" if not h.enabled else "否"),
            ("MAC 地址:", h.mac_address or ""),
        ]

        for label_text, val in fields:
            lbl = QLabel(label_text)
            lbl.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
            lbl.setFixedWidth(120)
            form.addRow(lbl, self._create_readonly_edit(val))

        layout.addLayout(form)

        # 底部确定按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_ok = QPushButton("确定")
        btn_ok.setFixedWidth(75)
        btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(btn_ok)

        layout.addLayout(btn_layout)
