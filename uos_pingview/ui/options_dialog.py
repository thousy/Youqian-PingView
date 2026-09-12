"""
Ping 探测选项与参数配置对话框
"""

from ..qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QSpinBox,
    QCheckBox, QPushButton, QGroupBox, QLabel
)
from ..core.pinger import PingOptions


class OptionsDialog(QDialog):
    def __init__(self, options: PingOptions, parent=None):
        super().__init__(parent)
        self.options = options
        self.setWindowTitle("Ping 选项设置")
        self.setMinimumWidth(400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        basic_group = QGroupBox("基础探测参数")
        form1 = QFormLayout()

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 3600)
        self.spin_interval.setValue(self.options.interval_sec)
        self.spin_interval.setSuffix(" 秒")
        form1.addRow("探测轮询间隔:", self.spin_interval)

        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(100, 30000)
        self.spin_timeout.setSingleStep(500)
        self.spin_timeout.setValue(self.options.timeout_ms)
        self.spin_timeout.setSuffix(" 毫秒")
        form1.addRow("单次探测超时:", self.spin_timeout)

        self.spin_size = QSpinBox()
        self.spin_size.setRange(16, 65500)
        self.spin_size.setValue(self.options.packet_size)
        self.spin_size.setSuffix(" 字节")
        form1.addRow("数据包大小:", self.spin_size)

        basic_group.setLayout(form1)
        layout.addWidget(basic_group)

        perf_group = QGroupBox("性能与并发控制")
        form2 = QFormLayout()

        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 300)
        self.spin_threads.setValue(self.options.max_threads)
        self.spin_threads.setSuffix(" 个线程")
        form2.addRow("最大并发线程数:", self.spin_threads)

        self.spin_history = QSpinBox()
        self.spin_history.setRange(50, 5000)
        self.spin_history.setSingleStep(50)
        self.spin_history.setValue(self.options.limit_history_count)
        self.spin_history.setSuffix(" 条")
        form2.addRow("下窗格明细最大保留数:", self.spin_history)

        perf_group.setLayout(form2)
        layout.addWidget(perf_group)

        alarm_group = QGroupBox("故障与告警设置")
        form3 = QFormLayout()

        self.chk_alarm = QCheckBox("开启连续失败蜂鸣/提示音")
        self.chk_alarm.setChecked(self.options.alarm_on_fail)
        form3.addRow(self.chk_alarm)

        self.spin_threshold = QSpinBox()
        self.spin_threshold.setRange(1, 50)
        self.spin_threshold.setValue(self.options.alarm_fail_threshold)
        self.spin_threshold.setSuffix(" 次")
        form3.addRow("触发告警阈值(连续失败):", self.spin_threshold)

        alarm_group.setLayout(form3)
        layout.addWidget(alarm_group)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_ok = QPushButton("保存设置")
        btn_ok.setStyleSheet("background-color: #2563eb; color: white; padding: 6px 16px; border-radius: 4px; font-weight: bold;")
        btn_ok.clicked.connect(self.save_and_accept)
        btn_layout.addWidget(btn_ok)

        layout.addLayout(btn_layout)

    def save_and_accept(self):
        self.options.interval_sec = self.spin_interval.value()
        self.options.timeout_ms = self.spin_timeout.value()
        self.options.packet_size = self.spin_size.value()
        self.options.max_threads = self.spin_threads.value()
        self.options.limit_history_count = self.spin_history.value()
        self.options.alarm_on_fail = self.chk_alarm.isChecked()
        self.options.alarm_fail_threshold = self.spin_threshold.value()
        self.accept()
