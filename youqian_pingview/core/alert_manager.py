# -*- coding: utf-8 -*-
"""
报警管理与命令触发模块 (AlertManager)
对标原版 PingInfoView 高级选项：
1. 跨平台声音提示与音频文件播放 (Windows winsound / Linux pulse/alsa/canberra 兜底 QApplication.beep)
2. 失败/成功外部命令异步触发与 11 种宏变量占位符安全替换
3. 日志文件自动追加写入
"""

import os
import sys
import platform
import subprocess
import threading
from typing import Optional, Dict
from datetime import datetime

# 延迟导入，防止无 Qt 环境报错
try:
    from youqian_pingview.qt_compat import QApplication
except Exception:
    QApplication = None


class AlertManager:
    """负责高级警报声音、外部命令与日志记录的核心执行器"""

    @staticmethod
    def replace_variables(cmd_template: str, host) -> str:
        """
        替换命令模板中的 11 个原版 PingInfoView 宏变量：
        %HostName%, %IPAddress%, %ReplyIPAddress%, %Description%, %SucceedCount%,
        %FailedCount%, %LastPingStatus%, %LastPingTime%, %LastPingTTL%,
        %LastSucceedOn%, %LastFailedOn%
        """
        if not cmd_template:
            return ""

        latency_str = f"{host.last_latency_ms:.3f}" if getattr(host, "last_latency_ms", None) is not None else ""
        ttl_str = str(host.last_ttl) if getattr(host, "last_ttl", None) is not None else ""

        var_map = {
            "%HostName%": str(getattr(host, "hostname", "") or getattr(host, "target", "") or ""),
            "%IPAddress%": str(getattr(host, "resolved_ip", "") or getattr(host, "target", "") or ""),
            "%ReplyIPAddress%": str(getattr(host, "reply_ip", "") or getattr(host, "resolved_ip", "") or getattr(host, "target", "") or ""),
            "%Description%": str(getattr(host, "description", "") or ""),
            "%SucceedCount%": str(getattr(host, "success_count", 0)),
            "%FailedCount%": str(getattr(host, "failed_count", 0)),
            "%LastPingStatus%": str(getattr(host, "last_status", "") or ""),
            "%LastPingTime%": latency_str,
            "%LastPingTTL%": ttl_str,
            "%LastSucceedOn%": str(getattr(host, "last_success_time", "") or ""),
            "%LastFailedOn%": str(getattr(host, "last_failed_time", "") or ""),
        }

        result = cmd_template
        for var_name, var_val in var_map.items():
            result = result.replace(var_name, var_val)
            # 兼容不区分大小写
            result = result.replace(var_name.lower(), var_val)
            result = result.replace(var_name.upper(), var_val)

        return result

    @classmethod
    def execute_command_async(cls, command_str: str, host=None):
        """异步非阻塞执行外部系统命令"""
        if not command_str or not command_str.strip():
            return

        final_cmd = cls.replace_variables(command_str.strip(), host) if host else command_str.strip()

        def _worker():
            try:
                # 使用 shell 模式执行，并重定向防止阻塞或弹窗卡顿
                subprocess.Popen(
                    final_cmd,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL
                )
            except Exception as e:
                print(f"[警告] 执行外部报警命令失败 [{final_cmd}]: {e}", file=sys.stderr)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    @classmethod
    def play_sound(cls, sound_type: str, audio_path: str = ""):
        """跨平台播放指定类型声音或音频文件，确保永不崩溃"""
        is_windows = platform.system().lower() == "windows"

        def _play():
            try:
                # 1. 播放自定义音频文件
                if sound_type == "播放 WAV/MP3 文件" or (audio_path and os.path.isfile(audio_path)):
                    if audio_path and os.path.isfile(audio_path):
                        if is_windows:
                            import winsound
                            winsound.PlaySound(audio_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                            return
                        else:
                            # Linux 尝试使用常见音频后端命令播放
                            for player in ["paplay", "aplay", "canberra-gtk-play", "ffplay -nodisp -autoexit", "mpv --no-video"]:
                                p_bin = player.split()[0]
                                if subprocess.call(["which", p_bin], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
                                    subprocess.Popen(f"{player} \"{audio_path}\"", shell=True,
                                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                    return
                    # 若文件不存在或 Linux 无可用音频播放器，回退到提示音
                    cls._system_beep(sound_type, is_windows)
                    return

                # 2. 播放内置系统事件音
                cls._system_beep(sound_type, is_windows)
            except Exception as e:
                try:
                    cls._system_beep("默认声", is_windows)
                except Exception:
                    pass

        threading.Thread(target=_play, daemon=True).start()

    @classmethod
    def _system_beep(cls, sound_type: str, is_windows: bool):
        """调用底层系统蜂鸣/通知音"""
        if is_windows:
            import winsound
            mb_map = {
                "简单声": winsound.MB_OK,
                "默认声": 0xFFFFFFFF,
                "询问声": winsound.MB_ICONQUESTION,
                "信息声": winsound.MB_ICONASTERISK,
                "警告声": winsound.MB_ICONEXCLAMATION,
                "错误声": winsound.MB_ICONHAND,
            }
            sound_id = mb_map.get(sound_type, winsound.MB_ICONASTERISK)
            if sound_id == 0xFFFFFFFF:
                winsound.MessageBeep(0xFFFFFFFF)
            else:
                winsound.MessageBeep(sound_id)
        else:
            # Linux / UOS 统信系统
            # 优先尝试 canberra-gtk-play
            canberra_sound = {
                "简单声": "bell",
                "默认声": "bell",
                "询问声": "dialog-question",
                "信息声": "message",
                "警告声": "dialog-warning",
                "错误声": "dialog-error",
            }.get(sound_type, "bell")

            played = False
            if subprocess.call(["which", "canberra-gtk-play"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
                ret = subprocess.call(["canberra-gtk-play", "-i", canberra_sound], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if ret == 0:
                    played = True

            if not played and QApplication is not None:
                try:
                    QApplication.beep()
                    played = True
                except Exception:
                    pass

            if not played:
                # 终端控制字符回退
                sys.stdout.write("\a")
                sys.stdout.flush()

    @staticmethod
    def append_log_entry(filename: str, file_type: str, mode: str, host, record):
        """根据模式将单条 Ping 记录追加到指定日志文件中"""
        if not filename:
            return

        is_success = (record.status in ("成功", "端口开放"))
        if mode == "仅记录失败的 pings" and is_success:
            return
        if mode == "仅记录成功的 pings" and not is_success:
            return

        def _write():
            try:
                os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
                file_exists = os.path.exists(filename) and os.path.getsize(filename) > 0

                delimiter = "\t" if "制表符" in file_type else ","
                now_str = record.timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                lat_str = f"{record.latency_ms:.3f}" if record.latency_ms is not None else "--"
                ttl_str = str(record.ttl) if record.ttl is not None else "--"

                fields = [
                    now_str,
                    getattr(host, "target", ""),
                    record.resolved_ip or getattr(host, "resolved_ip", "") or "",
                    record.status,
                    lat_str,
                    ttl_str,
                    str(record.sequence),
                    getattr(host, "description", "")
                ]

                with open(filename, "a", encoding="utf-8") as f:
                    if not file_exists:
                        # 写入首行表头
                        headers = ["时间", "主机名", "响应IP", "状态", "耗时(ms)", "TTL", "计数", "描述"]
                        f.write(delimiter.join(headers) + "\n")
                    # 安全转义 CSV
                    row_parts = []
                    for val in fields:
                        val_s = str(val).replace('"', '""')
                        if delimiter in val_s or '"' in val_s or "\n" in val_s:
                            val_s = f'"{val_s}"'
                        row_parts.append(val_s)
                    f.write(delimiter.join(row_parts) + "\n")
            except Exception as e:
                print(f"[警告] 写入 Ping 日志文件失败 [{filename}]: {e}", file=sys.stderr)

        threading.Thread(target=_write, daemon=True).start()
