# -*- coding: utf-8 -*-
"""
Youqian-PingView 自动化打包与版本自动递增脚本
构建产物统一输出至 dist/ 目录，彻底杜绝散落在项目根目录。
每次运行本脚本，版本号自动递增 (例如 1.0.5 -> 1.0.6 ...)
"""

import os
import re
import sys
import time
import glob
import shutil
import tarfile
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import build_deb


def get_current_version(base_dir: str) -> str:
    """读取当前版本号"""
    init_path = os.path.join(base_dir, "youqian_pingview", "__init__.py")
    if os.path.exists(init_path):
        with open(init_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("__version__"):
                    return line.split("=")[1].strip().strip("\"'")
    return "1.0.5"


def bump_version(current_ver: str) -> str:
    """将版本号最后一位小版本号自增 1 (如 1.0.5 -> 1.0.6)"""
    parts = current_ver.split(".")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
        return ".".join(parts)
    except ValueError:
        return f"{current_ver}.1"


def update_file_text(file_path: str, old_ver: str, new_ver: str):
    """安全更新文件中的版本号"""
    if not os.path.exists(file_path):
        return
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    new_content = content.replace(old_ver, new_ver)
    if new_content != content:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)


def clean_old_build_artifacts(base_dir: str, dist_dir: str):
    """清理根目录与 dist 目录下的旧打包文件，确保根目录绝不散落构建包"""
    # 1. 彻底清除根目录的历史残留包
    root_patterns = [
        os.path.join(base_dir, "youqian-pingview_*_all.deb"),
        os.path.join(base_dir, "Youqian-PingView-v*-Linux.tar.gz"),
        os.path.join(base_dir, "Youqian-PingView-v*-Linux.zip"),
        os.path.join(base_dir, "Youqian-PingView-统信UOS专版-一键安装合集-*.zip")
    ]
    for pattern in root_patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except Exception:
                pass

    # 2. 清理 dist 目录中的旧包
    if os.path.exists(dist_dir):
        for f in os.listdir(dist_dir):
            fpath = os.path.join(dist_dir, f)
            if os.path.isfile(fpath) and f.endswith((".deb", ".tar.gz", ".zip")):
                try:
                    os.remove(fpath)
                except Exception:
                    pass


def run_package(auto_bump: bool = True):
    os.makedirs(DIST_DIR, exist_ok=True)
    old_version = get_current_version(BASE_DIR)

    if auto_bump:
        new_version = bump_version(old_version)
        print("\n==================================================")
        print(f"[*] [版本号自动递增] {old_version}  ===>  {new_version}")
        print(f"[*] [构建产物输出目录] {DIST_DIR}")
        print("==================================================")

        # 1. 更新 youqian_pingview/__init__.py
        init_path = os.path.join(BASE_DIR, "youqian_pingview", "__init__.py")
        with open(init_path, "w", encoding="utf-8") as f:
            f.write(f'"""\nYouqian-PingView 包根模块\n"""\n__version__ = "{new_version}"\n')

        # 2. 更新其他文档与脚本中的版本标记
        update_file_text(os.path.join(BASE_DIR, "README.md"), old_version, new_version)
        update_file_text(os.path.join(BASE_DIR, "README_UOS.md"), old_version, new_version)
        update_file_text(os.path.join(BASE_DIR, "upload_release.py"), old_version, new_version)
    else:
        new_version = old_version
        print(f"\n[*] [打包保持当前版本] {new_version}")
        print(f"[*] [构建产物输出目录] {DIST_DIR}")

    # 清理所有位置的旧包
    clean_old_build_artifacts(BASE_DIR, DIST_DIR)

    # 3. 构建 DEB 包 (输出至 dist 目录)
    print(f"\n[1/3] 正在构建最新 Debian / 统信 UOS DEB 安装包...")
    deb_name = f"youqian-pingview_{new_version}_all.deb"
    deb_path = os.path.join(DIST_DIR, deb_name)
    build_deb.build_deb_package(BASE_DIR, deb_path, version=new_version)

    # 4. 在 dist 目录下创建临时打包目录，杜绝污染项目根目录
    pkg_folder_name = f"Youqian-PingView-v{new_version}-Linux"
    temp_pkg_dir = os.path.join(DIST_DIR, pkg_folder_name)
    if os.path.exists(temp_pkg_dir):
        shutil.rmtree(temp_pkg_dir)
    os.makedirs(temp_pkg_dir, exist_ok=True)

    files_to_include = [
        "run.py",
        "run_uos.sh",
        "install_uos.sh",
        "uninstall_uos.sh",
        "build_deb.py",
        "README_UOS.md",
        "README.md",
        "ABOUT.md",
        "LICENSE",
    ]

    for fname in files_to_include:
        src = os.path.join(BASE_DIR, fname)
        dst = os.path.join(temp_pkg_dir, fname)
        if os.path.exists(src):
            with open(src, "rb") as f:
                content = f.read()
            if fname.endswith((".sh", ".py", ".md", ".txt", ".ini", "LICENSE")):
                content = content.replace(b"\r\n", b"\n")
            with open(dst, "wb") as f:
                f.write(content)

    # 复制刚刚生成的 deb 安装包进便携目录
    shutil.copyfile(deb_path, os.path.join(temp_pkg_dir, deb_name))

    # 复制代码核心目录
    dst_code_dir = os.path.join(temp_pkg_dir, "youqian_pingview")
    shutil.copytree(
        os.path.join(BASE_DIR, "youqian_pingview"),
        dst_code_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )

    # 统一 LF 换行符
    for root, _, files in os.walk(dst_code_dir):
        for f in files:
            if f.endswith((".py", ".sh", ".md", ".ini", ".svg")):
                fpath = os.path.join(root, f)
                with open(fpath, "rb") as fp:
                    c = fp.read().replace(b"\r\n", b"\n")
                with open(fpath, "wb") as fp:
                    fp.write(c)

    # 5. 构建 tar.gz (带 0755 权限，输出至 dist 目录)
    print(f"[2/3] 正在生成 {pkg_folder_name}.tar.gz ...")
    tar_gz_path = os.path.join(DIST_DIR, f"{pkg_folder_name}.tar.gz")
    with tarfile.open(tar_gz_path, "w:gz") as tar:
        for root, dirs, files in os.walk(temp_pkg_dir):
            rel_root = os.path.relpath(root, DIST_DIR).replace("\\", "/")
            dir_ti = tar.gettarinfo(root, arcname=rel_root)
            dir_ti.mode = 0o755
            tar.addfile(dir_ti)
            for f in files:
                fpath = os.path.join(root, f)
                arcname = f"{rel_root}/{f}"
                ti = tar.gettarinfo(fpath, arcname=arcname)
                if f.endswith((".sh", ".py", ".deb")):
                    ti.mode = 0o755
                else:
                    ti.mode = 0o644
                with open(fpath, "rb") as fp:
                    tar.addfile(ti, fp)

    # 6. 构建 zip (带 POSIX 0755 属性，输出至 dist 目录)
    print(f"[3/3] 正在生成 {pkg_folder_name}.zip ...")
    zip_path = os.path.join(DIST_DIR, f"{pkg_folder_name}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(temp_pkg_dir):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, DIST_DIR).replace("\\", "/")
                with open(full, "rb") as fp:
                    data = fp.read()
                zinfo = zipfile.ZipInfo(rel)
                zinfo.date_time = time.localtime(time.time())[:6]
                zinfo.compress_type = zipfile.ZIP_DEFLATED
                if f.endswith((".sh", ".py", ".deb")):
                    zinfo.external_attr = 0o755 << 16
                else:
                    zinfo.external_attr = 0o644 << 16
                zf.writestr(zinfo, data)

    # 7. 一键合集 zip (输出至 dist 目录)
    col_zip_path = os.path.join(DIST_DIR, f"Youqian-PingView-统信UOS专版-一键安装合集-v{new_version}.zip")
    shutil.copyfile(zip_path, col_zip_path)

    # 清理临时目录
    shutil.rmtree(temp_pkg_dir)

    print("\n==================================================")
    print(f"[完成] 打包成功！所有文件已统一保存在 dist/ 目录下：")
    print(f"1. DEB 安装包:  {deb_path} ({os.path.getsize(deb_path)/1024:.1f} KB)")
    print(f"2. Linux 压缩包: {tar_gz_path} ({os.path.getsize(tar_gz_path)/1024:.1f} KB)")
    print(f"3. 通用 Zip 包:  {zip_path} ({os.path.getsize(zip_path)/1024:.1f} KB)")
    print(f"4. 一键安装合集: {col_zip_path} ({os.path.getsize(col_zip_path)/1024:.1f} KB)")
    print("==================================================")
    return new_version


if __name__ == "__main__":
    auto_bump = "--no-bump" not in sys.argv
    run_package(auto_bump=auto_bump)
