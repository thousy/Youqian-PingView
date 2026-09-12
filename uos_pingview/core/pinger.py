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


class HostStat:
    """单个主机的汇总统计数据 (用于上窗格主监控表)"""
    def __init__(self, index: int, target: str, description: str = "", port: Optional[int] = None):
        self.index = index
        self.target = target
        self.description = description
        self.port = port
        self.enabled = True

        self.resolved_ip = ""
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
        self.last_success_time = ""
        self.last_failed_time = ""
        self.consecutive_failures = 0
        self.max_consecutive_failures = 0

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
        self.last_success_time = ""
        self.last_failed_time = ""
        self.consecutive_failures = 0
        self.max_consecutive_failures = 0
        self.history_records.clear()

    def update_result(self, is_success: bool, latency: Optional[float], ttl: Optional[int],
                      status_msg: str, resolved_ip: str) -> PingRecord:
        """记录探测结果并更新累加统计值"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.total_sent += 1
        if resolved_ip:
            self.resolved_ip = resolved_ip

        if is_success:
            self.success_count += 1
            self.consecutive_failures = 0
            self.last_success_time = now_str
            self.last_status = "成功"
            self.last_latency_ms = latency
            self.last_ttl = ttl

            if latency is not None:
                self._total_latency += latency
                self.avg_latency_ms = self._total_latency / self.success_count
                if self.min_latency_ms is None or latency < self.min_latency_ms:
                    self.min_latency_ms = latency
                if self.max_latency_ms is None or latency > self.max_latency_ms:
                    self.max_latency_ms = latency
        else:
            self.failed_count += 1
            self.consecutive_failures += 1
            if self.consecutive_failures > self.max_consecutive_failures:
                self.max_consecutive_failures = self.consecutive_failures
            self.last_failed_time = now_str
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
        self.history_records.append(record)
        if len(self.history_records) > self.max_history:
            self.history_records.pop(0)

        return record


class PingOptions:
    """Ping 探测全局设置"""
    def __init__(self):
        self.interval_sec: int = 5         # 轮询间隔 (秒)
        self.timeout_ms: int = 2000        # 超时时间 (毫秒)
        self.packet_size: int = 32         # 数据包大小 (字节)
        self.max_threads: int = 50         # 并发探测线程上限
        self.alarm_on_fail: bool = True    # 连续失败告警
        self.alarm_fail_threshold: int = 3 # 连续失败报警阈值
        self.limit_history_count: int = 200 # 下窗格保留记录数


class PingWorker:
    """负责底层单次探测执行器"""

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
            return True, latency, None, "连接被拒(主机存活)", resolved_ip
        except socket.gaierror:
            return False, None, None, "域名解析失败", ""
        except Exception as e:
            return False, None, None, str(e), resolved_ip

    @staticmethod
    def probe_icmp(target: str, timeout_ms: int, packet_size: int) -> Tuple[bool, Optional[float], Optional[int], str, str]:
        """
        调用系统 ping 工具进行免 root ICMP 探测 (原生支持 IPv4 与 IPv6)
        自动识别 IPv6 并使用对应参数与 hlim 跳数限制解析
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
            if is_ipv6:
                cmd = ["ping", "-6", "-c", "1", "-W", str(timeout_sec), "-s", str(packet_size), target]
            else:
                cmd = ["ping", "-c", "1", "-W", str(timeout_sec), "-s", str(packet_size), target]
        else:
            if is_ipv6:
                cmd = ["ping", "-6", "-n", "1", "-w", str(timeout_ms), "-l", str(packet_size), target]
            else:
                cmd = ["ping", "-n", "1", "-w", str(timeout_ms), "-l", str(packet_size), target]

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

            if proc.returncode == 0:
                # 探测成功，解析延迟与 TTL/HLIM
                latency: Optional[float] = None
                ttl: Optional[int] = None

                # 匹配 time=xx.x ms
                time_match = re.search(r"time[=<]([0-9.]+)\s*ms", stdout, re.IGNORECASE)
                if time_match:
                    latency = float(time_match.group(1))

                # 匹配 IPv4 ttl 或 IPv6 hlim
                ttl_match = re.search(r"(?:ttl|hlim)[=<](\d+)", stdout, re.IGNORECASE)
                if ttl_match:
                    ttl = int(ttl_match.group(1))

                # 提取实际响应的 IP (如 64 bytes from 2400:3200::1)
                ip_match = re.search(r"from\s+([0-9a-fA-F:.]+)", stdout, re.IGNORECASE)
                if ip_match:
                    resp_ip = ip_match.group(1).rstrip(':')
                    if resp_ip:
                        resolved_ip = resp_ip

                return True, latency, ttl, "成功", resolved_ip
            else:
                if "Destination Host Unreachable" in stdout or "无法访问目标主机" in stdout:
                    return False, None, None, "目标不可达", resolved_ip
                elif "Request timed out" in stdout or "请求超时" in stdout or "100% packet loss" in stdout:
                    return False, None, None, "请求超时", resolved_ip
                elif "unknown host" in stdout or "找不到主机" in stdout:
                    return False, None, None, "未知主机", resolved_ip
                else:
                    return False, None, None, "探测失败", resolved_ip

        except subprocess.TimeoutExpired:
            return False, None, None, "命令超时", resolved_ip
        except Exception as e:
            return False, None, None, f"异常:{str(e)[:15]}", resolved_ip

    @classmethod
    def probe(cls, host: HostStat, timeout_ms: int, packet_size: int) -> Tuple[bool, Optional[float], Optional[int], str, str]:
        """统一探测入口"""
        if host.port is not None:
            return cls.probe_tcp(host.target, host.port, timeout_ms)
        else:
            return cls.probe_icmp(host.target, timeout_ms, packet_size)
