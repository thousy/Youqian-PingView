# -*- coding: utf-8 -*-
"""
全局配置与持久化管理器 (ConfigManager)
遵循 XDG 规范，跨平台存储配置与历史目标列表，支持本机网络接口 IP 自动枚举
"""

import os
import sys
import json
import socket
import platform
from typing import Dict, Any, List, Tuple


def get_local_ip_addresses() -> Tuple[List[str], List[str]]:
    """
    自动枚举当前设备上所有有效网卡的 IPv4 与 IPv6 地址列表
    返回: (ipv4_list, ipv6_list)
    """
    ipv4_list = ["(自动默认出口)"]
    ipv6_list = ["(自动默认出口)"]
    seen_v4 = set()
    seen_v6 = set()

    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            family, _, _, _, sockaddr = info
            ip = sockaddr[0]
            if family == socket.AF_INET:
                if ip not in seen_v4 and not ip.startswith("127."):
                    seen_v4.add(ip)
                    ipv4_list.append(ip)
            elif family == socket.AF_INET6:
                clean_ip = ip.split("%")[0]  # 去除接口标识符
                if clean_ip not in seen_v6 and clean_ip != "::1":
                    seen_v6.add(clean_ip)
                    ipv6_list.append(clean_ip)
    except Exception:
        pass

    # 针对 Linux 通过读取 /proc/net 或 UDP 伪连接探测主出口 IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        default_ip = s.getsockname()[0]
        s.close()
        if default_ip and default_ip not in seen_v4:
            seen_v4.add(default_ip)
            ipv4_list.insert(1, default_ip)
    except Exception:
        pass

    return ipv4_list, ipv6_list


class ConfigManager:
    """负责软件所有设置与目标列表的加载与持久化保存"""

    @staticmethod
    def get_config_dir() -> str:
        if platform.system().lower() == "windows":
            base = os.environ.get("APPDATA", os.path.expanduser("~"))
            cfg_dir = os.path.join(base, "YouqianPingView")
        else:
            base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
            cfg_dir = os.path.join(base, "youqian-pingview")
        os.makedirs(cfg_dir, exist_ok=True)
        return cfg_dir

    @classmethod
    def get_config_path(cls) -> str:
        return os.path.join(cls.get_config_dir(), "settings.json")

    @classmethod
    def load_config(cls) -> Dict[str, Any]:
        """读取配置文件，若不存在则返回空字典"""
        cfg_path = cls.get_config_path()
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[警告] 读取配置文件失败，将使用默认配置: {e}", file=sys.stderr)
        return {}

    @classmethod
    def save_config(cls, data: Dict[str, Any]) -> bool:
        """持久化保存配置字典到 settings.json"""
        cfg_path = cls.get_config_path()
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[错误] 保存配置文件失败: {e}", file=sys.stderr)
            return False
