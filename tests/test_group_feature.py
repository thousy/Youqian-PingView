# -*- coding: utf-8 -*-
"""
地址分组 (Group: ...) 语法解析与数据结构单元测试
对标原版 PingInfoView 2.20 / 2.22 官方规范
"""

import unittest
from youqian_pingview.core.target_parser import parse_targets_text, TargetItem
from youqian_pingview.core.pinger import HostStat


class TestGroupFeature(unittest.TestCase):
    def test_basic_group_parsing(self):
        text = """
Group: 核心机房
192.168.1.1 核心交换机网关
192.168.1.2 DNS服务

Group: 办公网络
192.168.2.1 办公路由
192.168.2.2:80 办公OA服务
"""
        items = parse_targets_text(text)
        self.assertEqual(len(items), 4)
        self.assertEqual(items[0].group, "核心机房")
        self.assertEqual(items[0].target, "192.168.1.1")
        self.assertEqual(items[1].group, "核心机房")
        self.assertEqual(items[2].group, "办公网络")
        self.assertEqual(items[3].group, "办公网络")
        self.assertEqual(items[3].port, 80)

    def test_group_case_and_chinese_syntax(self):
        text = """
group: Servers
10.0.0.1 Server1

分组: 交换机组
10.0.1.1 Switch1
"""
        items = parse_targets_text(text)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].group, "Servers")
        self.assertEqual(items[1].group, "交换机组")

    def test_cidr_and_range_inside_group(self):
        text = """
Group: 区域子网
192.168.10.0/30 子网网段
192.168.20.1-192.168.20.3 范围网段
"""
        items = parse_targets_text(text, skip_first=False, skip_last=False)
        self.assertTrue(len(items) >= 4)
        for it in items:
            self.assertEqual(it.group, "区域子网")

    def test_ungrouped_fallback(self):
        text = """
127.0.0.1 本地测试

Group: 业务组
1.1.1.1 Cloudflare
"""
        items = parse_targets_text(text)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].group, "")
        self.assertEqual(items[1].group, "业务组")

    def test_host_stat_group_property(self):
        stat = HostStat(1, "192.168.1.1", "核心网关", group="核心组")
        self.assertEqual(stat.group, "核心组")


if __name__ == "__main__":
    unittest.main()
