"""
图标组件与 Qt 兼容层单元测试
确保 AppIcons、create_action_icon、create_status_icon 以及无依赖兜底机制永不抛出 NameError 或 AttributeError
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from youqian_pingview.resources.icons import AppIcons, create_action_icon, create_status_icon


class TestIconsAndCompat(unittest.TestCase):
    def test_app_icons_instantiation(self):
        """测试单例 AppIcons 获取及所有默认图标均可正常实例化"""
        icons = AppIcons.get()
        self.assertIsNotNone(icons)
        self.assertIsNotNone(icons.green_light)
        self.assertIsNotNone(icons.red_light)
        self.assertIsNotNone(icons.gray_light)
        self.assertIsNotNone(icons.yellow_light)
        self.assertIsNotNone(icons.start)
        self.assertIsNotNone(icons.stop)
        self.assertIsNotNone(icons.add)
        self.assertIsNotNone(icons.clear)
        self.assertIsNotNone(icons.settings)
        self.assertIsNotNone(icons.export)
        self.assertIsNotNone(icons.columns)
        self.assertIsNotNone(icons.sort_az)

    def test_create_action_icon_all_types(self):
        """测试所有类型动作图标包括 sort_az 不会报 QFont 未定义或属性错误"""
        for action_type in ["start", "stop", "add", "clear", "settings", "export", "columns", "sort_az"]:
            icon = create_action_icon(action_type)
            self.assertIsNotNone(icon)

    def test_create_status_icon(self):
        """测试自绘状态灯生成"""
        icon = create_status_icon("#22c55e", size=16)
        self.assertIsNotNone(icon)


if __name__ == "__main__":
    unittest.main()
