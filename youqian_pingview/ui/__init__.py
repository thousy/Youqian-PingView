"""
UI 模块安全导出
"""
try:
    from youqian_pingview.qt_compat import QT_BINDING
except (ImportError, ModuleNotFoundError, ValueError):
    try:
        from qt_compat import QT_BINDING
    except Exception:
        QT_BINDING = None

if QT_BINDING:
    try:
        try:
            from youqian_pingview.ui.main_window import MainWindow
            from youqian_pingview.ui.options_dialog import OptionsDialog
            from youqian_pingview.ui.target_dialog import TargetDialog
            from youqian_pingview.ui.properties_dialog import PropertiesDialog
        except (ImportError, ModuleNotFoundError, ValueError):
            from .main_window import MainWindow
            from .options_dialog import OptionsDialog
            from .target_dialog import TargetDialog
            from .properties_dialog import PropertiesDialog
        __all__ = ["MainWindow", "OptionsDialog", "TargetDialog", "PropertiesDialog"]
    except Exception:
        MainWindow = OptionsDialog = TargetDialog = PropertiesDialog = None
        __all__ = []
else:
    MainWindow = OptionsDialog = TargetDialog = PropertiesDialog = None
    __all__ = []
