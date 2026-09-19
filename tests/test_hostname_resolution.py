# -*- coding: utf-8 -*-
"""
主机名反向解析 (Reverse DNS & NetBIOS) 单元测试
确保 Ping 探测支持返回并展示真实主机名
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from youqian_pingview.core.pinger import HostStat, PingOptions, resolve_host_name, resolve_reverse_dns


class TestHostnameResolution(unittest.TestCase):
    def test_host_stat_hostname_init(self):
        """测试 HostStat 初始化时对域名和纯 IP 的初始主机名处理"""
        # 1. 域名目标
        host_domain = HostStat(1, "www.baidu.com", description="百度")
        self.assertEqual(host_domain.hostname, "www.baidu.com")

        # 2. 纯 IP 目标
        host_ip = HostStat(2, "192.168.1.1", description="网关")
        self.assertEqual(host_ip.hostname, "")

        # 3. 反向解析更新
        host_ip.hostname = "router.local"
        self.assertEqual(host_ip.hostname, "router.local")

    def test_resolve_host_name_domain_passthrough(self):
        """测试如果输入的是主机名/域名，直接透传返回"""
        res = resolve_host_name("my-server.lan")
        self.assertEqual(res, "my-server.lan")

    def test_options_resolve_addresses_default(self):
        """测试 PingOptions 默认开启解析地址功能"""
        opts = PingOptions()
        self.assertTrue(opts.resolve_addresses)
        d = opts.to_dict()
        self.assertIn("resolve_addresses", d)
        self.assertTrue(d["resolve_addresses"])

        restored = PingOptions.from_dict(d)
        self.assertTrue(restored.resolve_addresses)


if __name__ == "__main__":
    unittest.main()
