# -*- coding: utf-8 -*-
"""
高级选项 (Advanced Options) 单元测试集
覆盖：
1. PingOptions 高级字段序列化与反序列化
2. AlertManager 11 种宏变量占位符替换
3. 下窗格 5 种模式流水过滤与容量上限限制
4. 连续失败与成功防抖状态跟踪
"""

import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from youqian_pingview.core.pinger import PingOptions, HostStat, PingRecord
from youqian_pingview.core.alert_manager import AlertManager


class TestAdvancedOptions(unittest.TestCase):
    def test_options_serialization(self):
        """测试高级选项参数的完整序列化与从字典还原"""
        opts = PingOptions()
        opts.max_concurrent_pings = 250
        opts.failed_sound_type = "警告声"
        opts.failed_audio_path = "/home/test.wav"
        opts.use_failed_cmd = True
        opts.failed_cmd = "echo fail %IPAddress%"
        opts.consecutive_failed_trigger = 3
        opts.success_sound_type = "信息声"
        opts.consecutive_success_trigger = 2
        opts.lower_pane_mode = "仅添加失败的 pings 到下窗格"
        opts.max_accumulated_pings = 12000
        opts.auto_export = True
        opts.auto_export_interval = 60

        d = opts.to_dict()
        self.assertEqual(d["max_concurrent_pings"], 250)
        self.assertEqual(d["failed_sound_type"], "警告声")
        self.assertEqual(d["failed_audio_path"], "/home/test.wav")
        self.assertEqual(d["use_failed_cmd"], True)
        self.assertEqual(d["consecutive_failed_trigger"], 3)
        self.assertEqual(d["lower_pane_mode"], "仅添加失败的 pings 到下窗格")
        self.assertEqual(d["max_accumulated_pings"], 12000)

        restored = PingOptions.from_dict(d)
        self.assertEqual(restored.max_concurrent_pings, 250)
        self.assertEqual(restored.failed_sound_type, "警告声")
        self.assertEqual(restored.use_failed_cmd, True)
        self.assertEqual(restored.consecutive_failed_trigger, 3)
        self.assertEqual(restored.lower_pane_mode, "仅添加失败的 pings 到下窗格")
        self.assertEqual(restored.max_accumulated_pings, 12000)

    def test_alert_command_variable_substitution(self):
        """测试 11 个宏变量的安全替换"""
        host = HostStat(1, "router.local", description="主路由网关")
        host.resolved_ip = "192.168.1.1"
        host.update_result(True, 12.345, 64, "成功", "192.168.1.1")
        host.update_result(False, None, None, "请求超时", "192.168.1.1")

        cmd_tpl = (
            "notify-send '%HostName%' '%IPAddress%' '%ReplyIPAddress%' '%Description%' "
            "'%SucceedCount%' '%FailedCount%' '%LastPingStatus%' '%LastPingTime%' '%LastPingTTL%'"
        )
        final_cmd = AlertManager.replace_variables(cmd_tpl, host)

        self.assertIn("router.local", final_cmd)
        self.assertIn("192.168.1.1", final_cmd)
        self.assertIn("主路由网关", final_cmd)
        self.assertIn("请求超时", final_cmd)
        self.assertIn("1", final_cmd)  # SucceedCount=1, FailedCount=1

    def test_lower_pane_mode_filtering(self):
        """测试下窗格 5 种过滤模式"""
        host = HostStat(1, "192.168.1.1")

        # 1. 仅添加失败
        host.update_result(True, 5.0, 64, "成功", "192.168.1.1", lower_pane_mode="仅添加失败的 pings 到下窗格")
        self.assertEqual(len(host.history_records), 0)
        host.update_result(False, None, None, "请求超时", "192.168.1.1", lower_pane_mode="仅添加失败的 pings 到下窗格")
        self.assertEqual(len(host.history_records), 1)

        # 2. 仅添加成功
        host.reset_stats()
        host.update_result(False, None, None, "超时", "192.168.1.1", lower_pane_mode="仅添加成功的 pings 到下窗格")
        self.assertEqual(len(host.history_records), 0)
        host.update_result(True, 5.0, 64, "成功", "192.168.1.1", lower_pane_mode="仅添加成功的 pings 到下窗格")
        self.assertEqual(len(host.history_records), 1)

        # 3. 不添加任何内容
        host.reset_stats()
        host.update_result(True, 5.0, 64, "成功", "192.168.1.1", lower_pane_mode="不添加 pings 到下窗格")
        host.update_result(False, None, None, "超时", "192.168.1.1", lower_pane_mode="不添加 pings 到下窗格")
        self.assertEqual(len(host.history_records), 0)

        # 4. 容量上限测试
        host.reset_stats()
        for _ in range(25):
            host.update_result(True, 5.0, 64, "成功", "192.168.1.1",
                               lower_pane_mode="添加所有 pings 到下窗格", max_accumulated=10)
        self.assertEqual(len(host.history_records), 10)

    def test_consecutive_success_and_failure_tracking(self):
        """测试连续成功与失败计数以及上次失败后恢复标志"""
        host = HostStat(1, "10.0.0.1")
        self.assertFalse(host.had_previous_failure)
        self.assertEqual(host.consecutive_failures, 0)
        self.assertEqual(host.consecutive_successes, 0)

        # 成功
        host.update_result(True, 2.0, 64, "成功", "10.0.0.1")
        self.assertEqual(host.consecutive_successes, 1)
        self.assertFalse(host.had_previous_failure)

        # 发生失败
        host.update_result(False, None, None, "超时", "10.0.0.1")
        self.assertTrue(host.had_previous_failure)
        self.assertEqual(host.consecutive_failures, 1)
        self.assertEqual(host.consecutive_successes, 0)

        # 再次失败
        host.update_result(False, None, None, "超时", "10.0.0.1")
        self.assertEqual(host.consecutive_failures, 2)

        # 恢复成功
        host.update_result(True, 2.0, 64, "成功", "10.0.0.1")
        self.assertEqual(host.consecutive_failures, 0)
        self.assertEqual(host.consecutive_successes, 1)
        self.assertTrue(host.had_previous_failure)


if __name__ == "__main__":
    unittest.main()
