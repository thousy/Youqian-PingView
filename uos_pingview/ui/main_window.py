"""
主窗体界面模块：双窗格架构 (上下分栏)
"""

import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict

from ..qt_compat import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView, QToolBar,
    QAction, QStatusBar, QLabel, QLineEdit, QComboBox,
    QMenu, QMessageBox, QFileDialog, QApplication, QAbstractItemView,
    Qt, Signal, QObject, QColor, QBrush, QFont, QTimer
)

from ..core.target_parser import TargetItem, parse_targets_text
from ..core.pinger import HostStat, PingRecord, PingOptions, PingWorker
from ..core.exporter import Exporter
from ..resources.icons import AppIcons
from .options_dialog import OptionsDialog
from .target_dialog import TargetDialog, SAMPLE_TEXT
from .properties_dialog import PropertiesDialog


class ProbeSignals(QObject):
    """用于后台工作线程向 Qt UI 主线程安全传递数据的信号集合"""
    single_result = Signal(int, bool, object, object, str, str)  # index, success, latency, ttl, status, resp_ip
    round_finished = Signal()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UOSPingView - 统信 UOS 批量网络探测监控工具")
        self.resize(1150, 720)

        # 核心数据
        self.options = PingOptions()
        self.hosts: List[HostStat] = []
        self.target_raw_text = SAMPLE_TEXT
        self.is_running = False
        self.selected_host_index: Optional[int] = None
        self.icons = AppIcons.get()

        # 线程与信号
        self.signals = ProbeSignals()
        self.signals.single_result.connect(self.on_single_probe_result)
        self.signals.round_finished.connect(self.on_round_finished)
        self.executor: Optional[ThreadPoolExecutor] = None

        # 轮询定时器
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.trigger_probe_round)

        # 倒计时显示定时器
        self.countdown_sec = 0
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self.update_countdown)

        self.init_ui()
        self.load_initial_targets(SAMPLE_TEXT)

    def init_ui(self):
        # 1. 菜单栏
        self.create_menu_bar()

        # 2. 工具栏
        self.create_tool_bar()

        # 3. 双窗格中心区域 (QSplitter 上下分栏)
        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.setHandleWidth(4)

        # 上窗格：主机监控总览表格
        self.upper_widget = QWidget()
        upper_layout = QVBoxLayout(self.upper_widget)
        upper_layout.setContentsMargins(4, 4, 4, 0)
        
        self.table_upper = QTableWidget()
        self.setup_upper_table()
        upper_layout.addWidget(self.table_upper)
        main_splitter.addWidget(self.upper_widget)

        # 下窗格：选定主机的历史流水明细表格
        self.lower_widget = QWidget()
        lower_layout = QVBoxLayout(self.lower_widget)
        lower_layout.setContentsMargins(4, 0, 4, 4)

        lower_header = QHBoxLayout()
        self.lbl_lower_title = QLabel("详细探测流水明细 (请在上表中点击选中某台主机)")
        self.lbl_lower_title.setStyleSheet("color: #475569; font-weight: bold; font-size: 12px; margin-top: 2px;")
        lower_header.addWidget(self.lbl_lower_title)
        lower_header.addStretch()
        lower_layout.addLayout(lower_header)

        self.table_lower = QTableWidget()
        self.setup_lower_table()
        lower_layout.addWidget(self.table_lower)
        main_splitter.addWidget(self.lower_widget)

        main_splitter.setStretchFactor(0, 7)
        main_splitter.setStretchFactor(1, 3)
        self.setCentralWidget(main_splitter)

        # 4. 状态栏
        self.create_status_bar()

    def create_menu_bar(self):
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        act_add = QAction("输入/编辑地址列表(&L)...", self)
        act_add.setShortcut("F8")
        act_add.triggered.connect(self.open_target_dialog)
        file_menu.addAction(act_add)

        act_options = QAction("Ping 选项设置(&O)...", self)
        act_options.setShortcut("F9")
        act_options.triggered.connect(self.open_options_dialog)
        file_menu.addAction(act_options)

        file_menu.addSeparator()

        act_copy = QAction("复制所选项目(&C)", self)
        act_copy.setShortcut("Ctrl+C")
        act_copy.triggered.connect(self.copy_selected_rows)
        file_menu.addAction(act_copy)

        act_props = QAction("属性(&P)...", self)
        act_props.setShortcut("Alt+Return")
        act_props.triggered.connect(self.show_selected_properties)
        file_menu.addAction(act_props)

        file_menu.addSeparator()

        act_export_html = QAction("导出 HTML 报告(&H)...", self)
        act_export_html.triggered.connect(lambda: self.export_report("html"))
        file_menu.addAction(act_export_html)

        act_export_csv = QAction("导出 CSV 表格(&C)...", self)
        act_export_csv.triggered.connect(lambda: self.export_report("csv"))
        file_menu.addAction(act_export_csv)

        file_menu.addSeparator()
        act_exit = QAction("退出(&X)", self)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # 控制菜单
        control_menu = menubar.addMenu("控制(&C)")
        self.act_start = QAction("开始 Ping(&S)", self)
        self.act_start.setIcon(self.icons.start)
        self.act_start.setShortcut("F5")
        self.act_start.triggered.connect(self.start_ping)
        control_menu.addAction(self.act_start)

        self.act_stop = QAction("停止 Ping(&T)", self)
        self.act_stop.setIcon(self.icons.stop)
        self.act_stop.setShortcut("F6")
        self.act_stop.setEnabled(False)
        self.act_stop.triggered.connect(self.stop_ping)
        control_menu.addAction(self.act_stop)

        act_refresh = QAction("立即刷新探测(&R)", self)
        act_refresh.setShortcut("Ctrl+R")
        act_refresh.triggered.connect(self.refresh_all_now)
        control_menu.addAction(act_refresh)

        act_reset = QAction("重置所有计数器(&Z)", self)
        act_reset.setIcon(self.icons.clear)
        act_reset.triggered.connect(self.reset_all_stats)
        control_menu.addAction(act_reset)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        act_about = QAction("关于 UOSPingView(&A)", self)
        act_about.triggered.connect(self.show_about)
        help_menu.addAction(act_about)

    def create_tool_bar(self):
        toolbar = QToolBar("主操作栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addAction(self.act_start)
        toolbar.addAction(self.act_stop)

        act_refresh = QAction(self.icons.clear, "刷新探测", self)
        act_refresh.setToolTip("立即执行新一轮探测并刷新大盘 (F5)")
        act_refresh.setShortcut("F5")
        act_refresh.triggered.connect(self.refresh_all_now)
        toolbar.addAction(act_refresh)

        act_reset = QAction(self.icons.clear, "重置统计", self)
        act_reset.triggered.connect(self.reset_all_stats)
        toolbar.addAction(act_reset)

        toolbar.addSeparator()

        act_targets = QAction(self.icons.add, "编辑目标列表", self)
        act_targets.triggered.connect(self.open_target_dialog)
        toolbar.addAction(act_targets)

        act_options = QAction(self.icons.settings, "探测设置", self)
        act_options.triggered.connect(self.open_options_dialog)
        toolbar.addAction(act_options)

        act_export = QAction(self.icons.export, "导出报表", self)
        act_export.triggered.connect(lambda: self.export_report("html"))
        toolbar.addAction(act_export)

        toolbar.addSeparator()

        lbl_filter = QLabel(" 筛选: ")
        toolbar.addWidget(lbl_filter)
        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["显示全部", "仅显示存活", "仅显示失败/异常"])
        self.combo_filter.currentIndexChanged.connect(self.apply_filter)
        toolbar.addWidget(self.combo_filter)

        lbl_search = QLabel("  搜索: ")
        toolbar.addWidget(lbl_search)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("过滤IP、主机或描述...")
        self.search_box.setMaximumWidth(180)
        self.search_box.textChanged.connect(self.apply_filter)
        toolbar.addWidget(self.search_box)

    def setup_upper_table(self):
        headers = [
            "状态", "序号", "目标", "解析IP", "最后状态", "成功", "失败",
            "失败率", "最后延迟", "平均延迟", "最小延迟", "最大延迟",
            "TTL", "连续失败", "最后成功时间", "描述"
        ]
        self.table_upper.setColumnCount(len(headers))
        self.table_upper.setHorizontalHeaderLabels(headers)
        self.table_upper.setSelectionBehavior(QAbstractItemView.SelectRows)
        # 支持按住 Ctrl 键跳选多项 (例如 1, 3, 5 行) 以及按住 Shift 键连续范围选择 (例如 2-5 行)
        self.table_upper.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_upper.setAlternatingRowColors(True)
        self.table_upper.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_upper.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_upper.customContextMenuRequested.connect(self.show_upper_context_menu)
        self.table_upper.itemSelectionChanged.connect(self.on_upper_selection_changed)
        self.table_upper.doubleClicked.connect(self.show_selected_properties)

        header = self.table_upper.horizontalHeader()
        # 允许每一列均可鼠标自由拖拽调整列宽
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)

        upper_widths = [45, 55, 140, 130, 85, 60, 60, 75, 85, 85, 70, 70, 65, 75, 160, 180]
        for col, w in enumerate(upper_widths):
            self.table_upper.setColumnWidth(col, w)

    def setup_lower_table(self):
        headers = ["序号", "探测时间", "探测目标", "响应IP", "耗时(ms)", "TTL", "结果状态"]
        self.table_lower.setColumnCount(len(headers))
        self.table_lower.setHorizontalHeaderLabels(headers)
        self.table_lower.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_lower.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_lower.setAlternatingRowColors(True)

        header = self.table_lower.horizontalHeader()
        # 允许所有列全部支持鼠标自由拖拽调整列宽！
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)

        # 初始默认列宽充足，确保探测时间 (2026-09-12 14:00:00) 完整显示绝不截断
        default_widths = [65, 165, 140, 140, 95, 75, 100]
        for col, w in enumerate(default_widths):
            self.table_lower.setColumnWidth(col, w)

    def create_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.lbl_status_mode = QLabel("状态: 空闲待命")
        self.lbl_status_count = QLabel("监控目标: 0 | 存活: 0 | 异常: 0")
        self.lbl_countdown = QLabel("下次探测: --")

        self.status_bar.addWidget(self.lbl_status_mode, 1)
        self.status_bar.addPermanentWidget(self.lbl_countdown)
        self.status_bar.addPermanentWidget(self.lbl_status_count)

    def load_initial_targets(self, text: str):
        self.target_raw_text = text
        items = parse_targets_text(text)
        self.hosts = []
        for idx, item in enumerate(items, start=1):
            stat = HostStat(idx, item.target, item.description, item.port)
            self.hosts.append(stat)
        self.refresh_upper_table_full()
        self.update_summary_status()

    def refresh_upper_table_full(self):
        self.table_upper.setRowCount(len(self.hosts))
        for row, host in enumerate(self.hosts):
            self.update_upper_table_row(row, host)
        self.apply_filter()

    def update_upper_table_row(self, row: int, host: HostStat):
        if not host.enabled:
            icon = self.icons.gray_light
        elif host.total_sent == 0:
            icon = self.icons.gray_light
        elif host.last_status in ("成功", "端口开放"):
            icon = self.icons.green_light
        else:
            icon = self.icons.red_light

        item_icon = QTableWidgetItem(icon, "")
        item_icon.setTextAlignment(Qt.AlignCenter)
        self.table_upper.setItem(row, 0, item_icon)

        target_display = f"{host.target}:{host.port}" if host.port else host.target
        col_values = [
            str(host.index),
            target_display,
            host.resolved_ip or "--",
            host.last_status,
            str(host.success_count),
            str(host.failed_count),
            f"{host.failure_rate:.1f}%",
            f"{host.last_latency_ms:.2f}" if host.last_latency_ms is not None else "--",
            f"{host.avg_latency_ms:.2f}" if host.avg_latency_ms is not None else "--",
            f"{host.min_latency_ms:.2f}" if host.min_latency_ms is not None else "--",
            f"{host.max_latency_ms:.2f}" if host.max_latency_ms is not None else "--",
            str(host.last_ttl) if host.last_ttl is not None else "--",
            str(host.consecutive_failures),
            host.last_success_time or "--",
            host.description or ""
        ]

        bg_color = None
        if host.total_sent > 0 and host.last_status not in ("成功", "端口开放"):
            bg_color = QColor("#fee2e2")

        for c_idx, val in enumerate(col_values, start=1):
            it = QTableWidgetItem(val)
            if bg_color:
                it.setBackground(QBrush(bg_color))
            if c_idx in (1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13):
                it.setTextAlignment(Qt.AlignCenter)
            self.table_upper.setItem(row, c_idx, it)

    def on_upper_selection_changed(self):
        selected_rows = self.table_upper.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        if 0 <= row < len(self.hosts):
            self.selected_host_index = row
            host = self.hosts[row]
            target_str = f"{host.target}:{host.port}" if host.port else host.target
            self.lbl_lower_title.setText(f"主机 [{target_str} ({host.description or '无描述'})] 探测流水记录 (共 {len(host.history_records)} 条)：")
            self.refresh_lower_table(host)

    def refresh_lower_table(self, host: HostStat):
        records = host.history_records
        self.table_lower.setRowCount(len(records))
        for row, rec in enumerate(reversed(records)):
            vals = [
                str(rec.sequence),
                rec.timestamp,
                rec.target,
                rec.resolved_ip or "--",
                f"{rec.latency_ms:.2f}" if rec.latency_ms is not None else "--",
                str(rec.ttl) if rec.ttl is not None else "--",
                rec.status
            ]
            bg_color = QColor("#fee2e2") if rec.status not in ("成功", "端口开放") else None
            for col, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if bg_color:
                    it.setBackground(QBrush(bg_color))
                it.setTextAlignment(Qt.AlignCenter)
                self.table_lower.setItem(row, col, it)

    def start_ping(self):
        if not self.hosts:
            QMessageBox.warning(self, "提示", "当前没有探测目标，请先添加目标！")
            return

        self.is_running = True
        self.act_start.setEnabled(False)
        self.act_stop.setEnabled(True)
        self.lbl_status_mode.setText("状态: 正在并发探测中...")
        self.trigger_probe_round()

    def stop_ping(self):
        self.is_running = False
        self.poll_timer.stop()
        self.countdown_timer.stop()
        self.act_start.setEnabled(True)
        self.act_stop.setEnabled(False)
        self.lbl_status_mode.setText("状态: 已停止")
        self.lbl_countdown.setText("下次探测: 已停止")

    def trigger_probe_round(self):
        if not self.is_running:
            return

        self.lbl_status_mode.setText("状态: 正在发送 Ping 探测包...")
        self.poll_timer.stop()
        self.countdown_timer.stop()

        timeout_ms = self.options.timeout_ms
        pkt_size = self.options.packet_size
        max_workers = min(self.options.max_threads, len(self.hosts) or 1)

        def worker_task(host_idx: int, host_stat: HostStat):
            if not host_stat.enabled:
                return
            is_succ, lat, ttl, status_str, resp_ip = PingWorker.probe(host_stat, timeout_ms, pkt_size)
            self.signals.single_result.emit(host_idx, is_succ, lat, ttl, status_str, resp_ip)

        def runner():
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = [pool.submit(worker_task, idx, h) for idx, h in enumerate(self.hosts)]
                for f in futures:
                    f.result()
            self.signals.round_finished.emit()

        import threading
        t = threading.Thread(target=runner, daemon=True)
        t.start()

    def on_single_probe_result(self, index: int, is_success: bool, latency: Optional[float],
                               ttl: Optional[int], status_msg: str, resolved_ip: str):
        if 0 <= index < len(self.hosts):
            host = self.hosts[index]
            host.update_result(is_success, latency, ttl, status_msg, resolved_ip)
            self.update_upper_table_row(index, host)

            # 核心特性：动态更新单行可见性！在“显示失败”视图下，一旦有新失败项，立即毫秒级弹现在页面上！
            self.update_row_visibility(index, host)

            if self.selected_host_index == index:
                self.refresh_lower_table(host)

            if not is_success and self.options.alarm_on_fail:
                if host.consecutive_failures == self.options.alarm_fail_threshold:
                    QApplication.beep()

    def on_round_finished(self):
        self.update_summary_status()
        self.apply_filter()
        if self.is_running:
            self.lbl_status_mode.setText("状态: 本轮探测完成，等待下一轮")
            self.countdown_sec = self.options.interval_sec
            self.update_countdown()
            self.countdown_timer.start(1000)
            self.poll_timer.start(self.options.interval_sec * 1000)

    def update_countdown(self):
        if self.countdown_sec > 0:
            self.lbl_countdown.setText(f"下次探测: {self.countdown_sec} 秒后")
            self.countdown_sec -= 1
        else:
            self.lbl_countdown.setText("下次探测: 正在准备...")

    def update_summary_status(self):
        total = len(self.hosts)
        alive = sum(1 for h in self.hosts if h.last_status in ("成功", "端口开放"))
        down = sum(1 for h in self.hosts if h.total_sent > 0 and h.last_status not in ("成功", "端口开放"))
        self.lbl_status_count.setText(f"监控目标: {total} | 存活: {alive} | 异常: {down}")

    def update_row_visibility(self, row: int, host: HostStat):
        """根据当前筛选模式，动态更新单行的显示/隐藏状态 (新失败项实时呈现)"""
        search_kw = self.search_box.text().strip().lower()
        filter_mode = self.combo_filter.currentIndex()  # 0: 全部, 1: 存活, 2: 异常/失败

        match_search = True
        if search_kw:
            combined_str = f"{host.target} {host.resolved_ip} {host.description}".lower()
            if search_kw not in combined_str:
                match_search = False

        match_status = True
        if not host.enabled:
            if filter_mode in (1, 2):
                match_status = False
        else:
            if filter_mode == 1:
                match_status = (host.last_status in ("成功", "端口开放"))
            elif filter_mode == 2:
                # 若探测失败或超时，在“仅显示失败”模式下立即匹配显示
                match_status = (host.total_sent > 0 and host.last_status not in ("成功", "端口开放"))

        self.table_upper.setRowHidden(row, not (match_search and match_status))

    def apply_filter(self):
        """批量更新所有行的显示与隐藏"""
        for row, host in enumerate(self.hosts):
            self.update_row_visibility(row, host)

    def show_upper_context_menu(self, pos):
        selected_indexes = self.table_upper.selectionModel().selectedRows()
        if not selected_indexes:
            return

        menu = QMenu(self)

        # 1. 复制所选项目 (支持 Ctrl/Shift 选中的单行或多行，带表头)
        act_copy_selected = menu.addAction(f"复制选择的项目 (&C) [{len(selected_indexes)} 项]")
        act_copy_selected.setShortcut("Ctrl+C")
        act_copy_selected.triggered.connect(self.copy_selected_rows)

        act_copy_cell = menu.addAction("复制单元格内容")
        item = self.table_upper.itemAt(pos)
        if item:
            act_copy_cell.triggered.connect(lambda: QApplication.clipboard().setText(item.text()))
        else:
            act_copy_cell.setEnabled(False)

        menu.addSeparator()

        # 2. 启用/禁用探测 (支持批量)
        first_row = selected_indexes[0].row()
        first_host = self.hosts[first_row]
        enable_text = "禁用所选项目 (从失败列表中隐藏)" if first_host.enabled else "启用所选项目"
        act_toggle = menu.addAction(enable_text)
        act_toggle.triggered.connect(self.toggle_selected_hosts)

        # 3. 刷新/立即探测
        act_refresh_sel = menu.addAction("刷新所选项目 (立即探测)")
        act_refresh_sel.setShortcut("F5")
        act_refresh_sel.triggered.connect(self.refresh_selected_hosts)

        menu.addSeparator()

        # 4. 属性 (完全对标原版 PingInfoView 经典属性界面)
        act_props = menu.addAction("属性 (&P)...")
        act_props.setShortcut("Alt+Return")
        act_props.triggered.connect(self.show_selected_properties)

        menu.exec_(self.table_upper.viewport().mapToGlobal(pos))

    def copy_selected_rows(self):
        """
        复制用户通过鼠标、Ctrl键或Shift键选中的所有整行数据
        输出规则：第1行为表头标题字段，第2行及后续行依次为选中项的数据行
        """
        selected_indexes = self.table_upper.selectionModel().selectedRows()
        if not selected_indexes:
            return

        # 获取选中的所有行号并进行升序排序 (例如 1, 3, 5 或 2, 3, 4, 5)
        selected_rows = sorted([idx.row() for idx in selected_indexes])

        # 第 1 行：表头标题字段 (Tab 制表符分隔)
        headers = [
            "序号", "目标", "解析IP", "最后状态", "成功次数", "失败次数",
            "失败率(%)", "最后延迟(ms)", "平均延迟(ms)", "最小延迟(ms)", "最大延迟(ms)",
            "TTL", "连续失败", "最后成功时间", "描述"
        ]
        output_lines = ["\t".join(headers)]

        # 第 2 行及后续行：具体数据行
        for r in selected_rows:
            if 0 <= r < len(self.hosts):
                h = self.hosts[r]
                row_data = [
                    str(h.index),
                    f"{h.target}:{h.port}" if h.port else h.target,
                    h.resolved_ip or "--",
                    h.last_status,
                    str(h.success_count),
                    str(h.failed_count),
                    f"{h.failure_rate:.1f}%",
                    f"{h.last_latency_ms:.3f}" if h.last_latency_ms is not None else "--",
                    f"{h.avg_latency_ms:.3f}" if h.avg_latency_ms is not None else "--",
                    f"{h.min_latency_ms:.3f}" if h.min_latency_ms is not None else "--",
                    f"{h.max_latency_ms:.3f}" if h.max_latency_ms is not None else "--",
                    str(h.last_ttl) if h.last_ttl is not None else "--",
                    str(h.consecutive_failures),
                    h.last_success_time or "--",
                    h.description or ""
                ]
                output_lines.append("\t".join(row_data))

        final_text = "\n".join(output_lines)
        QApplication.clipboard().setText(final_text)

    def show_selected_properties(self):
        """打开原版 1:1 经典属性对话框"""
        selected_indexes = self.table_upper.selectionModel().selectedRows()
        if not selected_indexes:
            return
        row = selected_indexes[0].row()
        if 0 <= row < len(self.hosts):
            host = self.hosts[row]
            dlg = PropertiesDialog(host, self)
            dlg.exec_()

    def toggle_selected_hosts(self):
        """批量切换选中项的启用/禁用状态"""
        selected_indexes = self.table_upper.selectionModel().selectedRows()
        if not selected_indexes:
            return
        target_state = None
        for idx in selected_indexes:
            r = idx.row()
            if 0 <= r < len(self.hosts):
                if target_state is None:
                    target_state = not self.hosts[r].enabled
                self.hosts[r].enabled = target_state
                self.update_upper_table_row(r, self.hosts[r])
        self.apply_filter()

    def refresh_selected_hosts(self):
        """立即刷新/探测当前选中的项目"""
        selected_indexes = self.table_upper.selectionModel().selectedRows()
        if not selected_indexes:
            # 若未选中特定项，则刷新全局
            self.refresh_all_now()
            return

        timeout_ms = self.options.timeout_ms
        pkt_size = self.options.packet_size
        rows_to_probe = [idx.row() for idx in selected_indexes]

        def do_probe_batch():
            for r in rows_to_probe:
                if 0 <= r < len(self.hosts):
                    h = self.hosts[r]
                    if h.enabled:
                        succ, lat, ttl, status_str, resp_ip = PingWorker.probe(h, timeout_ms, pkt_size)
                        self.signals.single_result.emit(r, succ, lat, ttl, status_str, resp_ip)

        import threading
        threading.Thread(target=do_probe_batch, daemon=True).start()

    def refresh_all_now(self):
        """全局刷新：立即发出一轮完整的并发探测"""
        self.lbl_status_mode.setText("状态: 正在手动触发刷新探测...")
        self.trigger_probe_round()

    def reset_all_stats(self):
        for h in self.hosts:
            h.reset_stats()
        self.refresh_upper_table_full()
        self.table_lower.setRowCount(0)
        self.update_summary_status()

    def open_target_dialog(self):
        was_running = self.is_running
        if was_running:
            self.stop_ping()

        dlg = TargetDialog(self.target_raw_text, self)
        if dlg.exec_():
            self.target_raw_text = dlg.get_text()
            self.load_initial_targets(self.target_raw_text)

        if was_running:
            self.start_ping()

    def open_options_dialog(self):
        dlg = OptionsDialog(self.options, self)
        if dlg.exec_():
            for h in self.hosts:
                h.max_history = self.options.limit_history_count

    def export_report(self, file_type: str = "html"):
        if not self.hosts:
            QMessageBox.warning(self, "提示", "当前无监控数据可导出！")
            return

        if file_type == "html":
            file_path, _ = QFileDialog.getSaveFileName(self, "保存 HTML 监控报表", "PingReport.html", "HTML 网页 (*.html)")
            if file_path:
                try:
                    Exporter.export_html(self.hosts, file_path)
                    QMessageBox.information(self, "成功", f"监控报表已成功导出至：\n{file_path}")
                except Exception as e:
                    QMessageBox.critical(self, "导出失败", f"生成 HTML 失败: {e}")

        elif file_type == "csv":
            file_path, _ = QFileDialog.getSaveFileName(self, "保存 CSV 表格", "PingReport.csv", "CSV 文件 (*.csv)")
            if file_path:
                try:
                    Exporter.export_csv(self.hosts, file_path)
                    QMessageBox.information(self, "成功", f"表格数据已成功导出至：\n{file_path}")
                except Exception as e:
                    QMessageBox.critical(self, "导出失败", f"生成 CSV 失败: {e}")

    def show_about(self):
        about_text = (
            "<h2 style='color:#2563eb; margin-bottom:4px;'>Youqian PingView v1.0.2</h2>"
            "<p style='color:#64748b; font-size:12px;'>专为统信 UOS Desktop 与 Linux 深度定制的原生批量网络监控工具</p>"
            "<hr style='border:none; border-top:1px solid #e2e8f0;'/>"
            "<p><b>🌟 核心亮点：</b></p>"
            "<ul style='margin-left: -15px;'>"
            "<li><b>双引擎保障</b>：PyQt5 现代大盘 + Python 原生零依赖引擎，未激活/离线环境秒开；</li>"
            "<li><b>100% 原生 IPv6 支持</b>：识别 IPv6 单目标、TCP 端口探测与 HLIM 跳数抓取；</li>"
            "<li><b>经典双窗格与交互</b>：支持 Ctrl/Shift 连选跳选、带表头复制、列宽自由拖拽；</li>"
            "<li><b>活动故障实时呈现</b>：在失败视图下，新故障主机秒级自动在大盘弹出；</li>"
            "<li><b>1:1 原版属性面板</b>：双击或右键属性随时查看 20+ 项网络统计指标。</li>"
            "</ul>"
            "<p><b>开源仓库：</b><a href='https://github.com/thousy/Youqian-PingView'>https://github.com/thousy/Youqian-PingView</a></p>"
            "<p style='color:#94a3b8; font-size:11px;'>作者：MoMo (ThousyMo) · 基于 MIT 开源协议发布 · 致敬 NirSoft PingInfoView</p>"
        )
        QMessageBox.about(self, "关于 Youqian PingView", about_text)
