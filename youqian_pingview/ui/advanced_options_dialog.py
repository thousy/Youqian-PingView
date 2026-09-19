# -*- coding: utf-8 -*-
"""
高级选项对话框 (AdvancedOptionsDialog)
1:1 深度像素级还原原版 PingInfoView 高级选项界面
"""

import os
try:
    from youqian_pingview.qt_compat import (
        QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
        QSpinBox, QComboBox, QCheckBox, QLineEdit, QPushButton,
        QWidget, QFileDialog, Qt, QMessageBox
    )
    from youqian_pingview.core.pinger import PingOptions
    from youqian_pingview.core.alert_manager import AlertManager
except (ImportError, ModuleNotFoundError, ValueError):
    from qt_compat import (
        QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
        QSpinBox, QComboBox, QCheckBox, QLineEdit, QPushButton,
        QWidget, QFileDialog, Qt, QMessageBox
    )
    from core.pinger import PingOptions
    from core.alert_manager import AlertManager


class AdvancedOptionsDialog(QDialog):
    """高级选项对话框：涵盖并发限制、声音报警、命令触发、日志记录、下窗格模式与自动定时导出"""

    def __init__(self, options: PingOptions, parent=None):
        super().__init__(parent)
        self.options = options
        self.setWindowTitle("高级选项")
        self.setMinimumWidth(560)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 12, 14, 12)

        # 1. 同时 Ping 的最大数量
        row_concur = QHBoxLayout()
        row_concur.addWidget(QLabel("同时Ping的最大数量："))
        self.spin_concur = QSpinBox()
        self.spin_concur.setRange(1, 2000)
        self.spin_concur.setValue(self.options.max_concurrent_pings)
        self.spin_concur.setFixedWidth(100)
        row_concur.addWidget(self.spin_concur)
        row_concur.addStretch()
        layout.addLayout(row_concur)

        # 2. 失败声音
        row_fail_sound = QHBoxLayout()
        row_fail_sound.addWidget(QLabel("Ping 失败时声音类型："))
        self.combo_fail_sound = QComboBox()
        sound_types = ["简单声", "默认声", "询问声", "信息声", "警告声", "错误声", "播放 WAV/MP3 文件"]
        for st in sound_types:
            self.combo_fail_sound.addItem(st)
        self.combo_fail_sound.setCurrentText(self.options.failed_sound_type)
        row_fail_sound.addWidget(self.combo_fail_sound, 1)

        btn_test_fail_sound = QPushButton("声音测试")
        btn_test_fail_sound.clicked.connect(lambda: AlertManager.play_sound(
            self.combo_fail_sound.currentText(), self.txt_fail_audio.text().strip()
        ))
        row_fail_sound.addWidget(btn_test_fail_sound)
        layout.addLayout(row_fail_sound)

        # 失败音频文件路径
        row_fail_file = QHBoxLayout()
        self.txt_fail_audio = QLineEdit()
        self.txt_fail_audio.setPlaceholderText("选择或输入 .wav / .mp3 音频文件路径")
        self.txt_fail_audio.setText(self.options.failed_audio_path)
        row_fail_file.addWidget(self.txt_fail_audio, 1)

        btn_browse_fail_audio = QPushButton("...")
        btn_browse_fail_audio.setFixedWidth(36)
        btn_browse_fail_audio.clicked.connect(lambda: self._browse_audio(self.txt_fail_audio))
        row_fail_file.addWidget(btn_browse_fail_audio)
        layout.addLayout(row_fail_file)

        # 3. 失败命令与变量说明
        self.chk_fail_cmd = QCheckBox("在失败的 ping 执行下列命令：")
        self.chk_fail_cmd.setChecked(self.options.use_failed_cmd)
        layout.addWidget(self.chk_fail_cmd)

        tip_vars = QLabel(
            "你可以在失败的命令中使用下列变量：\n"
            "%HostName%  %IPAddress%  %ReplyIPAddress%  %Description%  %SucceedCount%  %FailedCount%\n"
            "%LastPingStatus%  %LastPingTime%  %LastPingTTL%  %LastSucceedOn%  %LastFailedOn%"
        )
        tip_vars.setStyleSheet("color: #475569; font-size: 11px; margin-left: 18px;")
        layout.addWidget(tip_vars)

        self.txt_fail_cmd = QLineEdit()
        self.txt_fail_cmd.setPlaceholderText("例如: notify-send 'Ping报警' '主机 %HostName% (%IPAddress%) 离线！'")
        self.txt_fail_cmd.setText(self.options.failed_cmd)
        self.txt_fail_cmd.setEnabled(self.options.use_failed_cmd)
        self.chk_fail_cmd.toggled.connect(self.txt_fail_cmd.setEnabled)
        layout.addWidget(self.txt_fail_cmd)

        # 4. 连续失败阈值
        row_fail_cnt = QHBoxLayout()
        row_fail_cnt.addWidget(QLabel("连续失败 pings 数时触发命令失败/声音警报："))
        self.spin_fail_cnt = QSpinBox()
        self.spin_fail_cnt.setRange(1, 9999)
        self.spin_fail_cnt.setValue(self.options.consecutive_failed_trigger)
        self.spin_fail_cnt.setFixedWidth(80)
        row_fail_cnt.addWidget(self.spin_fail_cnt)
        row_fail_cnt.addStretch()
        layout.addLayout(row_fail_cnt)

        # 5. 成功声音
        row_succ_sound = QHBoxLayout()
        row_succ_sound.addWidget(QLabel("成功 ping 时的声音类型："))
        self.combo_succ_sound = QComboBox()
        for st in sound_types:
            self.combo_succ_sound.addItem(st)
        self.combo_succ_sound.setCurrentText(self.options.success_sound_type)
        row_succ_sound.addWidget(self.combo_succ_sound, 1)

        btn_test_succ_sound = QPushButton("声音测试")
        btn_test_succ_sound.clicked.connect(lambda: AlertManager.play_sound(
            self.combo_succ_sound.currentText(), self.txt_succ_audio.text().strip()
        ))
        row_succ_sound.addWidget(btn_test_succ_sound)
        layout.addLayout(row_succ_sound)

        # 成功音频文件路径
        row_succ_file = QHBoxLayout()
        self.txt_succ_audio = QLineEdit()
        self.txt_succ_audio.setPlaceholderText("选择或输入 .wav / .mp3 音频文件路径")
        self.txt_succ_audio.setText(self.options.success_audio_path)
        row_succ_file.addWidget(self.txt_succ_audio, 1)

        btn_browse_succ_audio = QPushButton("...")
        btn_browse_succ_audio.setFixedWidth(36)
        btn_browse_succ_audio.clicked.connect(lambda: self._browse_audio(self.txt_succ_audio))
        row_succ_file.addWidget(btn_browse_succ_audio)
        layout.addLayout(row_succ_file)

        # 6. 成功执行命令
        self.chk_succ_cmd = QCheckBox("在 ping 成功时执行以下命令(上次失败后)：")
        self.chk_succ_cmd.setChecked(self.options.use_success_cmd)
        layout.addWidget(self.chk_succ_cmd)

        self.txt_succ_cmd = QLineEdit()
        self.txt_succ_cmd.setPlaceholderText("例如: notify-send '恢复通知' '主机 %HostName% 恢复正常连接'")
        self.txt_succ_cmd.setText(self.options.success_cmd)
        self.txt_succ_cmd.setEnabled(self.options.use_success_cmd)
        self.chk_succ_cmd.toggled.connect(self.txt_succ_cmd.setEnabled)
        layout.addWidget(self.txt_succ_cmd)

        # 7. 连续成功次数触发
        row_succ_cnt = QHBoxLayout()
        row_succ_cnt.addWidget(QLabel("连续成功 ping 触发成功声音警报的次数："))
        self.spin_succ_cnt = QSpinBox()
        self.spin_succ_cnt.setRange(1, 9999)
        self.spin_succ_cnt.setValue(self.options.consecutive_success_trigger)
        self.spin_succ_cnt.setFixedWidth(80)
        row_succ_cnt.addWidget(self.spin_succ_cnt)
        row_succ_cnt.addStretch()
        layout.addLayout(row_succ_cnt)

        # 8. 添加 Ping 结果到下列日志文件
        self.chk_log = QCheckBox("添加Ping结果到下列日志文件：")
        self.chk_log.setChecked(self.options.log_pings)
        layout.addWidget(self.chk_log)

        row_log_path = QHBoxLayout()
        self.txt_log_path = QLineEdit()
        self.txt_log_path.setPlaceholderText("日志文件存储路径 (如: /home/ping_log.csv)")
        self.txt_log_path.setText(self.options.log_filename)
        row_log_path.addWidget(self.txt_log_path, 1)
        btn_browse_log = QPushButton("...")
        btn_browse_log.setFixedWidth(36)
        btn_browse_log.clicked.connect(self._browse_log_file)
        row_log_path.addWidget(btn_browse_log)
        layout.addLayout(row_log_path)

        row_log_opts = QHBoxLayout()
        self.combo_log_type = QComboBox()
        for ft in ["逗号分隔的文本文件", "制表符分隔的文本文件", "HTML 文件"]:
            self.combo_log_type.addItem(ft)
        self.combo_log_type.setCurrentText(self.options.log_file_type)
        row_log_opts.addWidget(self.combo_log_type)

        self.combo_log_mode = QComboBox()
        for lm in ["记录所有 pings", "仅记录失败的 pings", "仅记录成功的 pings"]:
            self.combo_log_mode.addItem(lm)
        self.combo_log_mode.setCurrentText(self.options.log_pings_mode)
        row_log_opts.addWidget(self.combo_log_mode)
        row_log_opts.addStretch()
        layout.addLayout(row_log_opts)

        # 9. 下窗格模式
        row_lower = QHBoxLayout()
        row_lower.addWidget(QLabel("下窗格模式："))
        self.combo_lower_mode = QComboBox()
        for lm in [
            "添加所有 pings 到下窗格",
            "仅添加失败的 pings 到下窗格",
            "仅添加成功的 pings 到下窗格",
            "为 ping 状态的每个更改添加 ping 行",
            "不添加 pings 到下窗格"
        ]:
            self.combo_lower_mode.addItem(lm)
        self.combo_lower_mode.setCurrentText(self.options.lower_pane_mode)
        row_lower.addWidget(self.combo_lower_mode, 1)
        layout.addLayout(row_lower)

        # 10. 限制累积 ping 总数
        row_limit = QHBoxLayout()
        self.chk_limit_pings = QCheckBox("限制累积ping的总数：")
        self.chk_limit_pings.setChecked(self.options.limit_accumulated_pings)
        row_limit.addWidget(self.chk_limit_pings)

        self.spin_max_pings = QSpinBox()
        self.spin_max_pings.setRange(100, 1000000)
        self.spin_max_pings.setValue(self.options.max_accumulated_pings)
        self.spin_max_pings.setFixedWidth(100)
        self.spin_max_pings.setEnabled(self.options.limit_accumulated_pings)
        self.chk_limit_pings.toggled.connect(self.spin_max_pings.setEnabled)
        row_limit.addWidget(self.spin_max_pings)
        row_limit.addStretch()
        layout.addLayout(row_limit)

        # 11. 自动导出下窗格
        row_export = QHBoxLayout()
        self.chk_auto_export = QCheckBox("自动导出下窗格的所有项目到文件每...")
        self.chk_auto_export.setChecked(self.options.auto_export)
        row_export.addWidget(self.chk_auto_export)

        self.spin_export_interval = QSpinBox()
        self.spin_export_interval.setRange(5, 86400)
        self.spin_export_interval.setValue(self.options.auto_export_interval)
        self.spin_export_interval.setFixedWidth(70)
        row_export.addWidget(self.spin_export_interval)
        row_export.addWidget(QLabel("秒"))
        row_export.addStretch()
        layout.addLayout(row_export)

        # 导出文件类型与文件名称
        grid_export = QGridLayout()
        grid_export.addWidget(QLabel("文件类型："), 0, 0)
        self.combo_export_type = QComboBox()
        for ft in ["逗号分隔的文本文件", "制表符分隔的文本文件", "HTML 文件"]:
            self.combo_export_type.addItem(ft)
        self.combo_export_type.setCurrentText(self.options.auto_export_file_type)
        grid_export.addWidget(self.combo_export_type, 0, 1)

        grid_export.addWidget(QLabel("文件名称："), 1, 0)
        row_exp_name = QHBoxLayout()
        self.txt_export_name = QLineEdit()
        self.txt_export_name.setText(self.options.auto_export_filename)
        row_exp_name.addWidget(self.txt_export_name, 1)
        btn_browse_export = QPushButton("...")
        btn_browse_export.setFixedWidth(36)
        btn_browse_export.clicked.connect(self._browse_export_file)
        row_exp_name.addWidget(btn_browse_export)
        grid_export.addLayout(row_exp_name, 1, 1)
        layout.addLayout(grid_export)

        self.chk_export_change = QCheckBox("仅比之前导出的文件有变化时导出的文件")
        self.chk_export_change.setChecked(self.options.auto_export_only_on_change)
        layout.addWidget(self.chk_export_change)

        row_exp_modes = QHBoxLayout()
        self.combo_exp_overwrite = QComboBox()
        self.combo_exp_overwrite.addItem("总是覆盖以前的文件")
        self.combo_exp_overwrite.addItem("追加到现有文件")
        self.combo_exp_overwrite.setCurrentText(self.options.auto_export_overwrite_mode)
        row_exp_modes.addWidget(self.combo_exp_overwrite)

        self.combo_exp_counter = QComboBox()
        self.combo_exp_counter.addItem("创建带数字计数器的文件名")
        self.combo_exp_counter.addItem("使用固定文件名")
        self.combo_exp_counter.setCurrentText(self.options.auto_export_counter_mode)
        row_exp_modes.addWidget(self.combo_exp_counter)
        layout.addLayout(row_exp_modes)

        # 12. 底部操作按钮 [确定] [取消]
        layout.addSpacing(10)
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()

        btn_ok = QPushButton("确定")
        btn_ok.setStyleSheet("background-color: #2563eb; color: white; padding: 6px 20px; font-weight: bold; border-radius: 4px;")
        btn_ok.clicked.connect(self.on_save)
        btn_bar.addWidget(btn_ok)

        btn_cancel = QPushButton("取消")
        btn_cancel.setStyleSheet("padding: 6px 18px;")
        btn_cancel.clicked.connect(self.reject)
        btn_bar.addWidget(btn_cancel)

        layout.addLayout(btn_bar)

    def _browse_audio(self, line_edit: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", "", "音频文件 (*.wav *.mp3 *.ogg *.aac);;所有文件 (*)"
        )
        if path:
            line_edit.setText(path)

    def _browse_log_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "选择或创建日志文件", "", "CSV 文件 (*.csv);;文本文件 (*.txt);;所有文件 (*)"
        )
        if path:
            self.txt_log_path.setText(path)

    def _browse_export_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "选择自动导出文件路径", "", "文本文件 (*.txt *.csv *.html);;所有文件 (*)"
        )
        if path:
            self.txt_export_name.setText(path)

    def on_save(self):
        """保存所有参数到 options 实体并关闭"""
        self.options.max_concurrent_pings = self.spin_concur.value()
        self.options.max_threads = self.spin_concur.value()

        # 失败
        self.options.failed_sound_type = self.combo_fail_sound.currentText()
        self.options.failed_audio_path = self.txt_fail_audio.text().strip()
        self.options.use_failed_cmd = self.chk_fail_cmd.isChecked()
        self.options.failed_cmd = self.txt_fail_cmd.text().strip()
        self.options.consecutive_failed_trigger = self.spin_fail_cnt.value()

        # 成功
        self.options.success_sound_type = self.combo_succ_sound.currentText()
        self.options.success_audio_path = self.txt_succ_audio.text().strip()
        self.options.use_success_cmd = self.chk_succ_cmd.isChecked()
        self.options.success_cmd = self.txt_succ_cmd.text().strip()
        self.options.consecutive_success_trigger = self.spin_succ_cnt.value()

        # 日志
        self.options.log_pings = self.chk_log.isChecked()
        self.options.log_filename = self.txt_log_path.text().strip()
        self.options.log_file_type = self.combo_log_type.currentText()
        self.options.log_pings_mode = self.combo_log_mode.currentText()

        # 下窗格
        self.options.lower_pane_mode = self.combo_lower_mode.currentText()
        self.options.limit_accumulated_pings = self.chk_limit_pings.isChecked()
        self.options.max_accumulated_pings = self.spin_max_pings.value()

        # 自动导出
        self.options.auto_export = self.chk_auto_export.isChecked()
        self.options.auto_export_interval = self.spin_export_interval.value()
        self.options.auto_export_file_type = self.combo_export_type.currentText()
        self.options.auto_export_filename = self.txt_export_name.text().strip()
        self.options.auto_export_only_on_change = self.chk_export_change.isChecked()
        self.options.auto_export_overwrite_mode = self.combo_exp_overwrite.currentText()
        self.options.auto_export_counter_mode = self.combo_exp_counter.currentText()

        self.accept()
