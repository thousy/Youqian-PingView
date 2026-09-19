"""
用于构建统信 UOS / Debian 标准 .deb 安装包的自动化构建工具 (v1.0.2)
采用 双引擎架构 (PyQt5 + Python原生)，彻底免除 401 商业源鉴权拦截问题
"""

import io
import os
import tarfile
import time


def create_ar_archive(files: list, output_path: str):
    with open(output_path, "wb") as ar:
        ar.write(b"!<arch>\n")

        for name, data, mtime, mode in files:
            name_bytes = name.encode("ascii").ljust(16)
            mtime_bytes = str(int(mtime)).encode("ascii").ljust(12)
            uid_bytes = b"0".ljust(6)
            gid_bytes = b"0".ljust(6)
            mode_bytes = oct(mode)[2:].encode("ascii").ljust(8)
            size_bytes = str(len(data)).encode("ascii").ljust(10)
            trailer = b"\x60\n"

            header = name_bytes + mtime_bytes + uid_bytes + gid_bytes + mode_bytes + size_bytes + trailer
            ar.write(header)
            ar.write(data)
            if len(data) % 2 != 0:
                ar.write(b"\n")


def get_version(source_dir: str) -> str:
    """自动读取 youqian_pingview/__init__.py 中的真实版本号"""
    init_path = os.path.join(source_dir, "youqian_pingview", "__init__.py")
    if os.path.exists(init_path):
        with open(init_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("__version__"):
                    return line.split("=")[1].strip().strip("\"'")
    return "1.0.3"


def build_deb_package(source_dir: str, output_deb_path: str, version: str = None):
    now = time.time()

    # 1. 创建 debian-binary
    debian_binary = b"2.0\n"

    # 2. 创建 control.tar.gz
    # 注意: python3-pyqt5 列为 Recommends 而非 Depends，避免未激活 UOS 官方源 401 导致安装中断
    Version = version or get_version(source_dir)
    control_content = f"""Package: youqian-pingview
Version: {Version}
Section: net
Priority: optional
Architecture: all
Depends: python3 (>= 3.7), iputils-ping
Recommends: python3-pyqt5
Maintainer: MoMo <momo@chinauos.com>
Installed-Size: 220
Description: YouQian 批量网络监控工具 (PingInfoView 原生版)
 专为统信 UOS Desktop V25 与 Linux 深度定制的原生图形化多目标网络连通性监控工具。
 采用经典双窗格设计，支持多目标并发 Ping 探测、CIDR 网段批量展开、
 连续丢包告警、HTML/CSV 统计报表导出等。内置双引擎保障，零依赖开箱即用。
""".replace("\r\n", "\n")

    postinst_content = """#!/bin/sh
set -e
if which update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if which gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi
exit 0
""".replace("\r\n", "\n")

    control_buf = io.BytesIO()
    with tarfile.open(fileobj=control_buf, mode="w:gz") as tar:
        ti = tarfile.TarInfo(name="./control")
        ti.size = len(control_content.encode("utf-8"))
        ti.mtime = int(now)
        ti.mode = 0o644
        tar.addfile(ti, io.BytesIO(control_content.encode("utf-8")))

        ti_p = tarfile.TarInfo(name="./postinst")
        ti_p.size = len(postinst_content.encode("utf-8"))
        ti_p.mtime = int(now)
        ti_p.mode = 0o755
        tar.addfile(ti_p, io.BytesIO(postinst_content.encode("utf-8")))

    control_tar_gz = control_buf.getvalue()

    # 3. 创建 data.tar.gz
    data_buf = io.BytesIO()
    with tarfile.open(fileobj=data_buf, mode="w:gz") as tar:
        def add_dir(tar_path):
            ti = tarfile.TarInfo(name=tar_path)
            ti.type = tarfile.DIRTYPE
            ti.mode = 0o755
            ti.mtime = int(now)
            tar.addfile(ti)

        def add_file(tar_path, local_content_bytes, mode=0o644):
            ti = tarfile.TarInfo(name=tar_path)
            ti.size = len(local_content_bytes)
            ti.mode = mode
            ti.mtime = int(now)
            tar.addfile(ti, io.BytesIO(local_content_bytes))

        # 建立目录
        dirs = [
            "./opt",
            "./opt/youqian-pingview",
            "./usr",
            "./usr/bin",
            "./usr/share",
            "./usr/share/applications",
            "./usr/share/pixmaps"
        ]
        for d in dirs:
            add_dir(d)

        # 添加源码到 /opt/youqian-pingview/youqian_pingview
        src_root = os.path.join(source_dir, "youqian_pingview")
        for root, _, files in os.walk(src_root):
            if "__pycache__" in root:
                continue
            rel_dir = os.path.relpath(root, src_root)
            target_dir = "./opt/youqian-pingview/youqian_pingview" if rel_dir == "." else f"./opt/youqian-pingview/youqian_pingview/{rel_dir.replace(os.sep, '/')}"
            add_dir(target_dir)
            for f in files:
                if f.endswith(".pyc"):
                    continue
                local_path = os.path.join(root, f)
                with open(local_path, "rb") as fp:
                    content = fp.read()
                if f.endswith((".py", ".desktop", ".sh", ".ini", ".txt", ".md")):
                    content = content.replace(b"\r\n", b"\n")
                add_file(f"{target_dir}/{f}", content, mode=0o644)

        # 增加 /opt/youqian-pingview/main.py 引导入口
        opt_main = """#!/usr/bin/env python3
import sys
import os

_base = os.path.dirname(os.path.abspath(__file__))
if _base not in sys.path:
    sys.path.insert(0, _base)

from youqian_pingview.main import main

if __name__ == "__main__":
    main()
""".replace("\r\n", "\n").encode("utf-8")
        add_file("./opt/youqian-pingview/main.py", opt_main, mode=0o755)

        # 启动脚本
        runner_sh = """#!/bin/bash
export PYTHONPATH="/opt/youqian-pingview:${PYTHONPATH}"
exec /usr/bin/python3 /opt/youqian-pingview/main.py "$@"
""".replace("\r\n", "\n").encode("utf-8")
        add_file("./usr/bin/youqian-pingview", runner_sh, mode=0o755)

        # 桌面快捷方式
        desktop_entry = """[Desktop Entry]
Name=Youqian-PingView
Name[zh_CN]=YouQian 批量网络监控工具
GenericName=Ping Monitor
GenericName[zh_CN]=网络连通性探测
Comment=Multi-Host Ping Monitor for Linux Desktop
Comment[zh_CN]=YouQian 批量多目标网络连通性监控工具
Exec=/usr/bin/youqian-pingview %F
Icon=/usr/share/pixmaps/youqian-pingview.svg
Terminal=false
Type=Application
Categories=Network;System;Utility;
Keywords=ping;network;icmp;uos;monitor;youqian;
StartupNotify=true
""".replace("\r\n", "\n").encode("utf-8")
        add_file("./usr/share/applications/youqian-pingview.desktop", desktop_entry, mode=0o644)

        # 矢量图标
        icon_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#2563eb" />
      <stop offset="100%" stop-color="#1d4ed8" />
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="url(#bg)" />
  <circle cx="64" cy="64" r="48" fill="none" stroke="#60a5fa" stroke-width="3" opacity="0.4" />
  <circle cx="64" cy="64" r="32" fill="none" stroke="#93c5fd" stroke-width="3" opacity="0.6" />
  <circle cx="64" cy="64" r="16" fill="none" stroke="#bfdbfe" stroke-width="3" opacity="0.8" />
  <circle cx="64" cy="64" r="7" fill="#ffffff" />
  <polyline points="20,64 42,64 52,36 64,92 76,46 86,64 108,64" fill="none" stroke="#22c55e" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" />
</svg>
""".replace("\r\n", "\n").encode("utf-8")
        add_file("./usr/share/pixmaps/youqian-pingview.svg", icon_svg, mode=0o644)

    data_tar_gz = data_buf.getvalue()

    # 4. 生成 .deb
    ar_members = [
        ("debian-binary", debian_binary, now, 0o644),
        ("control.tar.gz", control_tar_gz, now, 0o644),
        ("data.tar.gz", data_tar_gz, now, 0o644),
    ]
    create_ar_archive(ar_members, output_deb_path)
    print(f"[完成] deb 构建成功: {output_deb_path}, 大小: {os.path.getsize(output_deb_path)}")


if __name__ == "__main__":
    import sys
    base_dir = os.path.dirname(os.path.abspath(__file__))
    ver = get_version(base_dir)
    output_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(base_dir, f"youqian-pingview_{ver}_all.deb")
    build_deb_package(base_dir, output_path, version=ver)
