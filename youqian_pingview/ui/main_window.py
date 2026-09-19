"""
主窗体界面模块：双窗格架构 (上下分栏)
"""

import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict

try:
    from youqian_pingview.qt_compat import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
        QTableWidget, QTableWidgetItem, QHeaderView, QToolBar,
        QAction, QStatusBar, QLabel, QLineEdit, QComboBox,
        QMenu, QMessageBox, QFileDialog, QApplication, QAbstractItemView,
        Qt, Signal, QObject, QColor, QBrush, QFont, QTimer, QPoint, QCursor,
        QFontDialog, QSystemTrayIcon, QActionGroup
    )
    from youqian_pingview.core.target_parser import TargetItem, parse_targets_text
    from youqian_pingview.core.pinger import HostStat, PingRecord, PingOptions, PingWorker, resolve_host_name
    from youqian_pingview.core.constants import WINDOW_TITLE, SAMPLE_TEXT, APP_VERSION
    from youqian_pingview.core.exporter import Exporter
    from youqian_pingview.core.config_manager import ConfigManager
    from youqian_pingview.resources.icons import AppIcons
    from youqian_pingview.ui.options_dialog import OptionsDialog
    from youqian_pingview.ui.target_dialog import TargetDialog
    from youqian_pingview.ui.properties_dialog import PropertiesDialog
    from youqian_pingview.ui.advanced_options_dialog import AdvancedOptionsDialog
    from youqian_pingview.core.alert_manager import AlertManager
except (ImportError, ModuleNotFoundError, ValueError):
    from qt_compat import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
        QTableWidget, QTableWidgetItem, QHeaderView, QToolBar,
        QAction, QStatusBar, QLabel, QLineEdit, QComboBox,
        QMenu, QMessageBox, QFileDialog, QApplication, QAbstractItemView,
        Qt, Signal, QObject, QColor, QBrush, QFont, QTimer, QPoint, QCursor,
        QFontDialog, QSystemTrayIcon, QActionGroup
    )
    from core.target_parser import TargetItem, parse_targets_text
    from core.pinger import HostStat, PingRecord, PingOptions, PingWorker, resolve_host_name
    from core.constants import WINDOW_TITLE, SAMPLE_TEXT, APP_VERSION
    from core.exporter import Exporter
    from core.config_manager import ConfigManager
    from resources.icons import AppIcons
    from ui.options_dialog import OptionsDialog
    from ui.target_dialog import TargetDialog
    from ui.properties_dialog import PropertiesDialog
    from ui.advanced_options_dialog import AdvancedOptionsDialog
    from core.alert_manager import AlertManager

# 完整对标原版 PingInfoView 22 列大盘指标定义 (第 0 列为状态灯图标)
UPPER_COLUMNS = [
    "", "序号", "主机名", "IP 地址", "响应 IP 地址", "成功次数", "失败次数",
    "连续失败次数", "最大连续失败次数", "最大连续失败时间", "失败率(%)",
    "总计发送Pings数", "最后 Ping 状态", "最后 Ping 时间", "最后 Ping TTL",
    "平均 Ping 时间", "描述", "最后成功时间", "最后失败时间", "最小Ping时间",
    "最大Ping时间", "禁用", "MAC 地址"
]

# 对标原版下窗格流水记录表头
LOWER_COLUMNS = ["发送时间", "响应 IP 地址", "Ping 时间", "Ping 衰减", "Ping 状态", "Ping 计数"]


class ProbeSignals(QObject):
    """用于后台工作线程向 Qt UI 主线程安全传递数据的信号集合"""
    single_result = Signal(int, str, bool, object, object, str, str)  # round_id, host_id, success, latency, ttl, status, resp_ip
    round_finished = Signal(int)  # round_id
    hostname_resolved = Signal(str, str)  # host_id, hostname


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1150, 720)

        # 1. 加载持久化配置与选项
        self.saved_cfg = ConfigManager.load_config()
        self.options = PingOptions.from_dict(self.saved_cfg.get("options", {}))
        self.hidden_columns: List[str] = self.saved_cfg.get("hidden_columns", [])

        # 2. 恢复目标地址列表
        if self.options.remember_targets and self.saved_cfg.get("targets_text"):
            self.target_raw_text = self.saved_cfg.get("targets_text")
        else:
            self.target_raw_text = SAMPLE_TEXT

        # 3. 动态更新窗口标题
        self.update_window_title()

        # 核心数据
        self.hosts: List[HostStat] = []
        self.is_running = False
        self.current_round_id: int = 0
        self.is_probing_round_active: bool = False
        self.selected_host_index: Optional[int] = None
        self.icons = AppIcons.get()
        self.current_sort_col: Optional[int] = None
        self.current_sort_desc: bool = False
        self.lower_sort_col: Optional[int] = None
        self.lower_sort_desc: bool = False

        # 分组与折叠状态
        self.collapsed_groups: set = set()
        self.host_to_row: Dict[str, int] = {}
        self.row_to_host: Dict[int, HostStat] = {}
        self.row_to_group: Dict[int, str] = {}
        self.group_to_header_row: Dict[str, int] = {}

        # 线程与信号
        self.signals = ProbeSignals()
        self.signals.single_result.connect(self.on_single_probe_result)
        self.signals.round_finished.connect(self.on_round_finished)
        self.signals.hostname_resolved.connect(self.on_hostname_resolved)
        self.executor: Optional[ThreadPoolExecutor] = None

        # 轮询定时器
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.trigger_probe_round)

        # 倒计时显示定时器
        self.countdown_sec = 0
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self.update_countdown)

        # 下窗格流水自动定时导出定时器
        self.auto_export_timer = QTimer(self)
        self.auto_export_timer.timeout.connect(self.on_auto_export_timer)
        self.last_exported_content = ""
        self.export_file_counter = 1

        self.init_ui()
        self.load_initial_targets(self.target_raw_text)

        # 若开启了“不显示对话框立刻开始 Pinging”，延时 200ms 自动开启监控
        if self.options.auto_start_ping and self.hosts:
            QTimer.singleShot(200, self.start_ping)

    def update_window_title(self):
        """根据是否配置自定义业务标题动态设置窗口标题"""
        if self.options.custom_window_title:
            self.setWindowTitle(f"{self.options.custom_window_title} - {WINDOW_TITLE}")
        else:
            self.setWindowTitle(WINDOW_TITLE)

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

        # 5. 根据偏好设置应用初始窗口置顶与下窗格显隐
        if self.options.always_on_top:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.lower_widget.setVisible(self.options.show_lower_pane)

        # 6. 自定义字体应用
        if self.options.custom_font_family:
            try:
                custom_font = QFont(self.options.custom_font_family, self.options.custom_font_size)
                self.apply_custom_font(custom_font)
            except Exception:
                pass

        # 7. 系统托盘初始化
        self.setup_tray_icon()

    def create_menu_bar(self):
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        act_add = QAction("输入/编辑地址列表(&L)...", self)
        act_add.setShortcut("F8")
        act_add.triggered.connect(self.open_target_dialog)
        file_menu.addAction(act_add)

        act_options = QAction("Ping 选项设置(&O)...", self)
        act_options.setShortcut("F10")
        act_options.triggered.connect(self.open_options_dialog)
        file_menu.addAction(act_options)

        act_adv_file = QAction("高级选项(&A)...", self)
        act_adv_file.setShortcut("F9")
        act_adv_file.triggered.connect(self.open_advanced_options_dialog)
        file_menu.addAction(act_adv_file)

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

        # 查看菜单 (对标原版选择列功能)
        view_menu = menubar.addMenu("查看(&V)")
        act_choose_cols = QAction("选择列(&C)...", self)
        act_choose_cols.setToolTip("选择或隐藏大盘表格中展示的列字段")
        act_choose_cols.triggered.connect(lambda: self.show_column_select_menu())
        view_menu.addAction(act_choose_cols)

        act_sort_menu = QAction("排序选项(&S)...", self)
        act_sort_menu.setToolTip("选择排序列或切换升降序")
        act_sort_menu.triggered.connect(self.show_sort_menu)
        view_menu.addAction(act_sort_menu)

        view_menu.addSeparator()

        act_expand_all = QAction("展开所有分组(&E)", self)
        act_expand_all.setShortcut("Ctrl+Shift+E")
        act_expand_all.triggered.connect(self.expand_all_groups)
        view_menu.addAction(act_expand_all)

        act_collapse_all = QAction("折叠所有分组(&F)", self)
        act_collapse_all.setShortcut("Ctrl+Shift+C")
        act_collapse_all.triggered.connect(self.collapse_all_groups)
        view_menu.addAction(act_collapse_all)

        # 选项菜单 (1:1 像素级还原原版 Options 菜单体系)
        options_menu = menubar.addMenu("选项(&O)")

        # 1. 显示模式 (二级单选互斥子菜单)
        display_mode_menu = options_menu.addMenu("显示模式(&D)")
        mode_group = QActionGroup(self)
        mode_group.setExclusive(True)

        self.act_mode_all = QAction("显示所有 Hosts", self)
        self.act_mode_all.setCheckable(True)
        self.act_mode_all.setChecked(self.options.display_mode == "显示所有 Hosts")
        self.act_mode_all.triggered.connect(lambda: self.set_display_mode("显示所有 Hosts"))
        mode_group.addAction(self.act_mode_all)
        display_mode_menu.addAction(self.act_mode_all)

        self.act_mode_failed = QAction("仅显示失败的 Hosts", self)
        self.act_mode_failed.setCheckable(True)
        self.act_mode_failed.setChecked(self.options.display_mode == "仅显示失败的 Hosts")
        self.act_mode_failed.triggered.connect(lambda: self.set_display_mode("仅显示失败的 Hosts"))
        mode_group.addAction(self.act_mode_failed)
        display_mode_menu.addAction(self.act_mode_failed)

        self.act_mode_succ = QAction("仅显示成功的 Hosts", self)
        self.act_mode_succ.setCheckable(True)
        self.act_mode_succ.setChecked(self.options.display_mode == "仅显示成功的 Hosts")
        self.act_mode_succ.triggered.connect(lambda: self.set_display_mode("仅显示成功的 Hosts"))
        mode_group.addAction(self.act_mode_succ)
        display_mode_menu.addAction(self.act_mode_succ)

        # 2. 高分辨率 ping 时间
        self.act_high_res = QAction("高分辨率 ping 时间", self)
        self.act_high_res.setCheckable(True)
        self.act_high_res.setChecked(self.options.high_resolution_timer)
        self.act_high_res.toggled.connect(self.toggle_high_resolution_timer)
        options_menu.addAction(self.act_high_res)

        # 3. 以 GMT 格式显示时间(G)
        self.act_gmt_time = QAction("以 GMT 格式显示时间(&G)", self)
        self.act_gmt_time.setCheckable(True)
        self.act_gmt_time.setChecked(self.options.show_gmt_time)
        self.act_gmt_time.toggled.connect(self.toggle_gmt_time)
        options_menu.addAction(self.act_gmt_time)

        # 4. 标记失败 Pings(F)
        self.act_mark_failed = QAction("标记失败 Pings(&F)", self)
        self.act_mark_failed.setCheckable(True)
        self.act_mark_failed.setChecked(self.options.mark_failed_pings)
        self.act_mark_failed.toggled.connect(self.toggle_mark_failed_pings)
        options_menu.addAction(self.act_mark_failed)

        # 5. 总在最前(T)
        self.act_always_top = QAction("总在最前(&T)", self)
        self.act_always_top.setCheckable(True)
        self.act_always_top.setChecked(self.options.always_on_top)
        self.act_always_top.toggled.connect(self.toggle_always_on_top)
        options_menu.addAction(self.act_always_top)

        options_menu.addSeparator()

        # 6. 当 Ping 失败时发出哔声(B)
        self.act_beep_failed = QAction("当 Ping 失败时发出哔声(&B)", self)
        self.act_beep_failed.setCheckable(True)
        self.act_beep_failed.setChecked(self.options.beep_on_failed)
        self.act_beep_failed.toggled.connect(self.toggle_beep_on_failed)
        options_menu.addAction(self.act_beep_failed)

        # 7. 成功 ping 时发出蜂鸣音(失败后)
        self.act_beep_succ = QAction("成功 ping 时发出蜂鸣音(失败后)", self)
        self.act_beep_succ.setCheckable(True)
        self.act_beep_succ.setChecked(self.options.beep_on_success)
        self.act_beep_succ.toggled.connect(self.toggle_beep_on_success)
        options_menu.addAction(self.act_beep_succ)

        options_menu.addSeparator()

        # 8. 在托盘上放置图标(P)
        self.act_tray_icon = QAction("在托盘上放置图标(&P)", self)
        self.act_tray_icon.setCheckable(True)
        self.act_tray_icon.setChecked(self.options.tray_icon_enabled)
        self.act_tray_icon.toggled.connect(self.toggle_tray_icon)
        options_menu.addAction(self.act_tray_icon)

        # 9. 启动时隐藏
        self.act_start_hidden = QAction("启动时隐藏", self)
        self.act_start_hidden.setCheckable(True)
        self.act_start_hidden.setChecked(self.options.start_as_hidden)
        self.act_start_hidden.toggled.connect(self.toggle_start_as_hidden)
        options_menu.addAction(self.act_start_hidden)

        options_menu.addSeparator()

        # 10. 解析 IP 地址
        self.act_resolve_addr = QAction("解析 IP 地址", self)
        self.act_resolve_addr.setCheckable(True)
        self.act_resolve_addr.setChecked(self.options.resolve_addresses)
        self.act_resolve_addr.setToolTip("通过反向 DNS 与局域网 NetBIOS 解析 IP 对应的真实主机名")
        self.act_resolve_addr.toggled.connect(self.toggle_resolve_addresses)
        options_menu.addAction(self.act_resolve_addr)

        options_menu.addSeparator()

        # 11. 显示下窗格
        self.act_show_lower = QAction("显示下窗格", self)
        self.act_show_lower.setCheckable(True)
        self.act_show_lower.setChecked(self.options.show_lower_pane)
        self.act_show_lower.toggled.connect(self.toggle_lower_pane)
        options_menu.addAction(self.act_show_lower)

        # 12. 自动滚动下窗格
        self.act_scroll_lower = QAction("自动滚动下窗格", self)
        self.act_scroll_lower.setCheckable(True)
        self.act_scroll_lower.setChecked(self.options.auto_scroll_lower_pane)
        self.act_scroll_lower.toggled.connect(self.toggle_auto_scroll_lower)
        options_menu.addAction(self.act_scroll_lower)

        options_menu.addSeparator()

        # 13. 刷新后自动排序
        self.act_sort_update = QAction("刷新后自动排序", self)
        self.act_sort_update.setCheckable(True)
        self.act_sort_update.setChecked(self.options.sort_on_every_update)
        self.act_sort_update.toggled.connect(self.toggle_sort_on_every_update)
        options_menu.addAction(self.act_sort_update)

        options_menu.addSeparator()

        # 14. 添加标题行到 CSV/Tab 分隔的文件
        self.act_add_header = QAction("添加标题行到 CSV/Tab 分隔的文件", self)
        self.act_add_header.setCheckable(True)
        self.act_add_header.setChecked(self.options.add_header_to_export)
        self.act_add_header.toggled.connect(self.toggle_add_header_to_export)
        options_menu.addAction(self.act_add_header)

        options_menu.addSeparator()

        # 15. 选择其它字体 / 使用默认字体
        act_font = QAction("选择其它字体", self)
        act_font.triggered.connect(self.choose_custom_font)
        options_menu.addAction(act_font)

        act_default_font = QAction("使用默认字体", self)
        act_default_font.triggered.connect(self.restore_default_font)
        options_menu.addAction(act_default_font)

        options_menu.addSeparator()

        # 16. 高级选项(A)        F9
        act_adv_opts = QAction("高级选项(&A)", self)
        act_adv_opts.setShortcut("F9")
        act_adv_opts.triggered.connect(self.open_advanced_options_dialog)
        options_menu.addAction(act_adv_opts)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")
        act_about = QAction("关于 YouQian PingView(&A)", self)
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
        act_options.setToolTip("Ping 探测基础参数设置 (F10)")
        act_options.triggered.connect(self.open_options_dialog)
        toolbar.addAction(act_options)

        act_adv = QAction(self.icons.settings, "高级选项", self)
        act_adv.setToolTip("配置高级报警声音、命令触发、下窗格模式与日志导出 (F9)")
        act_adv.triggered.connect(self.open_advanced_options_dialog)
        toolbar.addAction(act_adv)

        act_cols = QAction(self.icons.columns, "选择列", self)
        act_cols.setToolTip("选择或隐藏大盘表格列 (Choose Columns)")
        act_cols.triggered.connect(lambda: self.show_column_select_menu())
        toolbar.addAction(act_cols)

        act_sort = QAction(self.icons.sort_az, "排序", self)
        act_sort.setToolTip("快捷列排序选项 (亦可直接点击表头按该列排序，再点反序)")
        act_sort.triggered.connect(self.show_sort_menu)
        toolbar.addAction(act_sort)

        act_export = QAction(self.icons.export, "导出报表", self)
        act_export.triggered.connect(lambda: self.export_report("html"))
        toolbar.addAction(act_export)

        toolbar.addSeparator()

        lbl_filter = QLabel(" 筛选: ")
        toolbar.addWidget(lbl_filter)
        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["显示全部", "仅显示存活", "仅显示失败/异常"])
        # 同步恢复选项中的显示模式状态到工具栏下拉框
        if self.options.display_mode == "仅显示失败的 Hosts":
            self.combo_filter.setCurrentIndex(2)
        elif self.options.display_mode == "仅显示成功的 Hosts":
            self.combo_filter.setCurrentIndex(1)
        else:
            self.combo_filter.setCurrentIndex(0)
        self.combo_filter.currentIndexChanged.connect(self.on_filter_combo_changed)
        toolbar.addWidget(self.combo_filter)

        lbl_search = QLabel("  搜索: ")
        toolbar.addWidget(lbl_search)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("过滤IP、主机或描述...")
        self.search_box.setMaximumWidth(180)
        self.search_box.textChanged.connect(self.apply_filter)
        toolbar.addWidget(self.search_box)

    def setup_upper_table(self):
        self.table_upper.setColumnCount(len(UPPER_COLUMNS))
        self.table_upper.setHorizontalHeaderLabels(UPPER_COLUMNS)
        self.table_upper.setSelectionBehavior(QAbstractItemView.SelectRows)
        # 支持按住 Ctrl 键跳选多项 (例如 1, 3, 5 行) 以及按住 Shift 键连续范围选择 (例如 2-5 行)
        self.table_upper.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_upper.setAlternatingRowColors(True)
        self.table_upper.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_upper.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_upper.customContextMenuRequested.connect(self.show_upper_context_menu)
        self.table_upper.itemSelectionChanged.connect(self.on_upper_selection_changed)
        self.table_upper.doubleClicked.connect(self.on_upper_table_double_clicked)

        header = self.table_upper.horizontalHeader()
        # 允许每一列均可鼠标自由拖拽调整列宽
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        # 核心特性：开启表头每一列均可鼠标自由按住拉动调整排列位置 (Column Reordering)！
        header.setSectionsMovable(True)
        # 表头支持右键菜单弹出「选择列」
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self.show_column_select_menu)
        header.sectionMoved.connect(lambda l, o, n: self.save_persistent_config())
        # 点击序号那一行(表头)任意一列进行排序，再点一下就反序
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self.on_upper_header_clicked)

        upper_widths = [
            36,   # 0: 状态灯
            50,   # 1: 序号
            130,  # 2: 主机名
            120,  # 3: IP 地址
            120,  # 4: 响应 IP 地址
            65,   # 5: 成功次数
            65,   # 6: 失败次数
            85,   # 7: 连续失败次数
            110,  # 8: 最大连续失败次数
            135,  # 9: 最大连续失败时间
            75,   # 10: 失败率(%)
            105,  # 11: 总计发送Pings数
            90,   # 12: 最后 Ping 状态
            95,   # 13: 最后 Ping 时间
            80,   # 14: 最后 Ping TTL
            95,   # 15: 平均 Ping 时间
            130,  # 16: 描述
            135,  # 17: 最后成功时间
            135,  # 18: 最后失败时间
            95,   # 19: 最小Ping时间
            95,   # 20: 最大Ping时间
            55,   # 21: 禁用
            125,  # 22: MAC 地址
        ]
        for col, w in enumerate(upper_widths):
            self.table_upper.setColumnWidth(col, w)

        # 还原用户之前隐藏的列
        for c_idx, c_name in enumerate(UPPER_COLUMNS):
            if c_name and c_name in self.hidden_columns:
                self.table_upper.setColumnHidden(c_idx, True)

        # 还原用户之前拖动调整过的列排布前后位置
        saved_order = self.saved_cfg.get("header_visual_order", [])
        if saved_order and len(saved_order) == len(UPPER_COLUMNS):
            for target_v_idx, logical_idx in enumerate(saved_order):
                current_v_idx = header.visualIndex(logical_idx)
                if current_v_idx != target_v_idx:
                    header.moveSection(current_v_idx, target_v_idx)

    def on_upper_header_clicked(self, col_idx: int):
        """当点击序号这一行的某一列，就按这一行排序，再点一下就反序"""
        if self.current_sort_col == col_idx:
            self.current_sort_desc = not self.current_sort_desc
        else:
            self.current_sort_col = col_idx
            self.current_sort_desc = False

        self.sort_hosts_by_column(self.current_sort_col, self.current_sort_desc)

    def sort_hosts_by_column(self, col_idx: int, desc: bool):
        """按指定指标列对主机数据进行精准类型排序并刷新大盘"""
        import ipaddress

        def parse_ip(val):
            if not val or val == "--":
                return (1, 0)
            try:
                clean = val.split(":")[0]
                return (0, int(ipaddress.ip_address(clean)))
            except Exception:
                return (0, str(val))

        def sort_key(h: HostStat):
            if col_idx == 0:  # 状态灯
                if not h.enabled:
                    return 3
                if h.total_sent == 0:
                    return 2
                return 0 if h.last_status in ("成功", "端口开放") else 1
            elif col_idx == 1:  # 序号
                return h.index
            elif col_idx == 2:  # 主机名
                return (h.hostname or h.target).lower()
            elif col_idx == 3:  # IP 地址
                return parse_ip(h.resolved_ip)
            elif col_idx == 4:  # 响应 IP 地址
                return parse_ip(h.reply_ip or h.resolved_ip)
            elif col_idx == 5:  # 成功次数
                return h.success_count
            elif col_idx == 6:  # 失败次数
                return h.failed_count
            elif col_idx == 7:  # 连续失败次数
                return h.consecutive_failures
            elif col_idx == 8:  # 最大连续失败次数
                return h.max_consecutive_failures
            elif col_idx == 9:  # 最大连续失败时间
                return h.max_consecutive_failure_time or ""
            elif col_idx == 10:  # 失败率(%)
                return h.failure_rate
            elif col_idx == 11:  # 总计发送Pings数
                return h.total_sent
            elif col_idx == 12:  # 最后 Ping 状态
                return h.last_status
            elif col_idx == 13:  # 最后 Ping 时间
                return (1, 0) if h.last_latency_ms is None else (0, h.last_latency_ms)
            elif col_idx == 14:  # 最后 Ping TTL
                return (1, 0) if h.last_ttl is None else (0, h.last_ttl)
            elif col_idx == 15:  # 平均 Ping 时间
                return (1, 0) if h.avg_latency_ms is None else (0, h.avg_latency_ms)
            elif col_idx == 16:  # 描述
                return (h.description or "").lower()
            elif col_idx == 17:  # 最后成功时间
                return h.last_success_time or ""
            elif col_idx == 18:  # 最后失败时间
                return h.last_failed_time or ""
            elif col_idx == 19:  # 最小Ping时间
                return (1, 0) if h.min_latency_ms is None else (0, h.min_latency_ms)
            elif col_idx == 20:  # 最大Ping时间
                return (1, 0) if h.max_latency_ms is None else (0, h.max_latency_ms)
            elif col_idx == 21:  # 禁用
                return 1 if not h.enabled else 0
            elif col_idx == 22:  # MAC 地址
                return h.mac_address or ""
            return h.index

        self.hosts.sort(key=sort_key, reverse=desc)
        self.refresh_upper_table_full()

        order = Qt.DescendingOrder if desc else Qt.AscendingOrder
        self.table_upper.horizontalHeader().setSortIndicator(col_idx, order)

    def show_sort_menu(self):
        """点击工具栏 AZ 图标弹出的快捷排序选项菜单"""
        menu = QMenu(self)
        title_action = menu.addAction("--- 快捷排序选项 (Sort Options) ---")
        title_action.setEnabled(False)
        menu.addSeparator()

        sort_presets = [
            ("按 序号 排序", 1),
            ("按 主机名 排序", 2),
            ("按 IP 地址 排序", 3),
            ("按 平均响应时间 排序", 15),
            ("按 失败率(%) 排序", 10),
            ("按 失败次数 排序", 6),
            ("按 连续失败次数 排序", 7),
        ]
        for name, col_i in sort_presets:
            act = menu.addAction(name)
            def make_trigger(c):
                return lambda: self.on_upper_header_clicked(c)
            act.triggered.connect(make_trigger(col_i))

        menu.addSeparator()
        cur_col_name = UPPER_COLUMNS[self.current_sort_col] if self.current_sort_col is not None and self.current_sort_col < len(UPPER_COLUMNS) and UPPER_COLUMNS[self.current_sort_col] else "序号"
        act_toggle = menu.addAction(f"当前排序列: [{cur_col_name}] · 切换反转方向")
        act_toggle.triggered.connect(lambda: self.on_upper_header_clicked(self.current_sort_col if self.current_sort_col is not None else 1))

        menu.exec_(QCursor.pos())

    def show_column_select_menu(self, pos=None):
        """弹出列选择复选菜单，支持勾选/取消勾选任意指标列，并自动持久化保存"""
        menu = QMenu(self)
        title_action = menu.addAction("--- 选择显示的列 (Choose Columns) ---")
        title_action.setEnabled(False)
        menu.addSeparator()

        for col_idx in range(1, len(UPPER_COLUMNS)):
            col_name = UPPER_COLUMNS[col_idx]
            action = QAction(col_name, menu)
            action.setCheckable(True)
            is_hidden = self.table_upper.isColumnHidden(col_idx)
            action.setChecked(not is_hidden)

            def make_toggle(c_idx, name):
                def toggle(checked):
                    self.table_upper.setColumnHidden(c_idx, not checked)
                    if checked:
                        if name in self.hidden_columns:
                            self.hidden_columns.remove(name)
                    else:
                        if name not in self.hidden_columns:
                            self.hidden_columns.append(name)
                    self.save_persistent_config()
                return toggle

            action.triggered.connect(make_toggle(col_idx, col_name))
            menu.addAction(action)

        if pos is not None and isinstance(pos, QPoint):
            menu.exec_(self.table_upper.horizontalHeader().viewport().mapToGlobal(pos))
        else:
            menu.exec_(QCursor.pos())

    def setup_lower_table(self):
        self.table_lower.setColumnCount(len(LOWER_COLUMNS))
        self.table_lower.setHorizontalHeaderLabels(LOWER_COLUMNS)
        self.table_lower.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_lower.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_lower.setAlternatingRowColors(True)

        header = self.table_lower.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        # 允许下窗格每一列均可按住表头自由拉动排列位置 (拖动移位置)
        header.setSectionsMovable(True)
        header.sectionMoved.connect(lambda l, o, n: self.save_persistent_config())

        # 开启表头排序指示器小三角，支持单击与双击表头排序
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self.on_lower_header_clicked)
        header.sectionDoubleClicked.connect(self.on_lower_header_clicked)

        lower_widths = [150, 130, 90, 80, 95, 80]
        for col, w in enumerate(lower_widths):
            self.table_lower.setColumnWidth(col, w)

        # 还原用户之前拖动调整过的下窗格列排列顺序
        saved_lower_order = self.saved_cfg.get("lower_header_visual_order", [])
        if saved_lower_order and len(saved_lower_order) == len(LOWER_COLUMNS):
            for target_v_idx, logical_idx in enumerate(saved_lower_order):
                current_v_idx = header.visualIndex(logical_idx)
                if current_v_idx != target_v_idx:
                    header.moveSection(current_v_idx, target_v_idx)

    def on_lower_header_clicked(self, col_idx: int):
        """下窗格表头单击或双击事件：按选中列进行升降序排序切换"""
        if self.lower_sort_col == col_idx:
            self.lower_sort_desc = not self.lower_sort_desc
        else:
            self.lower_sort_col = col_idx
            self.lower_sort_desc = False

        order = Qt.DescendingOrder if self.lower_sort_desc else Qt.AscendingOrder
        self.table_lower.horizontalHeader().setSortIndicator(col_idx, order)

        if getattr(self, "selected_host_id", None):
            host = next((h for h in self.hosts if h.host_id == self.selected_host_id), None)
            if host:
                self.refresh_lower_table(host)

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
        self.current_round_id += 1  # 切换目标清单，使所有旧在途探测回调立即作废
        self.is_probing_round_active = False
        self.target_raw_text = text
        items = parse_targets_text(
            text,
            skip_first=self.options.cidr_skip_first,
            skip_last=self.options.cidr_skip_last,
            use_ip_host_format=self.options.use_ip_host_format
        )

        # 若未允许 IPv6 地址，过滤掉纯 IPv6 目标
        if not self.options.allow_ipv6:
            import ipaddress
            filtered_items = []
            for item in items:
                try:
                    if ipaddress.ip_address(item.target).version == 6:
                        continue
                except ValueError:
                    pass
                filtered_items.append(item)
            items = filtered_items

        self.hosts = []
        for idx, item in enumerate(items, start=1):
            stat = HostStat(idx, item.target, item.description, item.port, group=item.group)
            self.hosts.append(stat)
        self.refresh_upper_table_full()
        self.update_summary_status()
        self.start_background_name_resolution()

    def refresh_upper_table_full(self):
        # 清除现有跨列合并与映射表
        self.table_upper.clearSpans()
        self.host_to_row.clear()
        self.row_to_host.clear()
        self.row_to_group.clear()
        self.group_to_header_row.clear()

        # 检查是否存在任何有效分组声明
        has_groups = any(bool(h.group) for h in self.hosts)

        if not has_groups:
            # 经典扁平单表模式
            self.table_upper.setRowCount(len(self.hosts))
            for row, host in enumerate(self.hosts):
                self.host_to_row[host.host_id] = row
                self.row_to_host[row] = host
                self.update_upper_table_row(row, host)
        else:
            # 原版 PingInfoView 2.20 分组组织模式
            groups_order = []
            grouped_hosts: Dict[str, List[HostStat]] = {}
            for h in self.hosts:
                g_name = h.group if h.group else "默认分组"
                if g_name not in grouped_hosts:
                    groups_order.append(g_name)
                    grouped_hosts[g_name] = []
                grouped_hosts[g_name].append(h)

            total_rows = sum(1 + len(hl) for hl in grouped_hosts.values())
            self.table_upper.setRowCount(total_rows)

            curr_row = 0
            for g_name in groups_order:
                hl = grouped_hosts[g_name]
                header_r = curr_row
                self.row_to_group[header_r] = g_name
                self.group_to_header_row[g_name] = header_r
                self.update_group_header_row(header_r, g_name, len(hl))
                curr_row += 1

                for h in hl:
                    r = curr_row
                    self.host_to_row[h.host_id] = r
                    self.row_to_host[r] = h
                    self.update_upper_table_row(r, h)
                    curr_row += 1

        self.apply_filter()

    def update_group_header_row(self, row: int, group_name: str, count: int):
        """渲染原版 PingInfoView 风格的跨列分组标题行"""
        self.table_upper.setSpan(row, 0, 1, len(UPPER_COLUMNS))
        is_collapsed = group_name in self.collapsed_groups
        arrow = "▶" if is_collapsed else "▼"
        state_tip = " [已折叠 - 双击展开]" if is_collapsed else " [双击折叠]"
        text = f" {arrow}  {group_name}  ({count} 个监控目标){state_tip}"

        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        font = QFont()
        font.setBold(True)
        item.setFont(font)
        item.setBackground(QBrush(QColor("#f1f5f9")))
        item.setForeground(QBrush(QColor("#0f172a")))
        self.table_upper.setItem(row, 0, item)

    def toggle_group_collapse(self, group_name: str):
        """双击切换指定分组的折叠/展开状态"""
        if group_name in self.collapsed_groups:
            self.collapsed_groups.remove(group_name)
        else:
            self.collapsed_groups.add(group_name)
        self.apply_filter()

    def expand_all_groups(self):
        """全部展开所有分组"""
        self.collapsed_groups.clear()
        self.apply_filter()

    def collapse_all_groups(self):
        """全部折叠所有分组"""
        for g_name in self.row_to_group.values():
            self.collapsed_groups.add(g_name)
        self.apply_filter()

    def on_upper_table_double_clicked(self, index):
        """表格双击事件调度：双击分组标题行触发折叠/展开；双击主机数据行打开属性"""
        row = index.row()
        if row in self.row_to_group:
            self.toggle_group_collapse(self.row_to_group[row])
        elif row in self.row_to_host:
            self.show_selected_properties()

    def start_background_name_resolution(self):
        """后台异步并发反向解析所有纯 IP 目标的真实主机名 (NetBIOS / 反向 DNS)，不阻塞主界面"""
        if not getattr(self.options, "resolve_addresses", True):
            return

        targets_to_resolve = []
        for h in self.hosts:
            if not h.hostname:
                ip_val = h.resolved_ip or h.target
                targets_to_resolve.append((h.host_id, ip_val))

        if not targets_to_resolve:
            return

        def _resolve_worker():
            with ThreadPoolExecutor(max_workers=min(20, len(targets_to_resolve))) as pool:
                def _do_resolve(hid: str, ip_str: str):
                    name = resolve_host_name(ip_str)
                    if name:
                        self.signals.hostname_resolved.emit(hid, name)

                futures = [pool.submit(_do_resolve, hid, ip_s) for hid, ip_s in targets_to_resolve]
                for f in futures:
                    try:
                        f.result()
                    except Exception:
                        pass

        import threading
        threading.Thread(target=_resolve_worker, daemon=True).start()

    def on_hostname_resolved(self, host_id: str, hostname: str):
        """主线程槽函数：当后台解析出主机名时，实时刷新表格第 2 列【主机名】"""
        for h in self.hosts:
            if h.host_id == host_id:
                h.hostname = hostname
                row = self.host_to_row.get(host_id)
                if row is not None:
                    self.update_upper_table_row(row, h)
                break

    def on_filter_combo_changed(self, index: int):
        """工具栏筛选下拉框与选项菜单显示模式双向联动"""
        if index == 2:
            self.options.display_mode = "仅显示失败的 Hosts"
            if hasattr(self, "act_mode_failed"):
                self.act_mode_failed.setChecked(True)
        elif index == 1:
            self.options.display_mode = "仅显示成功的 Hosts"
            if hasattr(self, "act_mode_succ"):
                self.act_mode_succ.setChecked(True)
        else:
            self.options.display_mode = "显示所有 Hosts"
            if hasattr(self, "act_mode_all"):
                self.act_mode_all.setChecked(True)
        self.save_persistent_config()
        self.apply_filter()

    def set_display_mode(self, mode: str):
        """选项菜单设置显示模式"""
        self.options.display_mode = mode
        self.save_persistent_config()
        if mode == "仅显示失败的 Hosts":
            self.combo_filter.setCurrentIndex(2)
        elif mode == "仅显示成功的 Hosts":
            self.combo_filter.setCurrentIndex(1)
        else:
            self.combo_filter.setCurrentIndex(0)
        self.apply_filter()

    def format_latency(self, latency: Optional[float]) -> str:
        """根据高分辨率 ping 时间设置格式化延迟"""
        if latency is None:
            return "--"
        if self.options.high_resolution_timer:
            return f"{latency:.3f}"
        return f"{int(round(latency))}"

    def format_time(self, time_str: str) -> str:
        """根据以 GMT 格式显示时间设置格式化时间字符串"""
        if not time_str or time_str == "--":
            return "--"
        if not self.options.show_gmt_time:
            return time_str
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            import time
            from datetime import timedelta
            offset = time.timezone if (time.localtime().tm_isdst == 0) else time.altzone
            utc_dt = dt + timedelta(seconds=offset)
            return utc_dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return time_str

    def toggle_high_resolution_timer(self, checked: bool):
        self.options.high_resolution_timer = checked
        self.save_persistent_config()
        self.refresh_upper_table_full()
        if getattr(self, "selected_host_id", None):
            h = next((x for x in self.hosts if x.host_id == self.selected_host_id), None)
            if h:
                self.refresh_lower_table(h)

    def toggle_gmt_time(self, checked: bool):
        self.options.show_gmt_time = checked
        self.save_persistent_config()
        self.refresh_upper_table_full()
        if getattr(self, "selected_host_id", None):
            h = next((x for x in self.hosts if x.host_id == self.selected_host_id), None)
            if h:
                self.refresh_lower_table(h)

    def toggle_mark_failed_pings(self, checked: bool):
        self.options.mark_failed_pings = checked
        self.save_persistent_config()
        self.refresh_upper_table_full()
        if getattr(self, "selected_host_id", None):
            h = next((x for x in self.hosts if x.host_id == self.selected_host_id), None)
            if h:
                self.refresh_lower_table(h)

    def toggle_always_on_top(self, checked: bool):
        self.options.always_on_top = checked
        self.save_persistent_config()
        flags = self.windowFlags()
        if checked:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def toggle_beep_on_failed(self, checked: bool):
        self.options.beep_on_failed = checked
        self.save_persistent_config()

    def toggle_beep_on_success(self, checked: bool):
        self.options.beep_on_success = checked
        self.save_persistent_config()

    def toggle_tray_icon(self, checked: bool):
        self.options.tray_icon_enabled = checked
        self.save_persistent_config()
        if self.tray_icon:
            if checked:
                self.tray_icon.show()
            else:
                self.tray_icon.hide()

    def toggle_start_as_hidden(self, checked: bool):
        self.options.start_as_hidden = checked
        self.save_persistent_config()

    def setup_tray_icon(self):
        self.tray_icon = None
        if not hasattr(QSystemTrayIcon, "isSystemTrayAvailable") or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = getattr(self.icons, "app_logo", None) or self.icons.start
        self.tray_icon = QSystemTrayIcon(icon, self)
        tray_menu = QMenu(self)
        act_show = tray_menu.addAction("显示主窗口")
        act_show.triggered.connect(self.show_normal_and_raise)
        act_start = tray_menu.addAction("开始 Ping")
        act_start.triggered.connect(self.start_ping)
        act_stop = tray_menu.addAction("停止 Ping")
        act_stop.triggered.connect(self.stop_ping)
        tray_menu.addSeparator()
        act_exit = tray_menu.addAction("退出")
        act_exit.triggered.connect(self.force_exit)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        if self.options.tray_icon_enabled:
            self.tray_icon.show()

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_normal_and_raise()

    def show_normal_and_raise(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def force_exit(self):
        if self.tray_icon:
            self.tray_icon.hide()
        self.close()

    def toggle_lower_pane(self, checked: bool):
        self.options.show_lower_pane = checked
        self.save_persistent_config()
        self.lower_widget.setVisible(checked)

    def toggle_auto_scroll_lower(self, checked: bool):
        self.options.auto_scroll_lower_pane = checked
        self.save_persistent_config()

    def toggle_sort_on_every_update(self, checked: bool):
        self.options.sort_on_every_update = checked
        self.save_persistent_config()

    def toggle_add_header_to_export(self, checked: bool):
        self.options.add_header_to_export = checked
        self.save_persistent_config()

    def choose_custom_font(self):
        curr_font = self.table_upper.font()
        ok, font = QFontDialog.getFont(curr_font, self, "选择表格显示字体")
        if ok:
            self.apply_custom_font(font)
            self.options.custom_font_family = font.family()
            self.options.custom_font_size = font.pointSize()
            self.save_persistent_config()

    def restore_default_font(self):
        default_font = QApplication.font()
        self.apply_custom_font(default_font)
        self.options.custom_font_family = ""
        self.options.custom_font_size = 9
        self.save_persistent_config()

    def apply_custom_font(self, font: QFont):
        self.table_upper.setFont(font)
        self.table_lower.setFont(font)

    def toggle_resolve_addresses(self, checked: bool):
        """切换是否自动解析地址"""
        self.options.resolve_addresses = checked
        self.save_persistent_config()
        if checked:
            self.start_background_name_resolution()

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
        hostname_display = f"{host.hostname}:{host.port}" if (host.hostname and host.port) else (host.hostname or target_display)
        ip_display = host.resolved_ip or host.target

        col_values = [
            str(host.index),                                                      # 1: 序号
            hostname_display,                                                     # 2: 主机名
            ip_display,                                                           # 3: IP 地址
            host.reply_ip or host.resolved_ip or "--",                            # 4: 响应 IP 地址
            str(host.success_count),                                              # 5: 成功次数
            str(host.failed_count),                                               # 6: 失败次数
            str(host.consecutive_failures),                                       # 7: 连续失败次数
            str(host.max_consecutive_failures),                                   # 8: 最大连续失败次数
            self.format_time(host.max_consecutive_failure_time),                  # 9: 最大连续失败时间
            f"{host.failure_rate:.1f}%",                                          # 10: 失败率(%)
            str(host.total_sent),                                                 # 11: 总计发送Pings数
            host.last_status,                                                     # 12: 最后 Ping 状态
            self.format_latency(host.last_latency_ms),                             # 13: 最后 Ping 时间
            str(host.last_ttl) if host.last_ttl is not None else "--",            # 14: 最后 Ping TTL
            self.format_latency(host.avg_latency_ms),                              # 15: 平均 Ping 时间
            host.description or "",                                               # 16: 描述
            self.format_time(host.last_success_time),                             # 17: 最后成功时间
            self.format_time(host.last_failed_time),                              # 18: 最后失败时间
            self.format_latency(host.min_latency_ms),                              # 19: 最小Ping时间
            self.format_latency(host.max_latency_ms),                              # 20: 最大Ping时间
            "是" if not host.enabled else "否",                                   # 21: 禁用
            host.mac_address or "--"                                              # 22: MAC 地址
        ]

        bg_color = None
        if self.options.mark_failed_pings and host.total_sent > 0 and host.last_status not in ("成功", "端口开放"):
            bg_color = QColor("#fee2e2")

        for c_idx, val in enumerate(col_values, start=1):
            it = QTableWidgetItem(val)
            if bg_color:
                it.setBackground(QBrush(bg_color))
            if c_idx not in (2, 16):
                it.setTextAlignment(Qt.AlignCenter)
            self.table_upper.setItem(row, c_idx, it)

    def on_upper_selection_changed(self):
        selected_rows = self.table_upper.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        host = self.row_to_host.get(row)
        if host:
            self.selected_host_id = host.host_id
            target_str = f"{host.target}:{host.port}" if host.port else host.target
            self.lbl_lower_title.setText(f"主机 [{target_str} ({host.description or '无描述'})] 探测流水记录 (共 {len(host.history_records)} 条)：")
            self.refresh_lower_table(host)

    def refresh_lower_table(self, host: HostStat):
        records = list(host.history_records)
        # 若用户指定了排序列，执行稳定排序
        if self.lower_sort_col is not None:
            def _lower_sort_key(r: PingRecord):
                if self.lower_sort_col == 0:  # 发送时间
                    return r.timestamp or ""
                elif self.lower_sort_col == 1: # 响应 IP 地址
                    return r.resolved_ip or r.target or ""
                elif self.lower_sort_col == 2: # Ping 时间
                    return (1, 0) if r.latency_ms is None else (0, r.latency_ms)
                elif self.lower_sort_col == 3: # Ping 衰减 (TTL)
                    return (1, 0) if r.ttl is None else (0, r.ttl)
                elif self.lower_sort_col == 4: # Ping 状态
                    return r.status or ""
                elif self.lower_sort_col == 5: # Ping 计数
                    return r.sequence
                return r.sequence
            records.sort(key=_lower_sort_key, reverse=self.lower_sort_desc)

        self.table_lower.setRowCount(len(records))
        for row, rec in enumerate(records):
            vals = [
                self.format_time(rec.timestamp),                                        # 发送时间
                rec.resolved_ip or rec.target or "--",                                  # 响应 IP 地址
                self.format_latency(rec.latency_ms),                                    # Ping 时间
                str(rec.ttl) if rec.ttl is not None else "--",                          # Ping 衰减 (TTL)
                rec.status,                                                             # Ping 状态
                str(rec.sequence)                                                       # Ping 计数
            ]
            bg_color = QColor("#fee2e2") if (self.options.mark_failed_pings and rec.status not in ("成功", "端口开放")) else None
            for col, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if bg_color:
                    it.setBackground(QBrush(bg_color))
                it.setTextAlignment(Qt.AlignCenter)
                self.table_lower.setItem(row, col, it)

        # 当开启自动滚动下窗格时，立即并配合延时双重确保精准滚屏到位
        if self.options.auto_scroll_lower_pane and len(records) > 0:
            self.scroll_lower_to_target()
            QTimer.singleShot(10, self.scroll_lower_to_target)

    def scroll_lower_to_target(self):
        """精准执行下窗格自动滚动到最新记录"""
        row_count = self.table_lower.rowCount()
        if row_count <= 0:
            return

        if self.lower_sort_col is None or (self.lower_sort_col in (0, 5) and not self.lower_sort_desc):
            # 默认时间正序 (最底部为最新探测记录)，使用 scrollToItem 与滚动条双重置底
            last_item = self.table_lower.item(row_count - 1, 0)
            if last_item:
                self.table_lower.scrollToItem(last_item, QAbstractItemView.PositionAtBottom)
            self.table_lower.scrollToBottom()
            vsb = self.table_lower.verticalScrollBar()
            vsb.setValue(vsb.maximum())
        else:
            # 倒序 (顶部为最新探测记录)，滚动到顶部
            first_item = self.table_lower.item(0, 0)
            if first_item:
                self.table_lower.scrollToItem(first_item, QAbstractItemView.PositionAtTop)
            self.table_lower.scrollToTop()
            self.table_lower.verticalScrollBar().setValue(0)

    def start_ping(self):
        if not self.hosts:
            QMessageBox.warning(self, "提示", "当前没有探测目标，请先添加目标！")
            return

        self.is_running = True
        self.act_start.setEnabled(False)
        self.act_stop.setEnabled(True)
        self.lbl_status_mode.setText("状态: 正在并发探测中...")

        if self.options.auto_export and self.options.auto_export_filename:
            self.auto_export_timer.start(self.options.auto_export_interval * 1000)

        self.trigger_probe_round()

    def stop_ping(self):
        self.is_running = False
        self.current_round_id += 1  # 递增轮次ID，立即使后台所有在途旧任务的结果失效丢弃
        self.is_probing_round_active = False
        self.poll_timer.stop()
        self.countdown_timer.stop()
        self.auto_export_timer.stop()
        self.act_start.setEnabled(True)
        self.act_stop.setEnabled(False)
        self.lbl_status_mode.setText("状态: 已停止")
        self.lbl_countdown.setText("下次探测: 已停止")

    def trigger_probe_round(self, is_manual_single: bool = False):
        if not self.is_running and not is_manual_single:
            return

        if self.is_probing_round_active:
            # 互斥保护：上一轮并发尚未全部完成，拒绝重入启动，防止并发线程池失控
            return

        self.is_probing_round_active = True
        self.current_round_id += 1
        this_round = self.current_round_id

        self.lbl_status_mode.setText("状态: 正在发送 Ping 探测包...")
        self.poll_timer.stop()
        self.countdown_timer.stop()

        timeout_ms = self.options.timeout_ms
        pkt_size = self.options.packet_size
        custom_ttl_enabled = self.options.custom_ttl_enabled
        custom_ttl = self.options.custom_ttl
        dont_fragment = self.options.dont_fragment
        source_ipv4 = self.options.source_ipv4
        source_ipv6 = self.options.source_ipv6
        resolve_dns_every_ping = self.options.resolve_dns_every_ping

        targets_snapshot = [(h.host_id, h) for h in self.hosts if h.enabled]
        max_workers = min(self.options.max_threads, len(targets_snapshot) or 1)

        def worker_task(h_id: str, host_stat: HostStat):
            is_succ, lat, ttl, status_str, resp_ip = PingWorker.probe(
                host_stat,
                timeout_ms,
                pkt_size,
                custom_ttl_enabled=custom_ttl_enabled,
                custom_ttl=custom_ttl,
                dont_fragment=dont_fragment,
                source_ipv4=source_ipv4,
                source_ipv6=source_ipv6,
                resolve_dns_every_ping=resolve_dns_every_ping
            )
            self.signals.single_result.emit(this_round, h_id, is_succ, lat, ttl, status_str, resp_ip)

        def runner():
            if targets_snapshot:
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    futures = [pool.submit(worker_task, hid, h) for hid, h in targets_snapshot]
                    for f in futures:
                        try:
                            f.result()
                        except Exception:
                            pass
            self.signals.round_finished.emit(this_round)

        import threading
        t = threading.Thread(target=runner, daemon=True)
        t.start()

    def on_single_probe_result(self, round_id: int, host_id: str, is_success: bool, latency: Optional[float],
                               ttl: Optional[int], status_msg: str, resolved_ip: str):
        # 1. 验证轮次：过期轮次直接丢弃，杜绝历史串线污染
        if round_id != self.current_round_id:
            return

        # 2. 根据 host_id 精准匹配目标
        host = None
        for h in self.hosts:
            if h.host_id == host_id:
                host = h
                break

        if host is None:
            return

        max_accum = self.options.max_accumulated_pings if self.options.limit_accumulated_pings else 50000
        record = host.update_result(
            is_success, latency, ttl, status_msg, resolved_ip,
            lower_pane_mode=self.options.lower_pane_mode,
            max_accumulated=max_accum
        )
        row = self.host_to_row.get(host_id)
        if row is not None:
            self.update_upper_table_row(row, host)
            self.update_row_visibility(row, host)

        if getattr(self, "selected_host_id", None) == host_id:
            target_str = f"{host.target}:{host.port}" if host.port else host.target
            self.lbl_lower_title.setText(f"主机 [{target_str} ({host.description or '无描述'})] 探测流水记录 (共 {len(host.history_records)} 条)：")
            self.refresh_lower_table(host)

        # 写入日志文件
        if self.options.log_pings and self.options.log_filename:
            AlertManager.append_log_entry(
                self.options.log_filename,
                self.options.log_file_type,
                self.options.log_pings_mode,
                host,
                record
            )

        # 失败报警与命令触发
        if not is_success:
            if self.options.beep_on_failed:
                try:
                    QApplication.beep()
                except Exception:
                    pass
            if host.consecutive_failures == self.options.consecutive_failed_trigger:
                AlertManager.play_sound(self.options.failed_sound_type, self.options.failed_audio_path)
                if self.options.use_failed_cmd and self.options.failed_cmd:
                    AlertManager.execute_command_async(self.options.failed_cmd, host)
        else:
            # 成功报警与命令触发 (仅在上次失败后恢复时触发)
            if host.had_previous_failure:
                if self.options.beep_on_success:
                    try:
                        QApplication.beep()
                    except Exception:
                        pass
                if host.consecutive_successes == self.options.consecutive_success_trigger:
                    AlertManager.play_sound(self.options.success_sound_type, self.options.success_audio_path)
                    if self.options.use_success_cmd and self.options.success_cmd:
                        AlertManager.execute_command_async(self.options.success_cmd, host)

        # 探测成功时若尚未获取到主机名，后台异步触发补充反查
        if is_success and not host.hostname and getattr(self.options, "resolve_addresses", True):
            def _async_single():
                ip_to_query = host.reply_ip or host.resolved_ip or host.target
                name = resolve_host_name(ip_to_query)
                if name:
                    self.signals.hostname_resolved.emit(host_id, name)
            import threading
            threading.Thread(target=_async_single, daemon=True).start()

    def on_round_finished(self, round_id: int):
        if round_id != self.current_round_id:
            return

        self.is_probing_round_active = False
        if self.options.sort_on_every_update and self.current_sort_col is not None:
            self.sort_hosts_by_column(self.current_sort_col, self.current_sort_desc)
        self.update_summary_status()
        self.apply_filter()

        if self.is_running:
            # 若未开启重复间隔 (即单次探测模式)，完成一轮后自动停止
            if not self.options.auto_repeat:
                self.stop_ping()
                self.lbl_status_mode.setText("状态: 单次探测已完成")
                self.lbl_countdown.setText("下次探测: 已结束")
                return

            self.lbl_status_mode.setText("状态: 本轮探测完成，等待下一轮")
            self.countdown_sec = self.options.interval_sec
            self.update_countdown()
            self.countdown_timer.start(1000)
            self.poll_timer.start(self.options.interval_sec * 1000)
        else:
            self.lbl_status_mode.setText("状态: 手动探测完成")
            self.lbl_countdown.setText("下次探测: 已停止")

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
        groups_count = len(set(h.group for h in self.hosts if h.group))
        g_text = f" ({groups_count}个分组)" if groups_count > 0 else ""
        self.lbl_status_count.setText(f"监控目标: {total}{g_text} | 存活: {alive} | 异常: {down}")

    def update_row_visibility(self, row: int, host: HostStat):
        """根据当前筛选模式及分组折叠状态，动态更新单行的显示/隐藏状态"""
        g_name = host.group if host.group else "默认分组"
        if g_name in self.collapsed_groups:
            self.table_upper.setRowHidden(row, True)
            return

        search_kw = self.search_box.text().strip().lower()
        filter_mode = self.combo_filter.currentIndex()  # 0: 全部, 1: 存活, 2: 异常/失败

        match_search = True
        if search_kw:
            combined_str = f"{host.target} {host.resolved_ip} {host.description} {host.group}".lower()
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
        """批量更新所有主机行与分组标题行的显示与隐藏"""
        search_kw = self.search_box.text().strip().lower()
        filter_mode = self.combo_filter.currentIndex()

        group_has_visible_child = {}

        # 1. 遍历所有主机行
        for row, host in self.row_to_host.items():
            g_name = host.group if host.group else "默认分组"
            is_group_collapsed = g_name in self.collapsed_groups

            match_search = True
            if search_kw:
                combined_str = f"{host.target} {host.resolved_ip} {host.description} {host.group}".lower()
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
                    match_status = (host.total_sent > 0 and host.last_status not in ("成功", "端口开放"))

            child_visible = match_search and match_status
            if child_visible:
                group_has_visible_child[g_name] = True

            if is_group_collapsed:
                self.table_upper.setRowHidden(row, True)
            else:
                self.table_upper.setRowHidden(row, not child_visible)

        # 2. 遍历所有分组标题行并更新标题状态
        for row, g_name in self.row_to_group.items():
            if (search_kw or filter_mode != 0) and not group_has_visible_child.get(g_name, False):
                self.table_upper.setRowHidden(row, True)
            else:
                self.table_upper.setRowHidden(row, False)
            g_count = sum(1 for h in self.hosts if (h.group if h.group else "默认分组") == g_name)
            self.update_group_header_row(row, g_name, g_count)

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
        复制用户选中的整行数据，按当前大盘界面的【视觉列排列顺序】与【可见列】所见即所得导出
        第 1 行为当前可见表头标题，第 2 行及后续行依次为选中项的数据行
        """
        selected_indexes = self.table_upper.selectionModel().selectedRows()
        if not selected_indexes:
            return

        header = self.table_upper.horizontalHeader()
        # 获取当前所有可见且非状态灯的视觉列序列 (严格遵循用户拖动排列后的位置)
        visible_logical_cols = []
        visible_headers = []
        for v_idx in range(header.count()):
            l_idx = header.logicalIndex(v_idx)
            if not self.table_upper.isColumnHidden(l_idx) and l_idx < len(UPPER_COLUMNS):
                col_name = UPPER_COLUMNS[l_idx]
                if col_name:  # 过滤第0列状态灯
                    visible_logical_cols.append(l_idx)
                    visible_headers.append(col_name)

        if not visible_logical_cols:
            return

        selected_rows = sorted([idx.row() for idx in selected_indexes])
        output_lines = ["\t".join(visible_headers)]

        for r in selected_rows:
            if r in self.row_to_group:
                output_lines.append(f"[{self.row_to_group[r]}]")
                continue
            row_data = []
            for c_idx in visible_logical_cols:
                item = self.table_upper.item(r, c_idx)
                row_data.append(item.text() if item else "")
            output_lines.append("\t".join(row_data))

        final_text = "\n".join(output_lines)
        QApplication.clipboard().setText(final_text)

    def show_selected_properties(self):
        """打开原版 1:1 经典属性对话框"""
        selected_indexes = self.table_upper.selectionModel().selectedRows()
        if not selected_indexes:
            return
        row = selected_indexes[0].row()
        host = self.row_to_host.get(row)
        if host:
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
            host = self.row_to_host.get(r)
            if host:
                if target_state is None:
                    target_state = not host.enabled
                host.enabled = target_state
                self.update_upper_table_row(r, host)
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
        items_to_probe = []
        for idx in selected_indexes:
            r = idx.row()
            h = self.row_to_host.get(r)
            if h and h.enabled:
                items_to_probe.append((h.host_id, h))

        if not items_to_probe:
            return

        this_round = self.current_round_id

        def do_probe_batch():
            for hid, h in items_to_probe:
                succ, lat, ttl, status_str, resp_ip = PingWorker.probe(h, timeout_ms, pkt_size)
                self.signals.single_result.emit(this_round, hid, succ, lat, ttl, status_str, resp_ip)

        import threading
        threading.Thread(target=do_probe_batch, daemon=True).start()

    def refresh_all_now(self):
        """全局刷新：立即发出一轮完整的并发探测"""
        if self.is_probing_round_active:
            return
        self.lbl_status_mode.setText("状态: 正在手动触发刷新探测...")
        self.trigger_probe_round(is_manual_single=True)

    def reset_all_stats(self):
        for h in self.hosts:
            h.reset_stats()
        self.refresh_upper_table_full()
        self.table_lower.setRowCount(0)
        self.update_summary_status()

    def save_persistent_config(self):
        """将当前目标地址、所有选项参数、用户隐藏列与列排布顺序偏好持久化保存到本地"""
        try:
            header = self.table_upper.horizontalHeader()
            visual_order = [header.logicalIndex(v_idx) for v_idx in range(header.count())]
            lower_header = self.table_lower.horizontalHeader()
            lower_visual_order = [lower_header.logicalIndex(v_idx) for v_idx in range(lower_header.count())]
            data = {
                "targets_text": self.target_raw_text if self.options.remember_targets else "",
                "options": self.options.to_dict(),
                "hidden_columns": self.hidden_columns,
                "header_visual_order": visual_order,
                "lower_header_visual_order": lower_visual_order
            }
            ConfigManager.save_config(data)
        except Exception:
            pass

    def closeEvent(self, event):
        """窗口关闭前自动持久化配置并安全退出；若开启托盘则最小化到托盘"""
        self.save_persistent_config()
        if self.options.tray_icon_enabled and getattr(self, "tray_icon", None) and self.tray_icon.isVisible():
            self.hide()
            try:
                self.tray_icon.showMessage("YouQian PingView", "程序已最小化到系统托盘，双击托盘图标恢复窗口。", QSystemTrayIcon.Information, 2000)
            except Exception:
                pass
            event.ignore()
            return
        self.stop_ping()
        event.accept()

    def open_target_dialog(self):
        was_running = self.is_running
        if was_running:
            self.stop_ping()

        dlg = TargetDialog(self.target_raw_text, self)
        if dlg.exec_():
            self.target_raw_text = dlg.get_text()
            self.load_initial_targets(self.target_raw_text)
            self.save_persistent_config()

        if was_running:
            self.start_ping()

    def open_options_dialog(self):
        dlg = OptionsDialog(self.options, self)
        if dlg.exec_():
            self.update_window_title()
            for h in self.hosts:
                h.max_history = self.options.limit_history_count
            self.load_initial_targets(self.target_raw_text)
            self.save_persistent_config()

            # 若用户点击了“开始”按钮
            if dlg.start_requested and not self.is_running:
                self.start_ping()

    def open_advanced_options_dialog(self):
        """打开原版 1:1 高级选项设置对话框"""
        dlg = AdvancedOptionsDialog(self.options, self)
        if dlg.exec_():
            self.save_persistent_config()
            # 动态调整自动导出定时器状态
            if self.is_running and self.options.auto_export and self.options.auto_export_filename:
                self.auto_export_timer.start(self.options.auto_export_interval * 1000)
            else:
                self.auto_export_timer.stop()

    def on_auto_export_timer(self):
        """下窗格项目自动定时导出处理"""
        if not self.options.auto_export or not self.options.auto_export_filename:
            return

        records_to_export = []
        for h in self.hosts:
            records_to_export.extend(h.history_records)

        if not records_to_export:
            return

        delimiter = "\t" if "制表符" in self.options.auto_export_file_type else ","
        lines = []
        if self.options.add_header_to_export:
            lines.append(delimiter.join(["发送时间", "主机名", "响应IP", "状态", "耗时(ms)", "TTL", "计数"]))
        for r in records_to_export:
            lat_str = f"{r.latency_ms:.3f}" if r.latency_ms is not None else "--"
            ttl_str = str(r.ttl) if r.ttl is not None else "--"
            lines.append(delimiter.join([
                r.timestamp,
                r.target,
                r.resolved_ip,
                r.status,
                lat_str,
                ttl_str,
                str(r.sequence)
            ]))
        content = "\n".join(lines)

        # 仅比之前导出的文件有变化时导出
        if self.options.auto_export_only_on_change and content == self.last_exported_content:
            return

        target_file = self.options.auto_export_filename
        if "带数字计数器" in self.options.auto_export_counter_mode:
            base, ext = os.path.splitext(target_file)
            target_file = f"{base}_{self.export_file_counter:04d}{ext}"
            self.export_file_counter += 1

        try:
            os.makedirs(os.path.dirname(os.path.abspath(target_file)), exist_ok=True)
            mode = "a" if "追加" in self.options.auto_export_overwrite_mode else "w"
            with open(target_file, mode, encoding="utf-8") as f:
                f.write(content + "\n")
            self.last_exported_content = content
        except Exception as e:
            print(f"[警告] 自动导出下窗格流水失败 [{target_file}]: {e}", file=sys.stderr)

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
                    Exporter.export_csv(self.hosts, file_path, add_header=self.options.add_header_to_export)
                    QMessageBox.information(self, "成功", f"表格数据已成功导出至：\n{file_path}")
                except Exception as e:
                    QMessageBox.critical(self, "导出失败", f"生成 CSV 失败: {e}")

    def show_about(self):
        about_text = (
            f"<h2 style='color:#2563eb; margin-bottom:4px;'>YouQian PingView v{APP_VERSION}</h2>"
            "<p style='color:#64748b; font-size:12px;'>YouQian 批量网络监控工具 · 专为统信 UOS 与 Linux 深度定制</p>"
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
        QMessageBox.about(self, "关于 YouQian PingView", about_text)
