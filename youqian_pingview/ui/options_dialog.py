# -*- coding: utf-8 -*-
"""
Ping 探测选项与参数配置对话框 (1:1 深度还原原版 PingInfoView 原型)
"""

try:
    from youqian_pingview.qt_compat import (
        QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
        QSpinBox, QComboBox, QCheckBox, QLineEdit, QPushButton,
        QWidget, Qt
    )
    from youqian_pingview.core.pinger import PingOptions
    from youqian_pingview.core.config_manager import get_local_ip_addresses
except (ImportError, ModuleNotFoundError, ValueError):
    from qt_compat import (
        QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
        QSpinBox, QComboBox, QCheckBox, QLineEdit, QPushButton,
        QWidget, Qt
    )
    from core.pinger import PingOptions
    from core.config_manager import get_local_ip_addresses


class OptionsDialog(QDialog):
    def __init__(self, options: PingOptions, parent=None):
        super().__init__(parent)
        self.options = options
        self.start_requested = False  # 是否点击了"开始"按钮
        self.setWindowTitle("Ping 选项设置")
        self.setMinimumWidth(560)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        grid = QGridLayout()
        grid.setVerticalSpacing(10)
        grid.setHorizontalSpacing(12)
        row = 0

        # 行 0: Ping 超时 (毫秒) 与 Ping 大小 (字节)
        lbl_timeout = QLabel("Ping 超时(毫秒):")
        self.combo_timeout = QComboBox()
        self.combo_timeout.setEditable(True)
        for t in ["500", "1000", "2000", "3000", "5000", "10000"]:
            self.combo_timeout.addItem(t)
        self.combo_timeout.setCurrentText(str(self.options.timeout_ms))
        grid.addWidget(lbl_timeout, row, 0)
        grid.addWidget(self.combo_timeout, row, 1)

        lbl_size = QLabel("Ping 大小(字节):")
        self.spin_size = QSpinBox()
        self.spin_size.setRange(16, 65500)
        self.spin_size.setValue(self.options.packet_size)
        grid.addWidget(lbl_size, row, 2)
        grid.addWidget(self.spin_size, row, 3)
        row += 1

        # 行 1: [√] 重复间隔... [数值] 秒
        self.chk_repeat = QCheckBox("重复间隔...")
        self.chk_repeat.setChecked(self.options.auto_repeat)
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 3600)
        self.spin_interval.setValue(self.options.interval_sec)
        lbl_sec = QLabel("秒")

        repeat_layout = QHBoxLayout()
        repeat_layout.addWidget(self.chk_repeat)
        repeat_layout.addWidget(self.spin_interval)
        repeat_layout.addWidget(lbl_sec)
        repeat_layout.addStretch()
        grid.addLayout(repeat_layout, row, 0, 1, 4)
        self.chk_repeat.toggled.connect(self.spin_interval.setEnabled)
        self.spin_interval.setEnabled(self.options.auto_repeat)
        row += 1

        # 行 2: [√] 记住地址列表
        self.chk_remember = QCheckBox("记住地址列表")
        self.chk_remember.setChecked(self.options.remember_targets)
        grid.addWidget(self.chk_remember, row, 0, 1, 4)
        row += 1

        # 行 3: [ ] 使用 IP-Host 描述格式
        self.chk_ip_host = QCheckBox("使用 IP-Host 描述格式")
        self.chk_ip_host.setChecked(self.options.use_ip_host_format)
        grid.addWidget(self.chk_ip_host, row, 0, 1, 4)
        row += 1

        # 行 4: [ ] 不显示对话框立刻开始 Pinging
        self.chk_autostart = QCheckBox("不显示对话框立刻开始 Pinging")
        self.chk_autostart.setChecked(self.options.auto_start_ping)
        grid.addWidget(self.chk_autostart, row, 0, 1, 4)
        row += 1

        # 行 5: [ ] 每次 ping 时解析主机名为IP地址
        self.chk_resolve_dns = QCheckBox("每次 ping 时解析主机名为IP地址")
        self.chk_resolve_dns.setChecked(self.options.resolve_dns_every_ping)
        grid.addWidget(self.chk_resolve_dns, row, 0, 1, 4)
        row += 1

        # 行 5b: [√] 解析 IP 地址为主机名 (反向 DNS / NetBIOS)
        self.chk_resolve_addr = QCheckBox("解析 IP 地址为主机名 (反向 DNS / 局域网 NetBIOS)")
        self.chk_resolve_addr.setChecked(getattr(self.options, "resolve_addresses", True))
        grid.addWidget(self.chk_resolve_addr, row, 0, 1, 4)
        row += 1

        # 行 6: [ ] IP 选项: 有效时间: [64]  [ ] 禁止分段
        self.chk_ip_opts = QCheckBox("IP 选项:")
        self.chk_ip_opts.setChecked(self.options.custom_ttl_enabled)
        lbl_ttl = QLabel("有效时间:")
        self.spin_ttl = QSpinBox()
        self.spin_ttl.setRange(1, 255)
        self.spin_ttl.setValue(self.options.custom_ttl)
        self.chk_df = QCheckBox("禁止分段")
        self.chk_df.setChecked(self.options.dont_fragment)

        ip_opts_layout = QHBoxLayout()
        ip_opts_layout.addWidget(self.chk_ip_opts)
        ip_opts_layout.addWidget(lbl_ttl)
        ip_opts_layout.addWidget(self.spin_ttl)
        ip_opts_layout.addSpacing(16)
        ip_opts_layout.addWidget(self.chk_df)
        ip_opts_layout.addStretch()
        grid.addLayout(ip_opts_layout, row, 0, 1, 4)

        def update_ip_opts_state(enabled):
            self.spin_ttl.setEnabled(enabled)
            self.chk_df.setEnabled(enabled)
        self.chk_ip_opts.toggled.connect(update_ip_opts_state)
        update_ip_opts_state(self.options.custom_ttl_enabled)
        row += 1

        # 行 7: 指定 CIDR 时: [ ] 跳过第一个地址  [√] 跳过最后一个地址
        lbl_cidr = QLabel("指定 CIDR 时:")
        self.chk_skip_first = QCheckBox("跳过第一个地址")
        self.chk_skip_first.setChecked(self.options.cidr_skip_first)
        self.chk_skip_last = QCheckBox("跳过最后一个地址")
        self.chk_skip_last.setChecked(self.options.cidr_skip_last)

        cidr_layout = QHBoxLayout()
        cidr_layout.addWidget(lbl_cidr)
        cidr_layout.addSpacing(12)
        cidr_layout.addWidget(self.chk_skip_first)
        cidr_layout.addSpacing(16)
        cidr_layout.addWidget(self.chk_skip_last)
        cidr_layout.addStretch()
        grid.addLayout(cidr_layout, row, 0, 1, 4)
        row += 1

        # 行 8: 窗口标题: [编辑框]
        lbl_wintitle = QLabel("窗口标题:")
        self.txt_wintitle = QLineEdit()
        self.txt_wintitle.setPlaceholderText("留空为默认系统窗口标题")
        self.txt_wintitle.setText(self.options.custom_window_title)
        grid.addWidget(lbl_wintitle, row, 0)
        grid.addWidget(self.txt_wintitle, row, 1, 1, 3)
        row += 1

        # 获取本机 IPv4 与 IPv6 列表
        ipv4_list, ipv6_list = get_local_ip_addresses()

        # 行 9: 源IPv4地址: [下拉框]
        lbl_src_v4 = QLabel("源IPv4地址:")
        self.combo_src_v4 = QComboBox()
        for ip in ipv4_list:
            self.combo_src_v4.addItem(ip)
        if self.options.source_ipv4 and self.options.source_ipv4 in ipv4_list:
            self.combo_src_v4.setCurrentText(self.options.source_ipv4)
        grid.addWidget(lbl_src_v4, row, 0)
        grid.addWidget(self.combo_src_v4, row, 1, 1, 3)
        row += 1

        # 行 10: [√] 允许 IPv6 地址
        self.chk_allow_v6 = QCheckBox("允许 IPv6 地址")
        self.chk_allow_v6.setChecked(self.options.allow_ipv6)
        grid.addWidget(self.chk_allow_v6, row, 0, 1, 4)
        row += 1

        # 行 11: 源地址 (可选): [下拉框]
        lbl_src_v6 = QLabel("源地址 (可选):")
        self.combo_src_v6 = QComboBox()
        for ip in ipv6_list:
            self.combo_src_v6.addItem(ip)
        if self.options.source_ipv6 and self.options.source_ipv6 in ipv6_list:
            self.combo_src_v6.setCurrentText(self.options.source_ipv6)
        grid.addWidget(lbl_src_v6, row, 0)
        grid.addWidget(self.combo_src_v6, row, 1, 1, 3)

        self.chk_allow_v6.toggled.connect(self.combo_src_v6.setEnabled)
        self.combo_src_v6.setEnabled(self.options.allow_ipv6)
        row += 1

        main_layout.addLayout(grid)

        # 底部按钮区: [更新设置]  [高级选项...]               [开始]  [取消]
        btn_layout = QHBoxLayout()
        btn_update = QPushButton("更新设置")
        btn_update.clicked.connect(self.on_update_settings)
        btn_layout.addWidget(btn_update)

        btn_adv = QPushButton("高级选项(&A)...")
        btn_adv.setToolTip("打开高级选项配置 (并发数量、声音报警、命令触发、下窗格与日志导出)")
        btn_adv.clicked.connect(self.open_advanced_options)
        btn_layout.addWidget(btn_adv)

        btn_layout.addStretch()

        btn_start = QPushButton("开始")
        btn_start.setStyleSheet("font-weight: bold; padding: 5px 16px;")
        btn_start.clicked.connect(self.on_start_clicked)
        btn_layout.addWidget(btn_start)

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        main_layout.addLayout(btn_layout)

    def open_advanced_options(self):
        try:
            from youqian_pingview.ui.advanced_options_dialog import AdvancedOptionsDialog
        except ImportError:
            from ui.advanced_options_dialog import AdvancedOptionsDialog
        dlg = AdvancedOptionsDialog(self.options, self)
        dlg.exec_()

    def _sync_to_options(self):
        """将界面各组件的值同步到 options 实体"""
        try:
            self.options.timeout_ms = int(self.combo_timeout.currentText().strip())
        except ValueError:
            self.options.timeout_ms = 1000

        self.options.packet_size = self.spin_size.value()
        self.options.auto_repeat = self.chk_repeat.isChecked()
        self.options.interval_sec = self.spin_interval.value()
        self.options.remember_targets = self.chk_remember.isChecked()
        self.options.use_ip_host_format = self.chk_ip_host.isChecked()
        self.options.auto_start_ping = self.chk_autostart.isChecked()
        self.options.resolve_dns_every_ping = self.chk_resolve_dns.isChecked()
        self.options.resolve_addresses = self.chk_resolve_addr.isChecked()
        self.options.custom_ttl_enabled = self.chk_ip_opts.isChecked()
        self.options.custom_ttl = self.spin_ttl.value()
        self.options.dont_fragment = self.chk_df.isChecked()
        self.options.cidr_skip_first = self.chk_skip_first.isChecked()
        self.options.cidr_skip_last = self.chk_skip_last.isChecked()
        self.options.custom_window_title = self.txt_wintitle.text().strip()

        v4_text = self.combo_src_v4.currentText().strip()
        self.options.source_ipv4 = "" if v4_text.startswith("(") else v4_text

        self.options.allow_ipv6 = self.chk_allow_v6.isChecked()
        v6_text = self.combo_src_v6.currentText().strip()
        self.options.source_ipv6 = "" if v6_text.startswith("(") else v6_text

    def on_update_settings(self):
        """保存设置并关闭对话框"""
        self._sync_to_options()
        self.start_requested = False
        self.accept()

    def on_start_clicked(self):
        """保存设置并请求立即开始探测"""
        self._sync_to_options()
        self.start_requested = True
        self.accept()
