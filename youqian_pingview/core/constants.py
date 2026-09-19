# -*- coding: utf-8 -*-
"""
全局通用常量定义
解耦 UI 与 Core，避免轻量级引擎（如 Tkinter）对特定图形界面的硬编码耦合
"""

SAMPLE_TEXT = """# ==========================================
# 在下方输入需要探测的 IP 地址或主机名列表
# 支持以下常用格式 (每行一个目标，可带描述)：
# 1. 声明分组:      Group: 核心服务组 (支持双击折叠与展开)
# 2. 普通IP:        192.168.1.1
# 3. IP与描述:      192.168.1.1 核心交换机网关
# 4. 域名解析:      www.baidu.com 百度外网连通性
# 5. CIDR网段:      192.168.1.0/29 财务室子网 (自动展开)
# 6. IP连续范围:    192.168.1.10-192.168.1.20 打印机集群
# 7. TCP端口探测:   192.168.1.200:80 内网Web服务
# ==========================================
Group: 公共服务与DNS
127.0.0.1 本机环回
223.5.5.5 阿里公共DNS
114.114.114.114 114公共DNS

Group: 互联网门户
www.baidu.com 百度搜索引擎
"""

from .. import __version__ as APP_VERSION

APP_NAME = "YouQian PingView"
APP_DISPLAY_NAME = "YouQian 批量网络监控工具"
WINDOW_TITLE = f"{APP_NAME} v{APP_VERSION} - {APP_DISPLAY_NAME}"
