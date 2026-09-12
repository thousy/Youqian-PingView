"""
目标解析模块
支持解析：
1. 单个 IP 或域名 (如: 192.168.1.1, www.baidu.com)
2. 带描述的格式 (如: 192.168.1.1 核心网关, www.google.com 谷歌搜索引擎)
3. CIDR 子网格式 (如: 192.168.1.0/24 或 192.168.1.0/28)
4. IP 范围格式 (如: 192.168.1.1-192.168.1.50)
5. TCP 端口格式 (如: 192.168.1.1:80, www.baidu.com:443)
"""

import ipaddress
import re
from typing import List, Dict, Optional


class TargetItem:
    def __init__(self, target: str, description: str = "", port: Optional[int] = None):
        self.target = target.strip()
        self.description = description.strip()
        self.port = port

    def to_dict(self) -> Dict:
        return {
            "target": self.target,
            "description": self.description,
            "port": self.port,
        }

    def __repr__(self):
        if self.port:
            return f"<Target {self.target}:{self.port} ({self.description})>"
        return f"<Target {self.target} ({self.description})>"


def parse_targets_text(text: str) -> List[TargetItem]:
    """
    解析多行文本为 TargetItem 列表
    支持：
    - 注释行（以 # 或 ; 或 // 开头）
    - 空行自动忽略
    - CIDR 展开（例如 192.168.1.0/29 局域网机房）
    - 范围展开（例如 192.168.1.1-192.168.1.10）
    - 常见格式：[IP/域名] [描述]
    """
    results: List[TargetItem] = []
    lines = text.splitlines()

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith(('#', ';', '//')):
            continue

        # 分割目标与描述：优先以空白字符（空格/制表符）分割为两部分
        parts = line.split(maxsplit=1)
        target_token = parts[0].strip()
        desc = parts[1].strip() if len(parts) > 1 else ""

        # 检查是否为 TCP 端口格式，如 192.168.1.1:80 或 [2001:db8::1]:80
        port: Optional[int] = None
        clean_target = target_token
        
        # 匹配 IPv4/域名加端口：host:port
        tcp_match = re.match(r"^([a-zA-Z0-9.\-_]+):(\d+)$", target_token)
        if tcp_match:
            clean_target = tcp_match.group(1)
            try:
                port = int(tcp_match.group(2))
            except ValueError:
                port = None
        else:
            # 匹配 IPv6 加端口：[ipv6]:port
            tcp_v6_match = re.match(r"^\[([a-fA-F0-9:]+)\]:(\d+)$", target_token)
            if tcp_v6_match:
                clean_target = tcp_v6_match.group(1)
                try:
                    port = int(tcp_v6_match.group(2))
                except ValueError:
                    port = None

        # 1. 尝试作为 CIDR 网段解析 (仅针对纯 IP 网段)
        if "/" in clean_target and port is None:
            try:
                net = ipaddress.ip_network(clean_target, strict=False)
                # 限制展开数量，防止输入 /8 导致卡顿
                if net.num_addresses > 1024:
                    results.append(TargetItem(clean_target, desc or f"CIDR网段({net.num_addresses}地址)"))
                    continue
                for ip in net.hosts():
                    results.append(TargetItem(str(ip), desc))
                continue
            except ValueError:
                pass

        # 2. 尝试作为 IP 范围解析 (如 192.168.1.1-192.168.1.10 或 192.168.1.1-10)
        if "-" in clean_target and port is None:
            range_match = re.match(r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.)(\d{1,3})-(\d{1,3})$", clean_target)
            if range_match:
                prefix = range_match.group(1)
                start_num = int(range_match.group(2))
                end_num = int(range_match.group(3))
                if 0 <= start_num <= 255 and 0 <= end_num <= 255 and start_num <= end_num:
                    for n in range(start_num, end_num + 1):
                        results.append(TargetItem(f"{prefix}{n}", desc))
                    continue

            range_full_match = re.match(r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})-(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})$", clean_target)
            if range_full_match:
                try:
                    start_ip = ipaddress.IPv4Address(range_full_match.group(1))
                    end_ip = ipaddress.IPv4Address(range_full_match.group(2))
                    if int(start_ip) <= int(end_ip) and (int(end_ip) - int(start_ip)) <= 1024:
                        curr = int(start_ip)
                        end_val = int(end_ip)
                        while curr <= end_val:
                            results.append(TargetItem(str(ipaddress.IPv4Address(curr)), desc))
                            curr += 1
                        continue
                except ValueError:
                    pass

        # 3. 普通单一目标
        results.append(TargetItem(clean_target, desc, port=port))

    return results
