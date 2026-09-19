"""
GitHub Release 发布与二进制资产自动上传脚本
"""

import json
import os
import subprocess
import urllib.error
import urllib.request


def get_github_token():
    p = subprocess.Popen(
        ['git', 'credential', 'fill'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    out, _ = p.communicate('protocol=https\nhost=github.com\n\n')
    for line in out.strip().split('\n'):
        if line.startswith('password='):
            return line.split('=', 1)[1]
    return ''


def main():
    token = get_github_token()
    if not token:
        print('[错误] 未能从本地 Git Credential 中获取到 GitHub Token')
        return

    repo = 'thousy/Youqian-PingView'
    tag = 'v1.0.2'
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Youqian-PingView-Release-Bot'
    }

    release_notes = """## 🌟 Youqian PingView v1.0.2 发布说明

专为 **Linux / 统信 UOS 桌面操作系统** 打造的原生图形化多目标批量网络探测与监控工具，深度对标 Windows 经典 PingInfoView。

### 🚀 核心更新与特性
- **双引擎自适应架构**：首选 PyQt5 现代高清大盘；未激活/离线环境自动回退至零依赖原生引擎，100% 确保开箱即用。
- **100% 原生 IPv6 深度支持**：支持 IPv6 单地址、`[IPv6]:端口` TCP 探测及双栈域名解析，自动抓取 `HLIM` 跳数与延迟。
- **多选与规范复制**：按住 `Ctrl` 任意跳选（如 1、3、5 行），按住 `Shift` 范围连选；`Ctrl+C` 复制整行带表头，粘入 Excel 自动对齐。
- **经典属性窗口**：鼠标双击或右键「属性 (Alt+Enter)」弹出 1:1 独立属性面板，汇总 20+ 项参数指标。
- **列宽自由调节**：下窗格时间列默认加宽至 165px 绝不截断，所有列均支持鼠标自由拖拽缩放。
- **活动故障实时呈现**：在「仅显示失败」视图下，一旦有新故障毫秒级自动弹现在页面上；支持右键「禁用此项」立即隐藏。

### 📦 安装包与资产说明
1. **`youqian-pingview_1.0.17_all.deb`**：统信 UOS / Debian 标准安装包，下载后直接双击一键安装；
2. **`Youqian-PingView-v1.0.17-Linux.tar.gz`**：Linux 绿色免安装运行合集（推荐，解压直接 `./run_uos.sh` 运行）；
3. **`Youqian-PingView-v1.0.17-Linux.zip`**：通用免安装合集压缩包。
"""

    payload = {
        'tag_name': tag,
        'name': f'Youqian PingView {tag} 正式发布版 (统信 UOS / Linux 专版)',
        'body': release_notes,
        'draft': False,
        'prerelease': False
    }

    # 1. 创建 Release
    rel_url = f'https://api.github.com/repos/{repo}/releases'
    req = urllib.request.Request(
        rel_url,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST'
    )

    try:
        with urllib.request.urlopen(req) as resp:
            rel_data = json.loads(resp.read().decode('utf-8'))
            print(f'[成功] Release 创建成功，ID: {rel_data["id"]}')
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8')
        if 'already_exists' in err_msg:
            tag_url = f'https://api.github.com/repos/{repo}/releases/tags/{tag}'
            get_req = urllib.request.Request(tag_url, headers=headers)
            with urllib.request.urlopen(get_req) as resp:
                rel_data = json.loads(resp.read().decode('utf-8'))
                print(f'[提示] Release 已存在，ID: {rel_data["id"]}')
        else:
            print(f'[失败] 创建 Release 失败: {e.code}, {err_msg}')
            return

    release_id = rel_data['id']
    upload_base = f'https://uploads.github.com/repos/{repo}/releases/{release_id}/assets'

    # 2. 上传二进制 Assets (从 dist/ 目录读取)
    base_dir = r'd:\AI_Project\pinginfoview3.5'
    dist_dir = os.path.join(base_dir, 'dist')
    assets = [
        ('youqian-pingview_1.0.17_all.deb', 'application/vnd.debian.binary-package', os.path.join(dist_dir, 'youqian-pingview_1.0.17_all.deb')),
        ('Youqian-PingView-v1.0.17-Linux.tar.gz', 'application/gzip', os.path.join(dist_dir, 'Youqian-PingView-v1.0.17-Linux.tar.gz')),
        ('Youqian-PingView-v1.0.17-Linux.zip', 'application/zip', os.path.join(dist_dir, 'Youqian-PingView-v1.0.17-Linux.zip'))
    ]

    for name, ctype, path in assets:
        if not os.path.exists(path):
            print(f'[警告] 文件不存在，跳过: {path}')
            continue

        print(f'正在上传资产: {name} (大小: {os.path.getsize(path)} 字节)...')
        with open(path, 'rb') as fp:
            data = fp.read()

        upload_url = f'{upload_base}?name={name}'
        up_headers = headers.copy()
        up_headers['Content-Type'] = ctype
        up_headers['Content-Length'] = str(len(data))

        up_req = urllib.request.Request(upload_url, data=data, headers=up_headers, method='POST')
        try:
            with urllib.request.urlopen(up_req) as up_resp:
                print(f'  [完成] {name} 成功上传至 GitHub Release！')
        except urllib.error.HTTPError as e:
            res_str = e.read().decode('utf-8', errors='ignore')
            if 'already_exists' in res_str:
                print(f'  [提示] 资产 {name} 已经存在于 Release 中。')
            else:
                print(f'  [异常] {name} 上传失败: {e.code}, {res_str[:150]}')

    print('\n🎉 Youqian PingView 所有 Release 资产已全部成功发布至 GitHub！')
    print(f'查看地址: https://github.com/{repo}/releases/tag/{tag}')


if __name__ == '__main__':
    main()
