"""
Youqian-PingView 核心模块单元测试
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from youqian_pingview.core.target_parser import parse_targets_text, TargetItem
from youqian_pingview.core.pinger import HostStat, PingWorker, PingOptions
from youqian_pingview.core.exporter import Exporter


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

    def test_tcp_refusal_is_failure(self):
        """测试 TCP 端口被拒时必须标为失败，不可判定为成功"""
        from unittest.mock import patch
        with patch("socket.create_connection", side_effect=ConnectionRefusedError):
            succ, lat, ttl, status_str, resp_ip = PingWorker.probe_tcp("127.0.0.1", 9999, 1000)
            self.assertFalse(succ)
            self.assertIn("端口关闭", status_str)

            stat = HostStat(1, "127.0.0.1", port=9999)
            stat.update_result(succ, lat, ttl, status_str, resp_ip)
            self.assertEqual(stat.success_count, 0)
            self.assertEqual(stat.failed_count, 1)
            self.assertEqual(stat.failure_rate, 100.0)
            self.assertIn("端口关闭", stat.last_status)

    def test_ping_reply_ip_extraction(self):
        """测试各类复杂系统 ping 输出中的响应 IP 提取逻辑"""
        sample_dns = "64 bytes from dns.google (8.8.8.8): icmp_seq=1 ttl=118 time=14.2 ms"
        ip = PingWorker._extract_reply_ip(sample_dns)
        self.assertEqual(ip, "8.8.8.8")  # 绝对不能是误截断的单个字符 'd'

        sample_v6 = "64 bytes from 2400:3200::1: icmp_seq=1 ttl=64 time=22.1 ms"
        ip_v6 = PingWorker._extract_reply_ip(sample_v6)
        self.assertEqual(ip_v6, "2400:3200::1")

        sample_win = "来自 192.168.1.1 的回复: 字节=32 时间=2ms TTL=64"
        ip_win = PingWorker._extract_reply_ip(sample_win)
        self.assertEqual(ip_win, "192.168.1.1")

    def test_avg_latency_with_none_samples(self):
        """测试某次成功缺失延迟时，平均延迟分母不会虚增导致均值偏小"""
        stat = HostStat(1, "127.0.0.1")
        # 第一次成功但没有延迟数据
        stat.update_result(True, None, 64, "成功", "127.0.0.1")
        self.assertIsNone(stat.avg_latency_ms)

        # 第二次成功且延迟为 10.0ms
        stat.update_result(True, 10.0, 64, "成功", "127.0.0.1")
        # 平均值应为 10.0ms，而不是 10.0 / 2 = 5.0ms
        self.assertEqual(stat.avg_latency_ms, 10.0)

    def test_html_export_xss_protection(self):
        """测试 HTML 报表导出对恶意标签的转义防范"""
        xss_payload = "<script>alert('xss')</script>"
        stat = HostStat(1, "192.168.1.1", description=xss_payload)
        stat.update_result(True, 5.0, 64, "成功", "192.168.1.1")

        test_html = os.path.join(BASE_DIR, "tests", "temp_xss_report.html")
        try:
            Exporter.export_html([stat], test_html, title=f"测试报告 {xss_payload}")
            with open(test_html, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn("<script>", content)
            self.assertIn("&lt;script&gt;", content)
        finally:
            if os.path.exists(test_html):
                os.remove(test_html)

    def test_port_validation_and_cidr_limit(self):
        """测试非法端口过滤与超大 CIDR 网段截断保护"""
        sample = """
        192.168.1.1:65536 端口越界测试
        10.0.0.0/16 超大网段测试
        """
        items = parse_targets_text(sample)
        # 65536 超出 65535 范围，端口应为 None
        target_65536 = next(it for it in items if "192.168.1.1" in it.target)
        self.assertIsNone(target_65536.port)

        # 10.0.0.0/16 展开应受限最大 1024 个主机，而不是把未展开的网段字符串当成目标
        cidr_items = [it for it in items if it.target.startswith("10.0.")]
        self.assertEqual(len(cidr_items), 1024)
        self.assertFalse(any("/" in it.target for it in items))

    def test_tk_isolation_without_qt(self):
        """测试在完全缺失 Qt 依赖的环境下，Tk 引擎依然能顺畅加载不抛出异常"""
        import subprocess
        test_script = (
            "import sys; "
            "sys.modules['PyQt5'] = None; "
            "sys.modules['PySide6'] = None; "
            "sys.modules['PyQt6'] = None; "
            f"sys.path.insert(0, r'{BASE_DIR}'); "
            "from youqian_pingview.ui.tk_window import TkMainWindow; "
            "import youqian_pingview.ui as ui; "
            "assert ui.MainWindow is None; "
            "print('ISOLATION_OK')"
        )
        proc = subprocess.run(
            [sys.executable, "-c", test_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=BASE_DIR
        )
        self.assertEqual(proc.returncode, 0, f"无Qt环境导入失败: {proc.stderr}")
        self.assertIn("ISOLATION_OK", proc.stdout)


    def test_config_manager_persistence(self):
        """测试 ConfigManager 配置保存与加载持久化能力"""
        from youqian_pingview.core.config_manager import ConfigManager
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            orig_func = ConfigManager.get_config_dir
            ConfigManager.get_config_dir = lambda: tmp_dir
            try:
                test_data = {
                    "targets_text": "192.168.1.1 核心路由",
                    "options": {
                        "timeout_ms": 3000,
                        "packet_size": 64,
                        "custom_ttl_enabled": True,
                        "custom_ttl": 128,
                        "dont_fragment": True,
                        "custom_window_title": "自定义机房A监控"
                    }
                }
                self.assertTrue(ConfigManager.save_config(test_data))
                loaded = ConfigManager.load_config()
                self.assertEqual(loaded.get("targets_text"), "192.168.1.1 核心路由")
                self.assertEqual(loaded["options"]["custom_ttl"], 128)
                self.assertEqual(loaded["options"]["custom_window_title"], "自定义机房A监控")

                opts = PingOptions.from_dict(loaded["options"])
                self.assertEqual(opts.timeout_ms, 3000)
                self.assertEqual(opts.packet_size, 64)
                self.assertTrue(opts.custom_ttl_enabled)
                self.assertEqual(opts.custom_ttl, 128)
                self.assertTrue(opts.dont_fragment)
                self.assertEqual(opts.custom_window_title, "自定义机房A监控")
            finally:
                ConfigManager.get_config_dir = orig_func

    def test_cidr_skip_first_and_last(self):
        """测试 CIDR 跳过第一个地址(网络号)与最后一个地址(广播号)开关"""
        # 192.168.10.0/29 包含 8 个 IP: .0 到 .7
        cidr = "192.168.10.0/29"
        
        # 1. 默认: skip_first=False, skip_last=True (包含 .0, 不包含 .7)
        items_def = parse_targets_text(cidr, skip_first=False, skip_last=True)
        ips_def = [it.target for it in items_def]
        self.assertIn("192.168.10.0", ips_def)
        self.assertNotIn("192.168.10.7", ips_def)
        self.assertEqual(len(ips_def), 7)

        # 2. 原版经典: skip_first=True, skip_last=True (排除 .0 和 .7, 纯有效主机)
        items_hosts = parse_targets_text(cidr, skip_first=True, skip_last=True)
        ips_hosts = [it.target for it in items_hosts]
        self.assertNotIn("192.168.10.0", ips_hosts)
        self.assertNotIn("192.168.10.7", ips_hosts)
        self.assertEqual(len(ips_hosts), 6)

        # 3. 包含全部: skip_first=False, skip_last=False
        items_all = parse_targets_text(cidr, skip_first=False, skip_last=False)
        ips_all = [it.target for it in items_all]
        self.assertIn("192.168.10.0", ips_all)
        self.assertIn("192.168.10.7", ips_all)
        self.assertEqual(len(ips_all), 8)

    def test_ping_command_advanced_options(self):
        """测试自定义 TTL、禁止分段 DF 与源 IP 参数在命令构建中的正确注入"""
        from unittest.mock import patch
        import platform

        captured_cmds = []

        def mock_run(cmd, *args, **kwargs):
            captured_cmds.append(cmd)
            class MockProc:
                returncode = 0
                stdout = "Reply from 1.1.1.1: bytes=32 time=12ms TTL=54"
                stderr = ""
            return MockProc()

        with patch("subprocess.run", side_effect=mock_run):
            PingWorker.probe_icmp(
                "1.1.1.1",
                timeout_ms=1000,
                packet_size=64,
                custom_ttl_enabled=True,
                custom_ttl=100,
                dont_fragment=True,
                source_ipv4="192.168.1.50"
            )

        self.assertTrue(len(captured_cmds) > 0)
        cmd = captured_cmds[0]
        # 检验参数存在
        if platform.system().lower() == "windows":
            self.assertIn("-i", cmd)
            self.assertIn("100", cmd)
            self.assertIn("-f", cmd)
            self.assertIn("-S", cmd)
            self.assertIn("192.168.1.50", cmd)
        else:
            self.assertIn("-t", cmd)
            self.assertIn("100", cmd)
            self.assertIn("-M", cmd)
            self.assertIn("do", cmd)
            self.assertIn("-I", cmd)
            self.assertIn("192.168.1.50", cmd)

    def test_host_stat_consecutive_and_mac(self):
        """测试最大连续失败次数、峰值时间戳、MAC 地址绑定与重置行为"""
        from youqian_pingview.core.pinger import get_mac_address
        stat = HostStat(1, "192.168.1.1", "核心网关")

        # 1. 连续失败 3 次
        stat.update_result(False, None, None, "请求超时", "192.168.1.1")
        stat.update_result(False, None, None, "请求超时", "192.168.1.1")
        stat.update_result(False, None, None, "请求超时", "192.168.1.1")
        self.assertEqual(stat.consecutive_failures, 3)
        self.assertEqual(stat.max_consecutive_failures, 3)
        self.assertIsNotNone(stat.max_consecutive_failure_time)
        self.assertIsNotNone(stat.last_failed_time)

        # 2. 成功 1 次，连续失败应归零，但最大连续失败保持为 3
        stat.update_result(True, 2.5, 64, "成功", "192.168.1.1")
        self.assertEqual(stat.consecutive_failures, 0)
        self.assertEqual(stat.max_consecutive_failures, 3)
        self.assertIsNotNone(stat.last_success_time)

        # 3. 再失败 2 次，最大连续失败依然为 3
        stat.update_result(False, None, None, "请求超时", "192.168.1.1")
        stat.update_result(False, None, None, "请求超时", "192.168.1.1")
        self.assertEqual(stat.consecutive_failures, 2)
        self.assertEqual(stat.max_consecutive_failures, 3)

        # 4. 再失败 2 次 (累计 4 次)，最大连续失败应更新为 4
        stat.update_result(False, None, None, "请求超时", "192.168.1.1")
        stat.update_result(False, None, None, "请求超时", "192.168.1.1")
        self.assertEqual(stat.consecutive_failures, 4)
        self.assertEqual(stat.max_consecutive_failures, 4)

        # 5. 测试 reset_stats 重置
        stat.reset_stats()
        self.assertEqual(stat.consecutive_failures, 0)
        self.assertEqual(stat.max_consecutive_failures, 0)
        self.assertEqual(stat.max_consecutive_failure_time, "")
        self.assertEqual(stat.last_failed_time, "")
        self.assertEqual(stat.total_sent, 0)

        # 6. 测试 get_mac_address 容错 (非内网IP不报错返回空)
        mac = get_mac_address("127.0.0.1")
        self.assertIsInstance(mac, str)

    def test_exporter_22_columns(self):
        """测试 Exporter 导出 22 列原版指标的完整性"""
        stat = HostStat(1, "192.168.1.1", "核心网关")
        stat.update_result(True, 1.25, 64, "成功", "192.168.1.1")

        self.assertEqual(len(Exporter.HEADERS), 22)
        self.assertEqual(Exporter.HEADERS[0], "序号")
        self.assertEqual(Exporter.HEADERS[1], "主机名")
        self.assertEqual(Exporter.HEADERS[2], "IP 地址")
        self.assertEqual(Exporter.HEADERS[3], "响应 IP 地址")
        self.assertEqual(Exporter.HEADERS[-1], "MAC 地址")

        row = Exporter._host_to_row(stat)
        self.assertEqual(len(row), 22)
        self.assertEqual(row[0], "1")
        self.assertEqual(row[1], "192.168.1.1")
        self.assertEqual(row[4], "1")  # 成功次数
        self.assertEqual(row[5], "0")  # 失败次数
        self.assertEqual(row[10], "1") # 总计发送Pings数
        self.assertEqual(row[20], "否") # 禁用=否


if __name__ == "__main__":
    unittest.main()
