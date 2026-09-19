#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Youqian-PingView 绿色免安装直接启动脚本
终端直接执行：python3 run.py
"""
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from youqian_pingview.main import main

if __name__ == "__main__":
    main()
