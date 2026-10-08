"""App fonts (Noto Sans TC / SC first, then the Windows UI fonts).

The quest-style colour tokens that used to live here went with the old task
pages (2026-10-04); the new shell keeps its own in ``src/ui/shell/theme.py``.

Noto Sans replaced MiSans on 2026-10-05: at the window's small sizes MiSans
put some horizontal strokes (the middle of 完) between two pixel rows, so they
came out pale (Leo).  Both scripts ship, so Traditional and Simplified text
each get their own letterforms; the one matching the app language goes first.
"""

from __future__ import annotations

from pathlib import Path

# Preferred global UI font stack for Traditional Chinese (and everything that
# is not Simplified), best first. Qt and qfluentwidgets resolve unavailable
# families through the platform fallback chain.
APP_FONT_FAMILIES = (
    "Noto Sans TC",
    "Noto Sans SC",
    "Microsoft JhengHei UI",
    "Microsoft YaHei UI",
    "Segoe UI",
)
_SIMPLIFIED_FAMILIES = (
    "Noto Sans SC",
    "Noto Sans TC",
    "Microsoft YaHei UI",
    "Microsoft JhengHei UI",
    "Segoe UI",
)
_FONT_FILES = ("NotoSansTC-VF.ttf", "NotoSansSC-VF.ttf")
_SIMPLIFIED_LOCALES = frozenset({"zh_CN", "zh_SG"})


def _app_locale_name() -> str:
    """The language the app shows (its own setting, else the system's)."""
    try:
        from ok.ui.qt.common.config import Language, cfg
        from PySide6.QtCore import QLocale

        language = cfg.get(cfg.language)
        locale = QLocale.system() if language == Language.AUTO else language.value
        return locale.name()
    except Exception:
        return ""


def font_families(locale_name: str | None = None) -> tuple[str, ...]:
    """The font stack for ``locale_name`` (default: the app's language)."""
    name = _app_locale_name() if locale_name is None else locale_name
    return _SIMPLIFIED_FAMILIES if name in _SIMPLIFIED_LOCALES else APP_FONT_FAMILIES


def _install_framework_fonts(families_list: tuple[str, ...]) -> None:
    """Keep upstream QSS from overriding the application's UI font families."""
    from ok.ui.qt.common.style_sheet import StyleSheet
    from ok.ui.qt.start.LogWindow import LogWindow
    from ok.ui.qt.util import app as app_module

    if getattr(StyleSheet, "_bd2_fonts_installed", False):
        return
    original_content = StyleSheet.content
    original_log_theme = LogWindow._apply_theme
    original_init = app_module.init_app_config
    families = ", ".join(f"'{family}'" for family in families_list)

    def content(self, *args, **kwargs):
        qss = original_content(self, *args, **kwargs)
        qss = qss.replace("'Segoe UI', 'Microsoft YaHei', 'PingFang SC'", families)
        qss = qss.replace(
            '"Segoe UI SemiBold", "Microsoft YaHei", \'PingFang SC\'',
            families + "; font-weight: 600",
        )
        return qss.replace("'Microsoft YaHei Light'", families + "; font-weight: 300")

    def log_theme(self):
        original_log_theme(self)
        self.status_label.setStyleSheet(f"font-family: {families};")

    def init_app_config():
        result = original_init()
        apply_app_font()
        return result

    StyleSheet.content = content
    LogWindow._apply_theme = log_theme
    app_module.init_app_config = init_app_config
    StyleSheet._bd2_fonts_installed = True


def apply_app_font() -> None:
    """Apply the project font stack before qfluentwidgets builds controls."""
    # Importing the app config first ensures its ui_config.json load cannot
    # overwrite the project stack after this call.
    from ok.ui.qt.common.config import cfg as _cfg  # noqa: F401
    from PySide6.QtWidgets import QApplication
    from qfluentwidgets import setFontFamilies

    families = list(font_families())
    setFontFamilies(families, save=False)
    _install_framework_fonts(tuple(families))

    app = QApplication.instance()
    if app is None:
        return
    if not app.property("bd2_bundled_font_loaded"):
        from PySide6.QtGui import QFontDatabase

        folder = Path(__file__).resolve().parents[2] / "assets/fonts"
        font_ids = [QFontDatabase.addApplicationFont(str(folder / name)) for name in _FONT_FILES]
        app.setProperty("bd2_bundled_font_loaded", all(font_id >= 0 for font_id in font_ids))
    font = app.font()
    font.setFamilies(families)
    app.setFont(font)
