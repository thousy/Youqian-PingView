"""
动态图标生成模块：使用 QPainter 自绘轻量矢量状态灯与操作图标
"""

try:
    from youqian_pingview.qt_compat import (
        QIcon, QPixmap, QPainter, QColor, QBrush, QPen, QPolygonF,
        Qt, QPointF, QRectF, QFont
    )
except (ImportError, ModuleNotFoundError, ValueError):
    from qt_compat import (
        QIcon, QPixmap, QPainter, QColor, QBrush, QPen, QPolygonF,
        Qt, QPointF, QRectF, QFont
    )


def create_status_icon(color_hex: str, size: int = 16) -> QIcon:
    """绘制状态指示灯小圆点 (绿色正常/红色超时/灰色待命)"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # 绘制外边框光晕
    outer_color = QColor(color_hex)
    outer_color.setAlpha(60)
    painter.setBrush(QBrush(outer_color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(1, 1, size - 2, size - 2)

    # 绘制中心实心圆
    inner_color = QColor(color_hex)
    painter.setBrush(QBrush(inner_color))
    painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
    painter.drawEllipse(3, 3, size - 6, size - 6)

    painter.end()
    return QIcon(pixmap)


def create_action_icon(action_type: str, size: int = 24) -> QIcon:
    """绘制工具栏动作图标：start(播放), stop(暂停), add(加号), settings(齿轮), export(导出), clear(清空)"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    if action_type == "start":
        painter.setBrush(QBrush(QColor("#16a34a")))
        painter.setPen(Qt.NoPen)
        poly = QPolygonF([
            QPointF(6, 4),
            QPointF(size - 4, size / 2),
            QPointF(6, size - 4)
        ])
        painter.drawPolygon(poly)

    elif action_type == "stop":
        painter.setBrush(QBrush(QColor("#dc2626")))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(5, 5, size - 10, size - 10), 2, 2)

    elif action_type == "add":
        pen = QPen(QColor("#2563eb"), 3, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(size / 2), 5, int(size / 2), size - 5)
        painter.drawLine(5, int(size / 2), size - 5, int(size / 2))

    elif action_type == "clear":
        pen = QPen(QColor("#64748b"), 2, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(QRectF(4, 4, size - 8, size - 8), 45 * 16, 270 * 16)
        painter.drawLine(size - 6, int(size / 2) - 4, size - 3, int(size / 2) + 2)

    elif action_type == "settings":
        painter.setBrush(QBrush(QColor("#475569")))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(7, 7, size - 14, size - 14))
        pen = QPen(QColor("#475569"), 2)
        painter.setPen(pen)
        painter.drawEllipse(QRectF(4, 4, size - 8, size - 8))

    elif action_type == "export":
        pen = QPen(QColor("#0891b2"), 2, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(size / 2), 4, int(size / 2), size - 8)
        painter.drawLine(int(size / 2) - 4, 8, int(size / 2), 4)
        painter.drawLine(int(size / 2) + 4, 8, int(size / 2), 4)
        painter.drawLine(4, size - 5, size - 4, size - 5)

    elif action_type == "columns":
        # 绘制“选择列”图标：多列表格布局图标
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.setPen(QPen(QColor("#475569"), 1.6))
        painter.drawRoundedRect(QRectF(3, 3, size - 6, size - 6), 2, 2)
        painter.drawLine(3, 8, size - 3, 8)
        col_w = (size - 6) / 3
        painter.drawLine(int(3 + col_w), 3, int(3 + col_w), size - 3)
        painter.drawLine(int(3 + col_w * 2), 3, int(3 + col_w * 2), size - 3)

    elif action_type == "sort_az":
        # 绘制“AZ 排序”图标：字母 A 和 Z 配以排序箭头
        painter.setPen(QPen(QColor("#2563eb"), 1))
        bold_weight = getattr(getattr(QFont, "Weight", QFont), "Bold", 75)
        font = QFont("Arial", 8, bold_weight)
        painter.setFont(font)
        painter.drawText(QRectF(1, 1, 13, 11), Qt.AlignCenter, "A")
        painter.drawText(QRectF(1, 12, 13, 11), Qt.AlignCenter, "Z")
        pen_arrow = QPen(QColor("#2563eb"), 1.8, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_arrow)
        painter.drawLine(17, 5, 17, size - 5)
        painter.drawLine(14, size - 8, 17, size - 5)
        painter.drawLine(20, size - 8, 17, size - 5)

    painter.end()
    return QIcon(pixmap)


class AppIcons:
    _instance = None

    def __init__(self):
        self.green_light = create_status_icon("#22c55e")
        self.red_light = create_status_icon("#ef4444")
        self.gray_light = create_status_icon("#94a3b8")
        self.yellow_light = create_status_icon("#eab308")

        self.start = create_action_icon("start")
        self.stop = create_action_icon("stop")
        self.add = create_action_icon("add")
        self.clear = create_action_icon("clear")
        self.settings = create_action_icon("settings")
        self.export = create_action_icon("export")
        self.columns = create_action_icon("columns")
        self.sort_az = create_action_icon("sort_az")

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
