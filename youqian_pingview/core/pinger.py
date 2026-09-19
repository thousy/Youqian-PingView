"""
Ping 探测引擎与状态统计核心模块
兼容统信 UOS / Linux 系统的原生探测 (无需 root 权限)
同时兼顾本地调试环境跨平台兼容
"""

import ipaddress
import platform
import re
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import uuid
from typing import Optional, List, Dict, Callable, Tuple


class PingRecord:
    """单次 Ping 探测记录 (用于下窗格明细)"""
    def __init__(self, sequence: int, target: str, resolved_ip: str,
                 latency_ms: Optional[float], ttl: Optional[int],
                 status: str, timestamp: Optional[str] = None):
        self.sequence = sequence
        self.target = target
        self.resolved_ip = resolved_ip
        self.latency_ms = latency_ms
        self.ttl = ttl
        self.status = status
        self.timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "target": self.target,
            "resolved_ip": self.resolved_ip,
            "latency_ms": f"{self.latency_ms:.2f}" if self.latency_ms is not None else "--",
            "ttl": str(self.ttl) if self.ttl is not None else "--",
            "status": self.status,
        }


def get_mac_address(ip: str) -> str:
    """尝试从系统 ARP 缓存中获取局域网主机的 MAC 地址 (非阻塞)"""
    if not ip or ip.startswith("127.") or ip == "::1":
        return ""

    import os
    # 1. Linux 首选高效读取 /proc/net/arp
    if os.path.exists("/proc/net/arp"):
        try:
            with open("/proc/net/arp", "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 4 and parts[0] == ip:
                    mac = parts[3].upper()
                    if mac != "00:00:00:00:00:00":
                        return mac.replace(":", "-")
        except Exception:
            pass

    # 2. 备用调用 arp 命令
    try:
        cmd = ["arp", "-n", ip] if platform.system().lower() != "windows" else ["arp", "-a", ip]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=0.8)
        match = re.search(r"([0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2})", res.stdout)
        if match:
            mac = match.group(1).upper().replace(":", "-")
            if mac != "00-00-00-00-00-00":
                return mac
    except Exception:
        pass

    return ""


def resolve_netbios_name(ip: str, timeout: float = 0.6) -> Optional[str]:
    """尝试通过 NetBIOS (UDP 137) 嗅探局域网 Windows/Linux 计算机名"""
    try:
        req = (
            b'\x80\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00'
            b'\x20CKAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\x00'
            b'\x00\x21\x00\x01'
        )
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        try:
            s.sendto(req, (ip, 137))
            data, _ = s.recvfrom(1024)
            if len(data) > 57:
                num_names = data[56]
                if num_names > 0:
                    name_bytes = data[57:57+15]
                    name = name_bytes.decode('gbk', errors='ignore').strip()
                    if name and not name.startswith('\x00'):
                        return name
        finally:
            s.close()
    except Exception:
        pass
    return None


def resolve_reverse_dns(ip: str) -> Optional[str]:
    """尝试通过反向 DNS PTR 解析主机名"""
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        if hostname and hostname != ip:
            return hostname
    except Exception:
        pass
    return None


def resolve_host_name(ip: str) -> Optional[str]:
    """
    综合反向解析主机名：
    1. 若本身即为域名或主机名，直接返回
    2. 针对纯 IP，局域网私有网段优先尝试 NetBIOS 嗅探真实计算机名
    3. 公网 IP 优先反查 DNS PTR 域名
    """
    if not ip:
        return None
    if ip.startswith("127.") or ip == "::1":
        try:
            return socket.gethostname() or "localhost"
        except Exception:
            return "localhost"
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return ip

    # 局域网私有地址优先尝试 NetBIOS
    if ip_obj.is_private:
        nb = resolve_netbios_name(ip, timeout=0.6)
        if nb:
            return nb

    # 反向 DNS PTR 解析
    dns = resolve_reverse_dns(ip)
    if dns:
        return dns

    # 兜底再次尝试 NetBIOS
    if not ip_obj.is_private:
        nb = resolve_netbios_name(ip, timeout=0.4)
        if nb:
            return nb

    return None


class HostStat:
    """单个主机的汇总统计数据 (用于上窗格主监控表)"""
    def __init__(self, index: int, target: str, description: str = "", port: Optional[int] = None, host_id: Optional[str] = None, group: str = ""):
        self.index = index
        self.target = target
        self.description = description
        self.port = port
        self.group = group.strip()
        self.enabled = True
        self.host_id = host_id or uuid.uuid4().hex

        # 主机名：若 target 本身是域名/主机名则默认为 target；若 target 是纯 IP 则初始为空，待反向解析后更新
        is_pure_ip = False
        try:
            ipaddress.ip_address(self.target)
            is_pure_ip = True
        except ValueError:
            pass
        self.hostname = "" if is_pure_ip else self.target

        self.resolved_ip = ""
        self.reply_ip = ""
        self.mac_address = ""
        self.success_count = 0
        self.failed_count = 0
        self.total_sent = 0

        self.last_status = "未开始"
        self.last_latency_ms: Optional[float] = None
        self.avg_latency_ms: Optional[float] = None
        self.min_latency_ms: Optional[float] = None
        self.max_latency_ms: Optional[float] = None
        self.last_ttl: Optional[int] = None

        self._total_latency = 0.0
        self._latency_samples_count = 0  # 有效延迟样本数，防止分母失真
        self.last_success_time = ""
        self.last_failed_time = ""
        self.consecutive_failures = 0
        self.max_consecutive_failures = 0
        self.max_consecutive_failure_time = ""
        self.consecutive_successes: int = 0
        self.had_previous_failure: bool = False

        # 存放最近的 N 条探测流水记录
        self.history_records: List[PingRecord] = []
        self.max_history = 200

    @property
    def failure_rate(self) -> float:
        if self.total_sent == 0:
            return 0.0
        return (self.failed_count / self.total_sent) * 100.0

    def reset_stats(self):
        """重置统计数据"""
        self.success_count = 0
        self.failed_count = 0
        self.total_sent = 0
        self.last_status = "未开始"
        self.last_latency_ms = None
        self.avg_latency_ms = None
        self.min_latency_ms = None
        self.max_latency_ms = None
        self.last_ttl = None
        self._total_latency = 0.0
        self._latency_samples_count = 0
        self.last_success_time = ""
        self.last_failed_time = ""
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.had_previous_failure = False
        self.max_consecutive_failures = 0
        self.max_consecutive_failure_time = ""
        self.history_records.clear()

    def update_result(self, is_success: bool, latency: Optional[float], ttl: Optional[int],
                      status_msg: str, resolved_ip: str,
                      lower_pane_mode: str = "添加所有 pings 到下窗格",
                      max_accumulated: int = 50000) -> PingRecord:
        """记录探测结果并更新累加统计值，支持下窗格模式过滤与上限限制"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prev_status = self.last_status
        self.total_sent += 1
        if resolved_ip:
            self.resolved_ip = resolved_ip
            self.reply_ip = resolved_ip

        if is_success:
            self.success_count += 1
            self.consecutive_failures = 0
            self.consecutive_successes += 1
            self.last_success_time = now_str
            self.last_status = status_msg or "成功"
            self.last_latency_ms = latency
            self.last_ttl = ttl

            # 探测成功时若尚未获取 MAC 地址，尝试嗅探
            if not self.mac_address and self.resolved_ip:
                self.mac_address = get_mac_address(self.resolved_ip)

            if latency is not None:
                self._total_latency += latency
                self._latency_samples_count += 1
                self.avg_latency_ms = self._total_latency / self._latency_samples_count
                if self.min_latency_ms is None or latency < self.min_latency_ms:
                    self.min_latency_ms = latency
                if self.max_latency_ms is None or latency > self.max_latency_ms:
                    self.max_latency_ms = latency
        else:
            self.failed_count += 1
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            self.had_previous_failure = True
            self.last_failed_time = now_str
            if self.consecutive_failures > self.max_consecutive_failures:
                self.max_consecutive_failures = self.consecutive_failures
                self.max_consecutive_failure_time = now_str
            self.last_status = status_msg or "请求超时"
            self.last_latency_ms = None

        record = PingRecord(
            sequence=self.total_sent,
            target=self.target,
            resolved_ip=self.resolved_ip or self.target,
            latency_ms=latency,
            ttl=ttl,
            status=self.last_status,
            timestamp=now_str
        )

        # 下窗格流水记录过滤
        should_add = True
        if lower_pane_mode == "不添加 pings 到下窗格":
            should_add = False
        elif "仅添加失败" in lower_pane_mode:
            should_add = not is_success
        elif "仅添加成功" in lower_pane_mode:
            should_add = is_success
        elif "更改添加" in lower_pane_mode or "状态的每个更改" in lower_pane_mode:
            should_add = (self.last_status != prev_status)

        if should_add:
            self.history_records.append(record)
            limit = max_accumulated if max_accumulated > 0 else self.max_history
            if len(self.history_records) > limit:
                self.history_records.pop(0)

        return record


class PingOptions:
    """Ping 探测全局设置 (对标原版 PingInfoView 完整功能集合)"""
    def __init__(self):
        # 基础探测
        self.interval_sec: int = 1         # 轮询间隔 (秒)
        self.timeout_ms: int = 1000        # 超时时间 (毫秒)
        self.packet_size: int = 32         # 数据包大小 (字节)
        self.max_threads: int = 50         # 并发探测线程上限
        self.alarm_on_fail: bool = True    # 连续失败告警
        self.alarm_fail_threshold: int = 3 # 连续失败报警阈值
        self.limit_history_count: int = 200 # 下窗格保留记录数

        # 高级与原版扩展特性
        self.auto_repeat: bool = True               # [√] 重复间隔 (取消勾选则只探测一次停止)
        self.remember_targets: bool = True         # [√] 记住地址列表
        self.use_ip_host_format: bool = True       # [ ] 使用 IP-Host 描述格式
        self.auto_start_ping: bool = False         # [ ] 不显示对话框立刻开始 Pinging
        self.resolve_dns_every_ping: bool = False  # [ ] 每次 ping 时解析主机名为 IP 地址
        
        # IP 高级选项
        self.custom_ttl_enabled: bool = False      # [ ] IP 选项开关
        self.custom_ttl: int = 64                  # 有效时间 (TTL)
        self.dont_fragment: bool = False           # [ ] 禁止分段 (DF)

        # CIDR 展开选项
        self.cidr_skip_first: bool = False         # [ ] 跳过第一个地址 (网络号)
        self.cidr_skip_last: bool = True           # [√] 跳过最后一个地址 (广播号)

        # 窗口与源地址
        self.custom_window_title: str = ""         # 窗口标题
        self.source_ipv4: str = ""                 # 源 IPv4 地址
        self.allow_ipv6: bool = True               # [√] 允许 IPv6 地址
        self.source_ipv6: str = ""                 # 源 IPv6 地址 (可选)
        self.resolve_addresses: bool = True        # [√] 解析地址 (反向解析主机名)

        # ===== 高级选项 (Advanced Options) =====
        self.max_concurrent_pings: int = 100       # 同时Ping的最大数量
        
        # 失败告警与命令
        self.failed_sound_type: str = "信息声"       # 失败声音类型 (简单声/默认声/询问声/信息声/警告声/错误声/播放 WAV/MP3 文件)
        self.failed_audio_path: str = ""           # 音频文件路径
        self.use_failed_cmd: bool = False          # 在失败的 ping 执行下列命令
        self.failed_cmd: str = ""                  # 失败命令
        self.consecutive_failed_trigger: int = 1   # 连续失败 pings 数时触发命令失败/声音警报

        # 成功告警与命令
        self.success_sound_type: str = "播放 WAV/MP3 文件" # 成功声音类型
        self.success_audio_path: str = ""          # 成功音频文件路径
        self.use_success_cmd: bool = False         # 在 ping 成功时执行以下命令(上次失败后)
        self.success_cmd: str = ""                 # 成功命令
        self.consecutive_success_trigger: int = 1  # 连续成功 ping 触发成功声音警报的次数

        # 日志文件
        self.log_pings: bool = False               # 添加 Ping 结果到下列日志文件
        self.log_filename: str = ""                # 日志文件名
        self.log_file_type: str = "逗号分隔的文本文件" # 逗号分隔的文本文件 / 制表符分隔的文本文件 / HTML 文件
        self.log_pings_mode: str = "记录所有 pings"   # 记录所有 pings / 仅记录失败的 pings / 仅记录成功的 pings

        # 下窗格控制
        self.lower_pane_mode: str = "添加所有 pings 到下窗格" # 添加所有 pings 到下窗格 / 仅添加失败的 pings / 仅添加成功的 pings / 为 ping 状态的每个更改添加 ping 行 / 不添加 pings 到下窗格
        self.limit_accumulated_pings: bool = True  # 限制累积 ping 的总数
        self.max_accumulated_pings: int = 50000    # 累积 ping 上限

        # 自动导出
        self.auto_export: bool = False             # 自动导出下窗格的所有项目到文件每...
        self.auto_export_interval: int = 30        # 导出间隔 (秒)
        self.auto_export_file_type: str = "逗号分隔的文本文件"
        self.auto_export_filename: str = ""
        self.auto_export_only_on_change: bool = False # 仅比之前导出的文件有变化时导出的文件
        self.auto_export_overwrite_mode: str = "总是覆盖以前的文件" # 总是覆盖以前的文件 / 追加到现有文件
        self.auto_export_counter_mode: str = "创建带数字计数器的文件名"

        # ===== 原版“选项”菜单全套功能配置 =====
        self.display_mode: str = "显示所有 Hosts"   # 显示所有 Hosts / 仅显示失败的 Hosts / 仅显示成功的 Hosts
        self.high_resolution_timer: bool = True     # [√] 高分辨率 ping 时间
        self.show_gmt_time: bool = False            # [ ] 以 GMT 格式显示时间
        self.mark_failed_pings: bool = True         # [√] 标记失败 Pings (高亮淡红底色)
        self.always_on_top: bool = False            # [ ] 总在最前
        self.beep_on_failed: bool = False           # [ ] 当 Ping 失败时发出哔声
        self.beep_on_success: bool = False          # [ ] 成功 ping 时发出蜂鸣音(失败后)
        self.tray_icon_enabled: bool = False        # [ ] 在托盘上放置图标
        self.start_as_hidden: bool = False          # [ ] 启动时隐藏
        self.show_lower_pane: bool = True           # [√] 显示下窗格
        self.auto_scroll_lower_pane: bool = True    # [√] 自动滚动下窗格
        self.sort_on_every_update: bool = False     # [ ] 刷新后自动排序
        self.add_header_to_export: bool = True      # [√] 添加标题行到 CSV/Tab 分隔的文件
        self.custom_font_family: str = ""           # 表格自定义字体
        self.custom_font_size: int = 9              # 表格字号

    def to_dict(self) -> dict:
        return {
            "interval_sec": self.interval_sec,
            "timeout_ms": self.timeout_ms,
            "packet_size": self.packet_size,
            "max_threads": self.max_concurrent_pings,
            "alarm_on_fail": self.alarm_on_fail,
            "alarm_fail_threshold": self.alarm_fail_threshold,
            "limit_history_count": self.limit_history_count,
            "auto_repeat": self.auto_repeat,
            "remember_targets": self.remember_targets,
            "use_ip_host_format": self.use_ip_host_format,
            "auto_start_ping": self.auto_start_ping,
            "resolve_dns_every_ping": self.resolve_dns_every_ping,
            "custom_ttl_enabled": self.custom_ttl_enabled,
            "custom_ttl": self.custom_ttl,
            "dont_fragment": self.dont_fragment,
            "cidr_skip_first": self.cidr_skip_first,
            "cidr_skip_last": self.cidr_skip_last,
            "custom_window_title": self.custom_window_title,
            "source_ipv4": self.source_ipv4,
            "allow_ipv6": self.allow_ipv6,
            "source_ipv6": self.source_ipv6,
            "resolve_addresses": self.resolve_addresses,
            # 原版选项子菜单特性
            "display_mode": self.display_mode,
            "high_resolution_timer": self.high_resolution_timer,
            "show_gmt_time": self.show_gmt_time,
            "mark_failed_pings": self.mark_failed_pings,
            "always_on_top": self.always_on_top,
            "beep_on_failed": self.beep_on_failed,
            "beep_on_success": self.beep_on_success,
            "tray_icon_enabled": self.tray_icon_enabled,
            "start_as_hidden": self.start_as_hidden,
            "show_lower_pane": self.show_lower_pane,
            "auto_scroll_lower_pane": self.auto_scroll_lower_pane,
            "sort_on_every_update": self.sort_on_every_update,
            "add_header_to_export": self.add_header_to_export,
            "custom_font_family": self.custom_font_family,
            "custom_font_size": self.custom_font_size,
            # 高级选项
            "max_concurrent_pings": self.max_concurrent_pings,
            "failed_sound_type": self.failed_sound_type,
            "failed_audio_path": self.failed_audio_path,
            "use_failed_cmd": self.use_failed_cmd,
            "failed_cmd": self.failed_cmd,
            "consecutive_failed_trigger": self.consecutive_failed_trigger,
            "success_sound_type": self.success_sound_type,
            "success_audio_path": self.success_audio_path,
            "use_success_cmd": self.use_success_cmd,
            "success_cmd": self.success_cmd,
            "consecutive_success_trigger": self.consecutive_success_trigger,
            "log_pings": self.log_pings,
            "log_filename": self.log_filename,
            "log_file_type": self.log_file_type,
            "log_pings_mode": self.log_pings_mode,
            "lower_pane_mode": self.lower_pane_mode,
            "limit_accumulated_pings": self.limit_accumulated_pings,
            "max_accumulated_pings": self.max_accumulated_pings,
            "auto_export": self.auto_export,
            "auto_export_interval": self.auto_export_interval,
            "auto_export_file_type": self.auto_export_file_type,
            "auto_export_filename": self.auto_export_filename,
            "auto_export_only_on_change": self.auto_export_only_on_change,
            "auto_export_overwrite_mode": self.auto_export_overwrite_mode,
            "auto_export_counter_mode": self.auto_export_counter_mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PingOptions":
        opts = cls()
        if not isinstance(data, dict):
            return opts
        for k, v in data.items():
            if hasattr(opts, k):
                setattr(opts, k, v)
        return opts


class PingWorker:
    """负责底层单次探测执行器"""

    @staticmethod
    def _extract_reply_ip(stdout: str) -> Optional[str]:
        """从 ping 输出中严格提取响应 IP 地址，防止误提取主机名前缀"""
        # 1. 优先匹配带括号的 IP (例如: 64 bytes from dns.google (8.8.8.8):)
        paren_match = re.search(r"from\s+[^\s()]+\s*\(([0-9a-fA-F:.]+)\)", stdout, re.IGNORECASE)
        if paren_match:
            candidate = paren_match.group(1).strip()
            try:
                ipaddress.ip_address(candidate)
                return candidate
            except ValueError:
                pass

        # 2. 匹配直接输出 IP 格式 (例如: 64 bytes from 8.8.8.8: 或 来自 8.8.8.8 的回复)
        for pattern in [
            r"(?:from|来自|Reply from)\s+([0-9a-fA-F:.]+)",
        ]:
            match = re.search(pattern, stdout, re.IGNORECASE)
            if match:
                candidate = match.group(1).rstrip(':').strip()
                try:
                    ipaddress.ip_address(candidate)
                    return candidate
                except ValueError:
                    pass

        return None

    @staticmethod
    def probe_tcp(target: str, port: int, timeout_ms: int) -> Tuple[bool, Optional[float], Optional[int], str, str]:
        """TCP 端口连通性探测 (原生支持 IPv4 与 IPv6 双栈)"""
        start_time = time.perf_counter()
        resolved_ip = ""
        timeout_sec = max(0.1, timeout_ms / 1000.0)
        try:
            infos = socket.getaddrinfo(target, port)
            if infos:
                resolved_ip = infos[0][4][0]
            with socket.create_connection((target, port), timeout=timeout_sec):
                latency = (time.perf_counter() - start_time) * 1000.0
                return True, latency, None, "端口开放", resolved_ip
        except socket.timeout:
            return False, None, None, "连接超时", resolved_ip
        except ConnectionRefusedError:
            latency = (time.perf_counter() - start_time) * 1000.0
            return False, latency, None, "端口关闭(连接被拒)", resolved_ip
        except socket.gaierror:
            return False, None, None, "域名解析失败", ""
        except Exception as e:
            return False, None, None, str(e), resolved_ip

    @staticmethod
    def probe_icmp(
        target: str,
        timeout_ms: int,
        packet_size: int,
        custom_ttl_enabled: bool = False,
        custom_ttl: int = 64,
        dont_fragment: bool = False,
        source_ipv4: str = "",
        source_ipv6: str = ""
    ) -> Tuple[bool, Optional[float], Optional[int], str, str]:
        """
        调用系统 ping 工具进行免 root ICMP 探测 (原生支持 IPv4 与 IPv6)
        支持自定义 TTL、禁止分段 (DF) 以及指定网卡源 IP 绑定
        """
        is_linux = platform.system().lower() != "windows"
        timeout_sec = max(1, int((timeout_ms + 999) // 1000))
        resolved_ip = ""
        is_ipv6 = False

        # 1. 智能识别与解析 IP (支持 IPv4 与 IPv6)
        try:
            ip_obj = ipaddress.ip_address(target)
            resolved_ip = str(ip_obj)
            is_ipv6 = (ip_obj.version == 6)
        except ValueError:
            # 域名解析
            try:
                infos = socket.getaddrinfo(target, None)
                if infos:
                    resolved_ip = infos[0][4][0]
                    if ":" in resolved_ip:
                        is_ipv6 = True
            except Exception:
                pass

        # 2. 组装命令
        if is_linux:
            cmd = ["ping"]
            if is_ipv6:
                cmd.append("-6")
            cmd.extend(["-c", "1", "-W", str(timeout_sec), "-s", str(packet_size)])

            # 自定义 TTL (跳数)
            if custom_ttl_enabled and custom_ttl > 0:
                cmd.extend(["-t", str(custom_ttl)])

            # 禁止分段 (DF)
            if dont_fragment and not is_ipv6:
                cmd.extend(["-M", "do"])

            # 绑定源 IP
            if not is_ipv6 and source_ipv4 and not source_ipv4.startswith("("):
                cmd.extend(["-I", source_ipv4])
            elif is_ipv6 and source_ipv6 and not source_ipv6.startswith("("):
                cmd.extend(["-I", source_ipv6])

            cmd.append(target)
        else:
            cmd = ["ping"]
            if is_ipv6:
                cmd.append("-6")
            cmd.extend(["-n", "1", "-w", str(timeout_ms), "-l", str(packet_size)])

            # Windows 自定义 TTL (-i)
            if custom_ttl_enabled and custom_ttl > 0:
                cmd.extend(["-i", str(custom_ttl)])

            # Windows 禁止分段 (-f)
            if dont_fragment and not is_ipv6:
                cmd.append("-f")

            # Windows 源 IP 绑定 (-S)
            if not is_ipv6 and source_ipv4 and not source_ipv4.startswith("("):
                cmd.extend(["-S", source_ipv4])
            elif is_ipv6 and source_ipv6 and not source_ipv6.startswith("("):
                cmd.extend(["-S", source_ipv6])

            cmd.append(target)

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_sec + 2
            )
            stdout = proc.stdout

            # Linux 若 ping -6 不支持则尝试使用 ping6 命令
            if is_linux and is_ipv6 and proc.returncode != 0 and ("invalid option" in proc.stderr or "未识别" in proc.stderr):
                cmd_alt = ["ping6", "-c", "1", "-W", str(timeout_sec), "-s", str(packet_size), target]
                proc = subprocess.run(cmd_alt, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_sec + 2)
                stdout = proc.stdout

            # 解析可能响应的实际 IP
            extracted_ip = PingWorker._extract_reply_ip(stdout)
            if extracted_ip:
                resolved_ip = extracted_ip

            if proc.returncode == 0:
                # 探测成功，解析延迟与 TTL/HLIM
                latency: Optional[float] = None
                ttl: Optional[int] = None

                # 匹配 time=xx.x ms
                time_match = re.search(r"time[=<]([0-9.]+)\s*ms", stdout, re.IGNORECASE)
                if time_match:
                    try:
                        latency = float(time_match.group(1))
                    except ValueError:
                        latency = None

                # 匹配 TTL / HLIM (Hop Limit)
                ttl_match = re.search(r"(?:ttl|hlim)[=<](\d+)", stdout, re.IGNORECASE)
                if ttl_match:
                    try:
                        ttl = int(ttl_match.group(1))
                    except ValueError:
                        ttl = None

                return True, latency, ttl, "成功", resolved_ip
            else:
                err_text = stdout + "\n" + proc.stderr
                if "100% packet loss" in err_text or "100% 丢失" in err_text or "请求超时" in err_text or "timed out" in err_text:
                    return False, None, None, "请求超时", resolved_ip
                elif "Destination Host Unreachable" in err_text or "无法访问目标主机" in err_text:
                    return False, None, None, "目标不可达", resolved_ip
                elif "Frag needed and DF set" in err_text or "需要拆分数据包" in err_text:
                    return False, None, None, "禁止分段拦截(包过大)", resolved_ip
                else:
                    return False, None, None, "探测失败", resolved_ip

        except subprocess.TimeoutExpired:
            return False, None, None, "探测超时", resolved_ip
        except Exception as e:
            return False, None, None, f"异常: {e}", resolved_ip

    @staticmethod
    def probe(
        host: HostStat,
        timeout_ms: int,
        packet_size: int,
        custom_ttl_enabled: bool = False,
        custom_ttl: int = 64,
        dont_fragment: bool = False,
        source_ipv4: str = "",
        source_ipv6: str = "",
        resolve_dns_every_ping: bool = False
    ) -> Tuple[bool, Optional[float], Optional[int], str, str]:
        """统一探测入口：支持动态 DNS 重新解析、TCP 与高级 ICMP 选项"""
        # 1. 动态 DNS 反解析：针对主机名或域名，每次 ping 前重新获取最新 IP
        if resolve_dns_every_ping and host.port is None:
            try:
                ipaddress.ip_address(host.target)
            except ValueError:
                # 是域名或主机名，触发动态 DNS 解析
                try:
                    infos = socket.getaddrinfo(host.target, None)
                    if infos:
                        host.resolved_ip = infos[0][4][0]
                except Exception:
                    pass

        if host.port:
            return PingWorker.probe_tcp(host.target, host.port, timeout_ms)
        else:
            return PingWorker.probe_icmp(
                host.target,
                timeout_ms,
                packet_size,
                custom_ttl_enabled=custom_ttl_enabled,
                custom_ttl=custom_ttl,
                dont_fragment=dont_fragment,
                source_ipv4=source_ipv4,
                source_ipv6=source_ipv6
            )
