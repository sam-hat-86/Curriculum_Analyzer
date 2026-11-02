"""
Material Design Icons (MDI) 完全内蔵型ベクターアイコンエンジン
外部ダウンロード・画像ファイル配置不要で、Pure Python / QtSvg により高精細な QIcon を生成。
"""
from typing import Dict, Optional
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QByteArray, QSize, Qt

MDI_SVG_PATHS: Dict[str, str] = {
    # ナビゲーション
    "arrow_back": "M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z",
    "arrow_forward": "M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z",
    "refresh": "M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z",
    "home": "M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z",
    # 操作・タブ
    "view_list": "M4 14h4v-4H4v4zm0 5h4v-4H4v4zM4 9h4V5H4v4zm5 5h12v-4H9v4zm0 5h12v-4H9v4zM9 5v4h12V5H9z",
    "play_arrow": "M8 5v14l11-7z",
    "stop": "M6 6h12v12H6z",
    "table_chart": "M10 10.02h5V21h-5zM17 21h3c1.1 0 2-.9 2-2v-9h-5v11zm3-18H5c-1.1 0-2 .9-2 2v3h19V5c0-1.1-.9-2-2-2zM3 19c0 1.1.9 2 2 2h3V10H3v9z",
    "settings": "M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z",
    "delete": "M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z",
    "delete_sweep": "M15 16h4v2h-4zm0-8h7v2h-7zm0 4h6v2h-6zM3 18c0 1.1.9 2 2 2h6c1.1 0 2-.9 2-2V8H3v10zm2-8h6v8H5v-8zm5-6H6L5 5H2v2h12V5h-3z",
    "help_outline": "M11 18h2v-2h-2v2zm1-16C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-14c-2.21 0-4 1.79-4 4h2c0-1.1.9-2 2-2s2 .9 2 2c0 2-3 1.75-3 5h2c0-2.25 3-2.5 3-5 0-2.21-1.79-4-4-4z",
}

_ICON_CACHE: Dict[str, QIcon] = {}


def _render_pixmap_from_path(svg_path: str, color_hex: str, size: int) -> QPixmap:
    svg_data = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">
        <path fill="{color_hex}" d="{svg_path}"/>
    </svg>""".encode("utf-8")

    renderer = QSvgRenderer(QByteArray(svg_data))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return pixmap


def get_mdi_icon(name: str, color: str = "#FFFFFF", size: int = 24) -> QIcon:
    """
    指定された名称の Material Design Icon を QIcon として取得する。
    Normal 状態（color）と Disabled 状態（#7A7A7A）のピックスマップを自動生成・登録。
    """
    cache_key = f"{name}_{color}_{size}"
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]

    svg_path = MDI_SVG_PATHS.get(name)
    if not svg_path:
        # 見つからない場合は空のアイコンを返す
        return QIcon()

    icon = QIcon()

    # Normal 状態
    pixmap_normal = _render_pixmap_from_path(svg_path, color, size)
    icon.addPixmap(pixmap_normal, QIcon.Mode.Normal, QIcon.State.Off)

    # Disabled 状態 (自動でグレー化)
    pixmap_disabled = _render_pixmap_from_path(svg_path, "#7A7A7A", size)
    icon.addPixmap(pixmap_disabled, QIcon.Mode.Disabled, QIcon.State.Off)

    _ICON_CACHE[cache_key] = icon
    return icon

