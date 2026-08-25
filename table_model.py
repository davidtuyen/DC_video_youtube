# table_model.py - Table column constants and delegates extracted from ui_script.py
from PyQt5.QtWidgets import (
    QApplication, QStyledItemDelegate, QStyle, QStyleOptionViewItem,
    QStyleOptionProgressBar, QStyleOptionButton,
)
from PyQt5.QtCore import Qt, QModelIndex, QRect, QSize
from PyQt5.QtGui import QPainter, QColor, QFont, QFontMetrics, QIcon, QPixmap

# Theme will be set by ui_script after import
APP_THEME = {}

def init_table_config(theme):
    global APP_THEME
    APP_THEME = theme

# --- Định nghĩa các cột cho TableView Model ---
# Thứ tự phải khớp với setHorizontalHeaderLabels
COL_CHECKBOX = 0                # << MỚI
COL_THUMBNAIL = 1
COL_TITLE = 2
COL_DURATION = 3
COL_PROXY_STATUS = 4  # [UI-UPDATE]
COL_RESOLUTION = 5
COL_STATUS_TEXT = 6
COL_VERIFICATION_STATUS = 7
COL_PROGRESS = 8
COL_SPEED_ETA = 9
# Các cột ẩn (thứ tự các cột này không ảnh hưởng đến hiển thị)
COL_URL = 10
COL_TASK_ID = 11
COL_QUALITY_REQUESTED = 12
COL_FILE_PATH = 13
COL_ERROR_DETAILS = 14
COL_TIMESTAMP = 15
COL_ENTITY_ID = 16
# Cột ẩn mới để lưu độ dài gốc (dạng chuỗi HH:MM:SS)
COL_EXPECTED_DURATION = 17
TOTAL_COLUMNS = 18

class ProgressBarDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        if index.column() == COL_PROGRESS:
            progress = index.data(Qt.DisplayRole)
            if progress is None: progress = 0
            try: progress_int = int(float(progress)) # Cho phép progress là float từ model
            except ValueError: progress_int = 0
            opt = QStyleOptionProgressBar()
            opt.rect = option.rect; opt.minimum = 0; opt.maximum = 100
            opt.progress = progress_int; opt.text = f"{progress_int}%"
            opt.textVisible = True; opt.textAlignment = Qt.AlignCenter
            if option.state & QStyle.State_Selected: painter.fillRect(option.rect, option.palette.highlight())
            QApplication.style().drawControl(QStyle.CE_ProgressBar, opt, painter)
        else: super().paint(painter, option, index)


class DownloadItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.default_font_size = QApplication.font().pointSize()
        self.title_font = QFont()
        self.title_font.setBold(True)
        self.title_font.setPointSize(self.default_font_size -1 if self.default_font_size > 9 else 9)
        self.details_font = QFont()
        self.details_font.setPointSize(self.default_font_size - 2 if self.default_font_size > 8 else 8)
        self.thumbnail_target_height = 54
        self.thumbnail_target_width = 96
        self.padding = 3
        self.text_padding_top = 2
        self.line_spacing = 2

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        # --- Vẽ nền trước (giữ nguyên) ---
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        elif option.state & QStyle.State_MouseOver and index.flags() & Qt.ItemIsEnabled:
            painter.fillRect(option.rect, option.palette.light())

        # --- Xử lý vẽ nội dung cho từng cột ---
        model = index.model()
        
        # << BỔ SUNG KHỐI ELSE ĐỂ VẼ CÁC CỘT CÒN LẠI >>
        if index.column() in [COL_TITLE, COL_DURATION, COL_PROXY_STATUS, COL_RESOLUTION, COL_STATUS_TEXT, 
                              COL_VERIFICATION_STATUS, COL_SPEED_ETA, COL_THUMBNAIL]:
            
            # --- Code vẽ tùy chỉnh cho các cột cụ thể (giữ nguyên logic cũ) ---
            current_row = index.row()
            icon_data = model.data(model.index(current_row, COL_THUMBNAIL), Qt.DecorationRole)
            title = model.data(model.index(current_row, COL_TITLE), Qt.DisplayRole) or "..."
            duration = model.data(model.index(current_row, COL_DURATION), Qt.DisplayRole) or "--:--"
            proxy_status = model.data(model.index(current_row, COL_PROXY_STATUS), Qt.DisplayRole) or "N/A"
            resolution = model.data(model.index(current_row, COL_RESOLUTION), Qt.DisplayRole) or ""
            status_text = model.data(model.index(current_row, COL_STATUS_TEXT), Qt.DisplayRole) or "..."
            verification_text = model.data(model.index(current_row, COL_VERIFICATION_STATUS), Qt.DisplayRole) or "-"

            if index.column() == COL_THUMBNAIL:
                thumb_cell_rect = option.rect
                thumb_draw_rect = QRect(
                    thumb_cell_rect.left() + (thumb_cell_rect.width() - self.thumbnail_target_width) // 2,
                    thumb_cell_rect.top() + (thumb_cell_rect.height() - self.thumbnail_target_height) // 2,
                    self.thumbnail_target_width, self.thumbnail_target_height
                )
                pixmap_to_draw = None
                if isinstance(icon_data, QIcon) and not icon_data.isNull():
                    pixmap_to_draw = icon_data.pixmap(self.thumbnail_target_width, self.thumbnail_target_height, QIcon.Normal, QIcon.On)
                elif isinstance(icon_data, QPixmap) and not icon_data.isNull():
                    pixmap_to_draw = icon_data
                if pixmap_to_draw:
                    painter.drawPixmap(thumb_draw_rect.topLeft(), pixmap_to_draw)
                else:
                    painter.setBrush(QColor(APP_THEME["thumb_bg"])); painter.setPen(Qt.NoPen)
                    painter.drawRect(thumb_draw_rect)
                    painter.setPen(QColor(APP_THEME["thumb_text"])); painter.drawText(thumb_draw_rect, Qt.AlignCenter, "No Img")

            text_color = option.palette.text().color() if not (option.state & QStyle.State_Selected) else option.palette.highlightedText().color()
            painter.setPen(text_color)
            text_rect = option.rect.adjusted(self.padding, self.padding, -self.padding, -self.padding)

            if index.column() == COL_TITLE:
                painter.setFont(self.title_font)
                fm_title = QFontMetrics(self.title_font)
                elided_title = fm_title.elidedText(title, Qt.ElideRight, text_rect.width())
                painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_title)
            elif index.column() == COL_DURATION:
                painter.setFont(self.details_font); painter.drawText(text_rect, Qt.AlignCenter | Qt.AlignVCenter, f"{duration}")  # [UI-UPDATE]
            elif index.column() == COL_PROXY_STATUS:
                painter.setFont(self.details_font)
                if not (option.state & QStyle.State_Selected):
                    status_str = str(proxy_status).lower()
                    if status_str.startswith("proxy") or status_str.startswith("có"):
                        painter.setPen(QColor(APP_THEME["status_success"]))
                    else:
                        painter.setPen(QColor(APP_THEME["status_neutral"]))
                painter.drawText(text_rect, Qt.AlignCenter | Qt.AlignVCenter, proxy_status)
                painter.setPen(text_color)
            elif index.column() == COL_RESOLUTION:
                painter.setFont(self.details_font); painter.drawText(text_rect, Qt.AlignCenter | Qt.AlignVCenter, resolution)  # [UI-UPDATE]
            elif index.column() == COL_STATUS_TEXT:
                painter.setFont(self.details_font); icon_to_draw = None
                success_keywords = ["Hoàn thành"]; error_keywords = ["Lỗi", "Thất bại", "failed", "Đã hủy"]
                if any(s_word in status_text for s_word in success_keywords):
                    icon_to_draw = self.parent().style().standardIcon(QStyle.SP_DialogApplyButton)
                elif any(e_word in status_text for e_word in error_keywords):
                    icon_to_draw = self.parent().style().standardIcon(QStyle.SP_MessageBoxCritical)
                if icon_to_draw:
                    icon_size = 16
                    icon_x = option.rect.left() + (option.rect.width() - icon_size) // 2
                    icon_y = option.rect.top() + (option.rect.height() - icon_size) // 2
                    icon_to_draw.paint(painter, QRect(icon_x, icon_y, icon_size, icon_size))
                else:
                    painter.drawText(text_rect, Qt.AlignCenter | Qt.AlignVCenter, status_text)  # [UI-UPDATE]
            elif index.column() == COL_VERIFICATION_STATUS:
                painter.setFont(self.details_font); painter.drawText(text_rect, Qt.AlignCenter | Qt.AlignVCenter, verification_text)  # [UI-UPDATE]
            elif index.column() == COL_SPEED_ETA:
                painter.setFont(self.details_font)
                speed_eta_text = model.data(model.index(current_row, COL_SPEED_ETA), Qt.DisplayRole) or "-"
                painter.drawText(text_rect, Qt.AlignCenter | Qt.AlignVCenter, speed_eta_text)  # [UI-UPDATE]
        
        elif index.column() == COL_CHECKBOX:
            check_state = index.data(Qt.CheckStateRole)
            check_box_option = QStyleOptionButton()

            # Lấy kích thước gốc của checkbox từ style hệ thống
            indicator_size = QApplication.style().pixelMetric(QStyle.PM_IndicatorWidth)
            
            # Đặt kích thước mới lớn gấp đôi
            new_size = indicator_size * 2
            
            # Tính toán vị trí để căn giữa checkbox trong ô
            cell_rect = option.rect
            x = cell_rect.left() + (cell_rect.width() - new_size) // 2
            y = cell_rect.top() + (cell_rect.height() - new_size) // 2
            
            check_box_option.rect = QRect(x, y, new_size, new_size)
            check_box_option.state = QStyle.State_Enabled
            
            if check_state == Qt.Checked:
                check_box_option.state |= QStyle.State_On
            else:
                check_box_option.state |= QStyle.State_Off
            
            # Yêu cầu hệ thống vẽ checkbox với các tùy chọn đã tùy chỉnh
            QApplication.style().drawControl(QStyle.CE_CheckBox, check_box_option, painter)
        
        else:
            # Cho tất cả các cột khác còn lại, sử dụng cách vẽ mặc định.
            super().paint(painter, option, index)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), self.thumbnail_target_height + 2 * self.padding)
# Thêm các import cần thiết ở đầu file ui_script.py nếu chưa có:
# from PyQt5.QtWidgets import QDialog, QFormLayout, QSpinBox, QLineEdit, QDialogButtonBox
# (QCheckBox, QLabel đã có)

