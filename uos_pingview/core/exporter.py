"""
数据导出模块：支持导出 HTML 报表、CSV 格式和纯文本制表符报表
完全对标 PingInfoView 的报告生成功能
"""

import csv
from datetime import datetime
from typing import List
from .pinger import HostStat


class Exporter:
    HEADERS = [
        "序号", "目标", "IP地址", "状态", "成功次数", "失败次数",
        "失败率(%)", "最后延迟(ms)", "平均延迟(ms)", "最小延迟(ms)", "最大延迟(ms)",
        "最后TTL", "连续失败", "最后成功时间", "最后失败时间", "描述"
    ]

    @staticmethod
    def _host_to_row(host: HostStat) -> List[str]:
        return [
            str(host.index),
            f"{host.target}:{host.port}" if host.port else host.target,
            host.resolved_ip or "--",
            host.last_status,
            str(host.success_count),
            str(host.failed_count),
            f"{host.failure_rate:.1f}%",
            f"{host.last_latency_ms:.2f}" if host.last_latency_ms is not None else "--",
            f"{host.avg_latency_ms:.2f}" if host.avg_latency_ms is not None else "--",
            f"{host.min_latency_ms:.2f}" if host.min_latency_ms is not None else "--",
            f"{host.max_latency_ms:.2f}" if host.max_latency_ms is not None else "--",
            str(host.last_ttl) if host.last_ttl is not None else "--",
            str(host.consecutive_failures),
            host.last_success_time or "--",
            host.last_failed_time or "--",
            host.description or ""
        ]

    @classmethod
    def export_csv(cls, hosts: List[HostStat], file_path: str):
        """导出为 UTF-8 BOM 编码的 CSV 文件 (兼容 Excel)"""
        with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(cls.HEADERS)
            for host in hosts:
                writer.writerow(cls._host_to_row(host))

    @classmethod
    def export_txt(cls, hosts: List[HostStat], file_path: str):
        """导出为制表符分隔的 TXT 文件"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\t".join(cls.HEADERS) + "\n")
            for host in hosts:
                f.write("\t".join(cls._host_to_row(host)) + "\n")

    @classmethod
    def export_html(cls, hosts: List[HostStat], file_path: str, title: str = "Ping 探测监控报告"):
        """导出为现代自适应美观 HTML 报表"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_hosts = len(hosts)
        alive_hosts = sum(1 for h in hosts if h.last_status in ("成功", "端口开放"))
        down_hosts = sum(1 for h in hosts if h.total_sent > 0 and h.last_status not in ("成功", "端口开放"))

        rows_html = []
        for host in hosts:
            row = cls._host_to_row(host)
            status = host.last_status
            if status in ("成功", "端口开放"):
                status_class = "status-success"
                row_class = "row-success"
            elif host.total_sent > 0:
                status_class = "status-fail"
                row_class = "row-fail"
            else:
                status_class = "status-none"
                row_class = ""

            tds = "".join([f"<td>{cell}</td>" for cell in row])
            rows_html.append(f"<tr class='{row_class}'>{tds}</tr>")

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - {now_str}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            background-color: #f4f6f9;
            color: #333;
            margin: 0;
            padding: 24px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: #fff;
            border-radius: 8px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.06);
            padding: 24px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #eef2f5;
            padding-bottom: 16px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
            color: #1e293b;
        }}
        .header .meta {{
            font-size: 14px;
            color: #64748b;
        }}
        .summary-cards {{
            display: flex;
            gap: 16px;
            margin-bottom: 24px;
        }}
        .card {{
            flex: 1;
            padding: 16px;
            border-radius: 8px;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
        }}
        .card .num {{
            font-size: 28px;
            font-weight: bold;
            margin-top: 4px;
        }}
        .card.total .num {{ color: #2563eb; }}
        .card.alive .num {{ color: #16a34a; }}
        .card.down .num {{ color: #dc2626; }}
        .table-responsive {{
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        th {{
            background: #f1f5f9;
            color: #475569;
            font-weight: 600;
            text-align: left;
            padding: 12px 10px;
            border-bottom: 2px solid #cbd5e1;
            white-space: nowrap;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #e2e8f0;
            white-space: nowrap;
        }}
        tr:hover {{
            background-color: #f8fafc;
        }}
        tr.row-fail {{
            background-color: #fff1f2;
        }}
        tr.row-fail:hover {{
            background-color: #ffe4e6;
        }}
        .status-success {{
            color: #16a34a;
            font-weight: 600;
        }}
        .status-fail {{
            color: #dc2626;
            font-weight: 600;
        }}
        .footer {{
            margin-top: 24px;
            text-align: center;
            font-size: 12px;
            color: #94a3b8;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>{title}</h1>
                <div class="meta">统信 UOS Desktop V25 原生探测监控生成</div>
            </div>
            <div class="meta">生成时间：{now_str}</div>
        </div>

        <div class="summary-cards">
            <div class="card total">
                <div>监控主机总数</div>
                <div class="num">{total_hosts}</div>
            </div>
            <div class="card alive">
                <div>正常存活数</div>
                <div class="num">{alive_hosts}</div>
            </div>
            <div class="card down">
                <div>异常超时数</div>
                <div class="num">{down_hosts}</div>
            </div>
        </div>

        <div class="table-responsive">
            <table>
                <thead>
                    <tr>{"".join([f"<th>{h}</th>" for h in cls.HEADERS])}</tr>
                </thead>
                <tbody>
                    {"".join(rows_html)}
                </tbody>
            </table>
        </div>

        <div class="footer">
            由 UOSPingView 自动生成 · 适配统信 UOS 桌面操作系统 V25
        </div>
    </div>
</body>
</html>
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
