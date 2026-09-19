"""
统信 UOS 原生零依赖 Tkinter 图形界面引擎
当系统处于未激活或无法连接统信商业源 (401 Unauthorized) 无法安装 PyQt5 时，
自动无缝启动本引擎，确保 100% 开箱即用，免装任何外部依赖！
"""

import sys
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List, Optional

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from youqian_pingview.core.target_parser import TargetItem, parse_targets_text
    from youqian_pingview.core.pinger import HostStat, PingRecord, PingOptions, PingWorker
    from youqian_pingview.core.exporter import Exporter
    from youqian_pingview.core.constants import SAMPLE_TEXT, WINDOW_TITLE, APP_VERSION
    from youqian_pingview.core.config_manager import ConfigManager
except (ImportError, ModuleNotFoundError, ValueError):
    from core.target_parser import TargetItem, parse_targets_text
    from core.pinger import HostStat, PingRecord, PingOptions, PingWorker
    from core.exporter import Exporter
    from core.constants import SAMPLE_TEXT, WINDOW_TITLE, APP_VERSION
    from core.config_manager import ConfigManager


class TkOptionsDialog(tk.Toplevel):
    def __init__(self, parent, options: PingOptions):
        super().__init__(parent)
        self.title("Ping 探测选项设置")
        self.geometry("380x360")
        self.resizable(False, False)
        self.options = options
        self.init_ui()

    def init_ui(self):
        pad = {"padx": 10, "pady": 6}

        frame = ttk.LabelFrame(self, text="基础探测与告警参数", padding=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 轮询间隔
        ttk.Label(frame, text="探测间隔 (秒):").grid(row=0, column=0, sticky=tk.W, **pad)
        self.ent_interval = ttk.Spinbox(frame, from_=1, to=3600, width=10)
        self.ent_interval.set(self.options.interval_sec)
        self.ent_interval.grid(row=0, column=1, sticky=tk.E, **pad)

        # 超时时间
        ttk.Label(frame, text="单次超时 (毫秒):").grid(row=1, column=0, sticky=tk.W, **pad)
        self.ent_timeout = ttk.Spinbox(frame, from_=100, to=30000, increment=500, width=10)
        self.ent_timeout.set(self.options.timeout_ms)
        self.ent_timeout.grid(row=1, column=1, sticky=tk.E, **pad)

        # 数据包大小
        ttk.Label(frame, text="数据包大小 (字节):").grid(row=2, column=0, sticky=tk.W, **pad)
        self.ent_size = ttk.Spinbox(frame, from_=16, to=65500, width=10)
        self.ent_size.set(self.options.packet_size)
        self.ent_size.grid(row=2, column=1, sticky=tk.E, **pad)

        # 并发线程
        ttk.Label(frame, text="最大并发线程数:").grid(row=3, column=0, sticky=tk.W, **pad)
        self.ent_threads = ttk.Spinbox(frame, from_=1, to=200, width=10)
        self.ent_threads.set(self.options.max_threads)
        self.ent_threads.grid(row=3, column=1, sticky=tk.E, **pad)

        # 连续失败报警阈值
        ttk.Label(frame, text="连续失败报警阈值 (次):").grid(row=4, column=0, sticky=tk.W, **pad)
        self.ent_alarm = ttk.Spinbox(frame, from_=1, to=50, width=10)
        self.ent_alarm.set(self.options.alarm_fail_threshold)
        self.ent_alarm.grid(row=4, column=1, sticky=tk.E, **pad)

        # 按钮
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="保存设置", command=self.save_and_close).pack(side=tk.RIGHT, padx=5)

    def save_and_close(self):
        try:
            self.options.interval_sec = int(self.ent_interval.get())
            self.options.timeout_ms = int(self.ent_timeout.get())
            self.options.packet_size = int(self.ent_size.get())
            self.options.max_threads = int(self.ent_threads.get())
            self.options.alarm_fail_threshold = int(self.ent_alarm.get())
            self.destroy()
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字！")


class TkTargetDialog(tk.Toplevel):
    def __init__(self, parent, current_text: str, on_confirm_callback):
        super().__init__(parent)
        self.title("输入 Ping 目标地址列表")
        self.geometry("620x480")
        self.on_confirm = on_confirm_callback
        self.init_ui(current_text)

    def init_ui(self, initial_text: str):
        tip_frame = ttk.LabelFrame(self, text=" 格式与分组填写说明 ", padding=6)
        tip_frame.pack(fill=tk.X, padx=10, pady=(6, 2))

        ttk.Label(
            tip_frame,
            text="📌 目标格式：每行一个探测目标，格式为 IP/域名 描述说明 (支持 :80 端口、/24 网段与 1.1-1.20 范围)\n"
                 "📁 分组设置：单独起一行输入 Group: 分组名 或 分组: 分组名，下方地址自动归组 (支持主界面双击折叠)",
            justify=tk.LEFT
        ).pack(anchor=tk.W)

        self.txt_edit = tk.Text(self, wrap=tk.NONE, font=("Courier", 10), bg="#fafafa")
        self.txt_edit.insert("1.0", initial_text)
        self.txt_edit.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        btn_box = ttk.Frame(self, padding=8)
        btn_box.pack(fill=tk.X)

        ttk.Button(btn_box, text="从文件载入...", command=self.load_file).pack(side=tk.LEFT, padx=5)

        def insert_group_tk():
            self.txt_edit.insert(tk.INSERT, "\nGroup: 新分组名称\n")
            self.txt_edit.focus_set()

        ttk.Button(btn_box, text="➕ 插入分组模板", command=insert_group_tk).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_box, text="清空", command=lambda: self.txt_edit.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_box, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_box, text="解析并开始", command=self.confirm).pack(side=tk.RIGHT, padx=5)

    def load_file(self):
        path = filedialog.askopenfilename(filetypes=[("文本文件", "*.txt;*.ini;*.csv"), ("所有文件", "*.*")])
        if path:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                self.txt_edit.delete("1.0", tk.END)
                self.txt_edit.insert("1.0", content)
            except Exception as e:
                messagebox.showerror("错误", f"读取文件失败: {e}")

    def confirm(self):
        text = self.txt_edit.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("提示", "请输入至少一个有效的主机目标！")
            return
        items = parse_targets_text(text)
        if not items:
            messagebox.showwarning("提示", "未解析到有效地址，请检查格式！")
            return
        self.on_confirm(text, items)
        self.destroy()


class TkMainWindow:
    """Tkinter 原生双窗格主窗口"""
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.geometry("1120x680")
        self.root.minsize(800, 500)

        # 1. 加载配置与目标
        saved_cfg = ConfigManager.load_config()
        self.options = PingOptions.from_dict(saved_cfg.get("options", {}))

        if self.options.remember_targets and saved_cfg.get("targets_text"):
            self.target_raw_text = saved_cfg.get("targets_text")
        else:
            self.target_raw_text = SAMPLE_TEXT

        # 2. 动态窗口标题
        self.update_window_title()

        self.hosts: List[HostStat] = []
        self.is_running = False
        self.current_round_id: int = 0
        self.is_probing_round_active: bool = False
        self.selected_host_index: Optional[int] = None
        self.countdown_sec = 0

        self.init_menu()
        self.init_toolbar()
        self.init_split_view()
        self.init_statusbar()

        self.load_targets_data(self.target_raw_text)

        # 窗口关闭监听
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        if self.options.auto_start_ping and self.hosts:
            self.root.after(200, self.start_ping)

    def update_window_title(self):
        if self.options.custom_window_title:
            self.root.title(f"{self.options.custom_window_title} - {WINDOW_TITLE}")
        else:
            self.root.title(WINDOW_TITLE)

    def on_close(self):
        try:
            data = {
                "targets_text": self.target_raw_text if self.options.remember_targets else "",
                "options": self.options.to_dict()
            }
            ConfigManager.save_config(data)
        except Exception:
            pass
        self.stop_ping()
        self.root.destroy()

    def init_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # 文件
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="编辑目标地址列表 (F8)", command=self.open_target_dialog)
        file_menu.add_command(label="探测参数设置 (F9)", command=self.open_options_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="导出 HTML 报告", command=lambda: self.export_data("html"))
        file_menu.add_command(label="导出 CSV 表格", command=lambda: self.export_data("csv"))
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)
        menubar.add_cascade(label="文件(F)", menu=file_menu)

        # 控制
        ctrl_menu = tk.Menu(menubar, tearoff=0)
        ctrl_menu.add_command(label="开始 Ping (F5)", command=self.start_ping)
        ctrl_menu.add_command(label="停止 Ping (F6)", command=self.stop_ping)
        ctrl_menu.add_command(label="重置计数器", command=self.reset_all)
        menubar.add_cascade(label="控制(C)", menu=ctrl_menu)

        # 帮助
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="关于 Youqian-PingView", command=self.show_about)
        menubar.add_cascade(label="帮助(H)", menu=help_menu)

        # 快捷键绑定
        self.root.bind("<F5>", lambda e: self.start_ping())
        self.root.bind("<F6>", lambda e: self.stop_ping())
        self.root.bind("<F8>", lambda e: self.open_target_dialog())
        self.root.bind("<F9>", lambda e: self.open_options_dialog())

    def init_toolbar(self):
        tb = ttk.Frame(self.root, padding=4)
        tb.pack(fill=tk.X, side=tk.TOP)

        self.btn_start = ttk.Button(tb, text="▶ 开始 Ping", command=self.start_ping)
        self.btn_start.pack(side=tk.LEFT, padx=3)

        self.btn_stop = ttk.Button(tb, text="⏹ 停止", command=self.stop_ping, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=3)

        ttk.Button(tb, text="🔄 重置统计", command=self.reset_all).pack(side=tk.LEFT, padx=3)
        ttk.Separator(tb, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Button(tb, text="➕ 目标列表", command=self.open_target_dialog).pack(side=tk.LEFT, padx=3)
        ttk.Button(tb, text="⚙ 探测设置", command=self.open_options_dialog).pack(side=tk.LEFT, padx=3)
        ttk.Button(tb, text="🔤 排序 (AZ)", command=lambda: self.sort_by_column("index")).pack(side=tk.LEFT, padx=3)
        ttk.Button(tb, text="📊 导出报表", command=lambda: self.export_data("html")).pack(side=tk.LEFT, padx=3)
        ttk.Separator(tb, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        # 筛选模式
        ttk.Label(tb, text="筛选:").pack(side=tk.LEFT, padx=3)
        self.combo_filter = ttk.Combobox(tb, values=["显示全部", "仅显示存活", "仅显示失败/异常"], width=12, state="readonly")
        self.combo_filter.current(0)
        self.combo_filter.pack(side=tk.LEFT, padx=3)
        self.combo_filter.bind("<<ComboboxSelected>>", lambda e: self.apply_filter())

        # 搜索过滤
        ttk.Label(tb, text="搜索:").pack(side=tk.LEFT, padx=3)
        self.ent_search = ttk.Entry(tb, width=16)
        self.ent_search.pack(side=tk.LEFT, padx=3)
        self.ent_search.bind("<KeyRelease>", lambda e: self.apply_filter())

    def init_split_view(self):
        paned = tk.PanedWindow(self.root, orient=tk.VERTICAL, sashrelief=tk.RAISED, sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)

        # 上窗格
        frame_upper = ttk.Frame(paned)
        paned.add(frame_upper, height=420)

        # 上表格 Treeview (22 列对齐原版)
        upper_cols = (
            "status", "index", "target", "resolved_ip", "reply_ip", "success", "failed",
            "consec_fail", "max_consec_fail", "max_consec_time", "fail_rate", "total_sent",
            "last_status", "last_time", "last_ttl", "avg_lat", "desc", "last_succ_time",
            "last_failed_time", "min_lat", "max_lat", "disabled", "mac"
        )
        self.tree_upper = ttk.Treeview(frame_upper, columns=upper_cols, show="headings", selectmode="browse")
        self.tree_upper.bind("<Button-3>", self.show_upper_menu)

        headers_def = [
            ("status", "状态", 60), ("index", "序号", 45), ("target", "主机名", 130),
            ("resolved_ip", "IP 地址", 110), ("reply_ip", "响应 IP 地址", 110),
            ("success", "成功次数", 60), ("failed", "失败次数", 60),
            ("consec_fail", "连续失败次数", 80), ("max_consec_fail", "最大连续失败次数", 100),
            ("max_consec_time", "最大连续失败时间", 125), ("fail_rate", "失败率(%)", 65),
            ("total_sent", "总计发送Pings数", 95), ("last_status", "最后 Ping 状态", 85),
            ("last_time", "最后 Ping 时间", 85), ("last_ttl", "最后 Ping TTL", 75),
            ("avg_lat", "平均 Ping 时间", 85), ("desc", "描述", 140),
            ("last_succ_time", "最后成功时间", 125), ("last_failed_time", "最后失败时间", 125),
            ("min_lat", "最小Ping时间", 80), ("max_lat", "最大Ping时间", 80),
            ("disabled", "禁用", 50), ("mac", "MAC 地址", 120)
        ]
        for col_id, col_name, width in headers_def:
            self.tree_upper.heading(col_id, text=col_name, command=lambda c=col_id: self.sort_by_column(c))
            self.tree_upper.column(col_id, width=width, anchor=tk.CENTER if col_id not in ("target", "desc") else tk.W)

        # 滚动条
        scroll_y1 = ttk.Scrollbar(frame_upper, orient=tk.VERTICAL, command=self.tree_upper.yview)
        scroll_x1 = ttk.Scrollbar(frame_upper, orient=tk.HORIZONTAL, command=self.tree_upper.xview)
        self.tree_upper.configure(yscrollcommand=scroll_y1.set, xscrollcommand=scroll_x1.set)

        self.tree_upper.grid(row=0, column=0, sticky="nsew")
        scroll_y1.grid(row=0, column=1, sticky="ns")
        scroll_x1.grid(row=1, column=0, sticky="ew")
        frame_upper.rowconfigure(0, weight=1)
        frame_upper.columnconfigure(0, weight=1)

        self.tree_upper.bind("<<TreeviewSelect>>", self.on_upper_select)

        # 标签样式：成功绿色高亮，失败浅红背景
        self.tree_upper.tag_configure("success", foreground="#16a34a")
        self.tree_upper.tag_configure("fail", background="#fee2e2", foreground="#dc2626")
        self.tree_upper.tag_configure("idle", foreground="#64748b")

        # 下窗格
        frame_lower = ttk.Frame(paned)
        paned.add(frame_lower, height=180)

        self.lbl_lower_title = ttk.Label(frame_lower, text="选中主机的历史明细流水 (请在上表中点击选择某主机):", padding=2)
        self.lbl_lower_title.pack(anchor=tk.W)

        lower_cols = ("time", "resp_ip", "lat", "ttl", "status", "seq")
        self.tree_lower = ttk.Treeview(frame_lower, columns=lower_cols, show="headings", selectmode="browse")

        lower_headers = [
            ("time", "发送时间", 140), ("resp_ip", "响应 IP 地址", 120),
            ("lat", "Ping 时间", 80), ("ttl", "Ping 衰减", 60),
            ("status", "Ping 状态", 100), ("seq", "Ping 计数", 60)
        ]
        for col_id, col_name, width in lower_headers:
            self.tree_lower.heading(col_id, text=col_name)
            self.tree_lower.column(col_id, width=width, anchor=tk.CENTER)

        scroll_y2 = ttk.Scrollbar(frame_lower, orient=tk.VERTICAL, command=self.tree_lower.yview)
        self.tree_lower.configure(yscrollcommand=scroll_y2.set)
        self.tree_lower.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y2.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree_lower.tag_configure("fail", background="#fee2e2", foreground="#dc2626")

    def init_statusbar(self):
        self.status_bar = ttk.Frame(self.root, padding=2)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_status = ttk.Label(self.status_bar, text="状态: 空闲待命")
        self.lbl_status.pack(side=tk.LEFT, padx=5)

        self.lbl_summary = ttk.Label(self.status_bar, text="监控: 0 | 存活: 0 | 异常: 0")
        self.lbl_summary.pack(side=tk.RIGHT, padx=10)

        self.lbl_timer = ttk.Label(self.status_bar, text="下次探测: --")
        self.lbl_timer.pack(side=tk.RIGHT, padx=10)

    def load_targets_data(self, text: str):
        self.current_round_id += 1  # 切换目标清单，使所有旧在途探测回调立即作废
        self.is_probing_round_active = False
        self.target_raw_text = text
        items = parse_targets_text(
            text,
            skip_first=self.options.cidr_skip_first,
            skip_last=self.options.cidr_skip_last,
            use_ip_host_format=self.options.use_ip_host_format
        )

        if not self.options.allow_ipv6:
            import ipaddress
            filtered_items = []
            for it in items:
                try:
                    if ipaddress.ip_address(it.target).version == 6:
                        continue
                except ValueError:
                    pass
                filtered_items.append(it)
            items = filtered_items

        self.hosts = []
        for idx, it in enumerate(items, start=1):
            self.hosts.append(HostStat(idx, it.target, it.description, it.port, group=it.group))
        self.refresh_upper_table()
        self.update_summary()

    def refresh_upper_table(self):
        self.tree_upper.delete(*self.tree_upper.get_children())
        kw = self.ent_search.get().strip().lower()
        filter_mode = self.combo_filter.current() if hasattr(self, 'combo_filter') else 0

        for idx, host in enumerate(self.hosts):
            if kw:
                c_str = f"{host.target} {host.resolved_ip} {host.description} {host.group}".lower()
                if kw not in c_str:
                    continue

            # 过滤逻辑：
            if not host.enabled:
                # 在仅显示失败或仅显示存活模式下，禁用项直接隐藏
                if filter_mode in (1, 2):
                    continue
            else:
                if filter_mode == 1 and host.last_status not in ("成功", "端口开放"):
                    continue
                elif filter_mode == 2 and (host.total_sent == 0 or host.last_status in ("成功", "端口开放")):
                    continue

            # 状态灯符号
            if not host.enabled:
                st_icon = "⚪ 禁用"
                tag = "idle"
            elif host.total_sent == 0:
                st_icon = "⚪ 待命"
                tag = "idle"
            elif host.last_status in ("成功", "端口开放"):
                st_icon = "🟢 正常"
                tag = "success"
            else:
                st_icon = "🔴 异常"
                tag = "fail"

            vals = (
                st_icon,
                host.index,
                f"{host.target}:{host.port}" if host.port else host.target,
                host.resolved_ip or "--",
                host.reply_ip or host.resolved_ip or "--",
                host.success_count,
                host.failed_count,
                host.consecutive_failures,
                host.max_consecutive_failures,
                host.max_consecutive_failure_time or "--",
                f"{host.failure_rate:.1f}%",
                host.total_sent,
                host.last_status,
                f"{host.last_latency_ms:.3f}" if host.last_latency_ms is not None else "--",
                host.last_ttl if host.last_ttl is not None else "--",
                f"{host.avg_latency_ms:.3f}" if host.avg_latency_ms is not None else "--",
                host.description or "",
                host.last_success_time or "--",
                host.last_failed_time or "--",
                f"{host.min_latency_ms:.3f}" if host.min_latency_ms is not None else "--",
                f"{host.max_latency_ms:.3f}" if host.max_latency_ms is not None else "--",
                "是" if not host.enabled else "否",
                host.mac_address or "--"
            )
            self.tree_upper.insert("", tk.END, iid=str(idx), values=vals, tags=(tag,))

    def apply_filter(self):
        self.refresh_upper_table()

    def show_upper_menu(self, event):
        row_id = self.tree_upper.identify_row(event.y)
        if not row_id:
            return
        self.tree_upper.selection_set(row_id)
        idx = int(row_id)
        host = self.hosts[idx]

        menu = tk.Menu(self.root, tearoff=0)
        toggle_label = "禁用此项探测 (从失败列表中隐藏)" if host.enabled else "启用此项探测"
        menu.add_command(label=toggle_label, command=lambda: self.toggle_host(idx))
        menu.post(event.x_root, event.y_root)

    def toggle_host(self, idx: int):
        self.hosts[idx].enabled = not self.hosts[idx].enabled
        self.refresh_upper_table()

    def on_upper_select(self, event):
        selected = self.tree_upper.selection()
        if not selected:
            return
        idx = int(selected[0])
        if 0 <= idx < len(self.hosts):
            self.selected_host_index = idx
            host = self.hosts[idx]
            self.lbl_lower_title.config(text=f"主机 [{host.target}] 探测流水记录 (共 {len(host.history_records)} 条)：")
            self.refresh_lower_table(host)

    def refresh_lower_table(self, host: HostStat):
        self.tree_lower.delete(*self.tree_lower.get_children())
        for rec in reversed(host.history_records):
            tag = "fail" if rec.status not in ("成功", "端口开放") else ""
            vals = (
                rec.timestamp,
                rec.resolved_ip or rec.target or "--",
                f"{rec.latency_ms:.3f}" if rec.latency_ms is not None else "--",
                rec.ttl if rec.ttl is not None else "--",
                rec.status,
                rec.sequence
            )
            self.tree_lower.insert("", tk.END, values=vals, tags=(tag,) if tag else ())

    def sort_by_column(self, col_id: str):
        """点击表头按该列排序，再点一下反序"""
        if not hasattr(self, "_sort_col"):
            self._sort_col = None
            self._sort_desc = False

        if self._sort_col == col_id:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col_id
            self._sort_desc = False

        def get_k(h: HostStat):
            if col_id == "index": return h.index
            elif col_id == "target": return h.target.lower()
            elif col_id == "resolved_ip": return h.resolved_ip or ""
            elif col_id == "reply_ip": return h.reply_ip or h.resolved_ip or ""
            elif col_id == "success": return h.success_count
            elif col_id == "failed": return h.failed_count
            elif col_id == "consec_fail": return h.consecutive_failures
            elif col_id == "max_consec_fail": return h.max_consecutive_failures
            elif col_id == "max_consec_time": return h.max_consecutive_failure_time or ""
            elif col_id == "fail_rate": return h.failure_rate
            elif col_id == "total_sent": return h.total_sent
            elif col_id == "last_status": return h.last_status
            elif col_id == "last_time": return (1, 0) if h.last_latency_ms is None else (0, h.last_latency_ms)
            elif col_id == "last_ttl": return (1, 0) if h.last_ttl is None else (0, h.last_ttl)
            elif col_id == "avg_lat": return (1, 0) if h.avg_latency_ms is None else (0, h.avg_latency_ms)
            elif col_id == "desc": return (h.description or "").lower()
            elif col_id == "last_succ_time": return h.last_success_time or ""
            elif col_id == "last_failed_time": return h.last_failed_time or ""
            elif col_id == "min_lat": return (1, 0) if h.min_latency_ms is None else (0, h.min_latency_ms)
            elif col_id == "max_lat": return (1, 0) if h.max_latency_ms is None else (0, h.max_latency_ms)
            elif col_id == "disabled": return 1 if not h.enabled else 0
            elif col_id == "mac": return h.mac_address or ""
            return h.index

        self.hosts.sort(key=get_k, reverse=self._sort_desc)
        self.refresh_upper_table()

    def start_ping(self):
        if not self.hosts:
            messagebox.showwarning("提示", "当前无探测目标，请先添加！")
            return
        self.is_running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.lbl_status.config(text="状态: 正在并发探测中...")
        self.run_probe_round()

    def stop_ping(self):
        self.is_running = False
        self.current_round_id += 1  # 轮次递增，使在途旧任务失效
        self.is_probing_round_active = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.lbl_status.config(text="状态: 已停止")
        self.lbl_timer.config(text="下次探测: 已停止")

    def run_probe_round(self, is_manual_single: bool = False):
        if not self.is_running and not is_manual_single:
            return

        if self.is_probing_round_active:
            # 互斥保护，防止多轮重入
            return

        self.is_probing_round_active = True
        self.current_round_id += 1
        this_round = self.current_round_id

        self.lbl_status.config(text="状态: 正在发送 Ping 探测包...")
        timeout_ms = self.options.timeout_ms
        pkt_size = self.options.packet_size
        targets_snapshot = [(h.host_id, h) for h in self.hosts if h.enabled]
        max_workers = min(self.options.max_threads, len(targets_snapshot) or 1)

        def worker():
            if targets_snapshot:
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    futures = []
                    for hid, h in targets_snapshot:
                        futures.append(pool.submit(self._probe_single, this_round, hid, h, timeout_ms, pkt_size))
                    for f in futures:
                        try:
                            f.result()
                        except Exception:
                            pass

            # 一轮结束回到主线程调度
            self.root.after(0, lambda: self.on_round_done(this_round))

        threading.Thread(target=worker, daemon=True).start()

    def _probe_single(self, round_id: int, host_id: str, host: HostStat, timeout_ms: int, pkt_size: int):
        succ, lat, ttl, status_str, resp_ip = PingWorker.probe(
            host,
            timeout_ms,
            pkt_size,
            custom_ttl_enabled=self.options.custom_ttl_enabled,
            custom_ttl=self.options.custom_ttl,
            dont_fragment=self.options.dont_fragment,
            source_ipv4=self.options.source_ipv4,
            source_ipv6=self.options.source_ipv6,
            resolve_dns_every_ping=self.options.resolve_dns_every_ping
        )
        self.root.after(0, lambda: self.on_single_result(round_id, host_id, succ, lat, ttl, status_str, resp_ip))

    def on_single_result(self, round_id: int, host_id: str, succ: bool, lat, ttl, status_str: str, resp_ip: str):
        if round_id != self.current_round_id:
            return

        host = None
        for h in self.hosts:
            if h.host_id == host_id:
                host = h
                break

        if not host:
            return

        host.update_result(succ, lat, ttl, status_str, resp_ip)
        # 告警声音
        if not succ and self.options.alarm_on_fail:
            if host.consecutive_failures == self.options.alarm_fail_threshold:
                self.root.bell()
        # 核心特性：在筛选视图下（如仅显示失败），一旦有新的探测结果，立即毫秒级刷新表格呈现！
        filter_mode = self.combo_filter.current() if hasattr(self, 'combo_filter') else 0
        if filter_mode != 0:
            self.refresh_upper_table()

    def on_round_done(self, round_id: int):
        if round_id != self.current_round_id:
            return

        self.is_probing_round_active = False
        self.refresh_upper_table()
        if self.selected_host_index is not None and 0 <= self.selected_host_index < len(self.hosts):
            self.refresh_lower_table(self.hosts[self.selected_host_index])
        self.update_summary()

        if self.is_running:
            if not self.options.auto_repeat:
                self.stop_ping()
                self.lbl_status.config(text="状态: 单次探测已完成")
                self.lbl_timer.config(text="下次探测: 已结束")
                return

            self.lbl_status.config(text="状态: 本轮探测完成，等待下一轮")
            self.countdown_sec = self.options.interval_sec
            self.tick_countdown()
        else:
            self.lbl_status.config(text="状态: 手动探测完成")
            self.lbl_timer.config(text="下次探测: 已停止")

    def tick_countdown(self):
        if not self.is_running:
            return
        if self.countdown_sec > 0:
            self.lbl_timer.config(text=f"下次探测: {self.countdown_sec} 秒后")
            self.countdown_sec -= 1
            self.root.after(1000, self.tick_countdown)
        else:
            self.run_probe_round()

    def update_summary(self):
        total = len(self.hosts)
        alive = sum(1 for h in self.hosts if h.last_status in ("成功", "端口开放"))
        down = sum(1 for h in self.hosts if h.total_sent > 0 and h.last_status not in ("成功", "端口开放"))
        self.lbl_summary.config(text=f"监控: {total} | 存活: {alive} | 异常: {down}")

    def reset_all(self):
        for h in self.hosts:
            h.reset_stats()
        self.refresh_upper_table()
        self.tree_lower.delete(*self.tree_lower.get_children())
        self.update_summary()

    def open_target_dialog(self):
        was_running = self.is_running
        if was_running:
            self.stop_ping()

        def on_confirm(raw_text, parsed_items):
            self.current_round_id += 1
            self.is_probing_round_active = False
            self.target_raw_text = raw_text
            self.hosts = []
            for idx, it in enumerate(parsed_items, start=1):
                self.hosts.append(HostStat(idx, it.target, it.description, it.port, group=it.group))
            self.refresh_upper_table()
            self.update_summary()
            if was_running:
                self.start_ping()

        TkTargetDialog(self.root, self.target_raw_text, on_confirm)

    def open_options_dialog(self):
        TkOptionsDialog(self.root, self.options)

    def export_data(self, file_type: str = "html"):
        if not self.hosts:
            messagebox.showwarning("提示", "当前无数据可导出！")
            return
        if file_type == "html":
            path = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML网页", "*.html")])
            if path:
                try:
                    Exporter.export_html(self.hosts, path)
                    messagebox.showinfo("成功", f"报表已成功导出至:\n{path}")
                except Exception as e:
                    messagebox.showerror("错误", f"导出失败: {e}")
        elif file_type == "csv":
            path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV表格", "*.csv")])
            if path:
                try:
                    Exporter.export_csv(self.hosts, path)
                    messagebox.showinfo("成功", f"数据已成功导出至:\n{path}")
                except Exception as e:
                    messagebox.showerror("错误", f"导出失败: {e}")

    def show_about(self):
        messagebox.showinfo(
            "关于 YouQian PingView",
            f"YouQian PingView v{APP_VERSION}\n"
            "YouQian 批量网络监控工具 (统信 UOS / Linux 专版)\n\n"
            "完全对标 NirSoft PingInfoView 功能与经典双窗格体验。\n"
            "支持免 Root 多并发探测、CIDR 网段展开与 HTML/CSV 报表导出。\n\n"
            "深度适配统信 UOS 桌面操作系统。"
        )


def launch_tk_ui():
    """Tkinter 引擎启动器"""
    root = tk.Tk()
    app = TkMainWindow(root)
    root.mainloop()
