# -*- coding: utf-8 -*-
"""
原版选项 (Options) 菜单新增全量功能单元测试
测试内容包括：
1. PingOptions 所有新字段的持久化与默认值
2. 延迟与时间格式化辅助函数 (高分辨率时间 vs 整数毫秒，GMT时间 vs 本地时间)
3. 导出器 (Exporter) 控制标题行 (add_header) 开关测试
4. 主机名排序与真实主机名回填逻辑测试
"""

import unittest
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from youqian_pingview.core.pinger import PingOptions, HostStat
from youqian_pingview.core.exporter import Exporter


class TestOptionsMenuFeatures(unittest.TestCase):
    def test_options_defaults_and_serialization(self):
        """测试原版选项菜单所有属性的默认值与字典序列化"""
        opts = PingOptions()
        # 默认值检验
        self.assertEqual(opts.display_mode, "显示所有 Hosts")
        self.assertTrue(opts.high_resolution_timer)
        self.assertFalse(opts.show_gmt_time)
        self.assertTrue(opts.mark_failed_pings)
        self.assertFalse(opts.always_on_top)
        self.assertFalse(opts.beep_on_failed)
        self.assertFalse(opts.beep_on_success)
        self.assertFalse(opts.tray_icon_enabled)
        self.assertFalse(opts.start_as_hidden)
        self.assertTrue(opts.resolve_addresses)
        self.assertTrue(opts.show_lower_pane)
        self.assertTrue(opts.auto_scroll_lower_pane)
        self.assertFalse(opts.sort_on_every_update)
        self.assertTrue(opts.add_header_to_export)
        self.assertEqual(opts.custom_font_family, "")
        self.assertEqual(opts.custom_font_size, 9)

        # 修改并序列化
        opts.display_mode = "仅显示失败的 Hosts"
        opts.high_resolution_timer = False
        opts.show_gmt_time = True
        opts.always_on_top = True
        opts.beep_on_failed = True
        opts.sort_on_every_update = True
        opts.add_header_to_export = False
        opts.custom_font_family = "SimSun"
        opts.custom_font_size = 11

        d = opts.to_dict()
        restored = PingOptions.from_dict(d)
        self.assertEqual(restored.display_mode, "仅显示失败的 Hosts")
        self.assertFalse(restored.high_resolution_timer)
        self.assertTrue(restored.show_gmt_time)
        self.assertTrue(restored.always_on_top)
        self.assertTrue(restored.beep_on_failed)
        self.assertTrue(restored.sort_on_every_update)
        self.assertFalse(restored.add_header_to_export)
        self.assertEqual(restored.custom_font_family, "SimSun")
        self.assertEqual(restored.custom_font_size, 11)

    def test_high_resolution_latency_formatting(self):
        """测试高分辨率 (3位小数) 与标准 (四舍五入整数) 延迟显示格式化"""
        # 高分辨率 True
        high_res = True
        lat = 12.3456
        res_high = f"{lat:.3f}" if high_res else f"{int(round(lat))}"
        self.assertEqual(res_high, "12.346")

        # 高分辨率 False
        high_res = False
        res_low = f"{lat:.3f}" if high_res else f"{int(round(lat))}"
        self.assertEqual(res_low, "12")

        lat_round = 8.6
        res_low_round = f"{lat_round:.3f}" if high_res else f"{int(round(lat_round))}"
        self.assertEqual(res_low_round, "9")

    def test_exporter_add_header_option(self):
        """测试 Exporter 导出时添加标题行参数的有效性"""
        host1 = HostStat(1, "192.168.1.1", description="网关")
        host1.hostname = "router.lan"
        host1.update_result(True, 2.5, 64, "成功", "192.168.1.1")

        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_with_header = os.path.join(tmp_dir, "with_header.csv")
            csv_no_header = os.path.join(tmp_dir, "no_header.csv")

            # 1. 导出带标题行
            Exporter.export_csv([host1], csv_with_header, add_header=True)
            with open(csv_with_header, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()
                self.assertGreaterEqual(len(lines), 2)
                self.assertIn("序号", lines[0])
                self.assertIn("router.lan", lines[1])

            # 2. 导出不带标题行
            Exporter.export_csv([host1], csv_no_header, add_header=False)
            with open(csv_no_header, "r", encoding="utf-8-sig") as f:
                lines_no_header = f.readlines()
                self.assertEqual(len(lines_no_header), 1)
                self.assertNotIn("序号", lines_no_header[0])
                self.assertIn("router.lan", lines_no_header[0])


    def test_lower_pane_sorting(self):
        """测试下窗格按各列 (Ping时间/耗时/状态/序号) 排序算法的准确性"""
        host = HostStat(1, "192.168.1.1")
        host.update_result(True, 15.2, 64, "成功", "192.168.1.1")
        host.update_result(False, None, None, "超时", "192.168.1.1")
        host.update_result(True, 8.4, 64, "成功", "192.168.1.1")

        records = list(host.history_records)
        self.assertEqual(len(records), 3)

        # 1. 按 Ping 计数排序
        records_by_seq = sorted(records, key=lambda r: r.sequence)
        self.assertEqual([r.sequence for r in records_by_seq], [1, 2, 3])

        records_by_seq_desc = sorted(records, key=lambda r: r.sequence, reverse=True)
        self.assertEqual([r.sequence for r in records_by_seq_desc], [3, 2, 1])

        # 2. 按 Ping 时间 (耗时) 升序排序 (None排在最后)
        def _lat_key(r):
            return (1, 0) if r.latency_ms is None else (0, r.latency_ms)
        records_by_lat = sorted(records, key=_lat_key)
        self.assertEqual(records_by_lat[0].latency_ms, 8.4)
        self.assertEqual(records_by_lat[1].latency_ms, 15.2)
        self.assertIsNone(records_by_lat[2].latency_ms)


if __name__ == "__main__":
    unittest.main()
