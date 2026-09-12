"""
UOSPingView 核心模块单元测试
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from uos_pingview.core.target_parser import parse_targets_text, TargetItem
from uos_pingview.core.pinger import HostStat, PingWorker, PingOptions
from uos_pingview.core.exporter import Exporter


class TestCoreModules(unittest.TestCase):

    def test_target_parser_formats(self):
        sample = """
        # 注释行
        192.168.1.1 核心网关
        www.baidu.com 百度外网
        192.168.1.100:80 Web服务
        10.0.0.0/30 财务室子网
        172.16.1.1-172.16.1.3 监控主机
        """
        items = parse_targets_text(sample)
        targets = [it.target for it in items]

        # 验证解析数量与内容
        self.assertIn("192.168.1.1", targets)
        self.assertIn("www.baidu.com", targets)
        self.assertIn("192.168.1.100", targets)
        
        # 验证 TCP 端口
        web_item = next(it for it in items if it.target == "192.168.1.100")
        self.assertEqual(web_item.port, 80)
        self.assertEqual(web_item.description, "Web服务")

        # 验证 CIDR 展开 /30 应该展开为 2 个可用主机 (10.0.0.1, 10.0.0.2)
        self.assertIn("10.0.0.1", targets)
        self.assertIn("10.0.0.2", targets)

        # 验证 IP 范围展开 (172.16.1.1, 172.16.1.2, 172.16.1.3)
        self.assertIn("172.16.1.1", targets)
        self.assertIn("172.16.1.2", targets)
        self.assertIn("172.16.1.3", targets)

    def test_host_stat_calculations(self):
        stat = HostStat(1, "127.0.0.1", "本机测试")
        self.assertEqual(stat.last_status, "未开始")
        self.assertEqual(stat.failure_rate, 0.0)

        # 模拟第1次探测成功，延迟 10ms
        stat.update_result(True, 10.0, 64, "成功", "127.0.0.1")
        self.assertEqual(stat.success_count, 1)
        self.assertEqual(stat.failed_count, 0)
        self.assertEqual(stat.total_sent, 1)
        self.assertEqual(stat.failure_rate, 0.0)
        self.assertEqual(stat.avg_latency_ms, 10.0)
        self.assertEqual(stat.min_latency_ms, 10.0)
        self.assertEqual(stat.max_latency_ms, 10.0)

        # 模拟第2次探测成功，延迟 20ms
        stat.update_result(True, 20.0, 64, "成功", "127.0.0.1")
        self.assertEqual(stat.success_count, 2)
        self.assertEqual(stat.avg_latency_ms, 15.0)
        self.assertEqual(stat.min_latency_ms, 10.0)
        self.assertEqual(stat.max_latency_ms, 20.0)

        # 模拟第3次探测失败
        stat.update_result(False, None, None, "请求超时", "127.0.0.1")
        self.assertEqual(stat.failed_count, 1)
        self.assertEqual(stat.total_sent, 3)
        self.assertAlmostEqual(stat.failure_rate, 33.33, delta=0.1)
        self.assertEqual(stat.consecutive_failures, 1)
        self.assertEqual(stat.max_consecutive_failures, 1)

        # 验证流水记录数
        self.assertEqual(len(stat.history_records), 3)

    def test_exporter(self):
        stat = HostStat(1, "127.0.0.1", "测试主机")
        stat.update_result(True, 5.2, 64, "成功", "127.0.0.1")
        
        test_html = os.path.join(BASE_DIR, "tests", "temp_report.html")
        test_csv = os.path.join(BASE_DIR, "tests", "temp_report.csv")

        try:
            Exporter.export_html([stat], test_html)
            self.assertTrue(os.path.exists(test_html))
            with open(test_html, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("127.0.0.1", content)
                self.assertIn("测试主机", content)

            Exporter.export_csv([stat], test_csv)
            self.assertTrue(os.path.exists(test_csv))
        finally:
            if os.path.exists(test_html):
                os.remove(test_html)
            if os.path.exists(test_csv):
                os.remove(test_csv)

    def test_pinger_local_loopback(self):
        # 探测本机 127.0.0.1
        stat = HostStat(1, "127.0.0.1")
        succ, lat, ttl, status, ip = PingWorker.probe(stat, timeout_ms=2000, packet_size=32)
        self.assertTrue(succ, f"127.0.0.1 应该可达，但返回: {status}")
        self.assertIsNotNone(lat)


if __name__ == "__main__":
    unittest.main()
