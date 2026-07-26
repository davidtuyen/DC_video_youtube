# scripts/updater_gui.py

import sys
import os
import time
import subprocess
from pathlib import Path

from update_manager import UpdateMutex, UpdatePackageApplier

from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QProgressBar, QMessageBox
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont

class UpdateWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        zip_path: Path,
        install_dir: Path,
        main_exe_name: str,
        runtime_package: Path | None = None,
    ):
        super().__init__()
        self.zip_path = zip_path
        self.install_dir = install_dir
        self.main_exe_name = main_exe_name
        self.runtime_package = runtime_package
        
        # Xác định tên file của chính updater để tránh tự ghi đè lên mình khi đang chạy
        if getattr(sys, "frozen", False):
            self.updater_exe_name = os.path.basename(sys.executable)
        else:
            self.updater_exe_name = "Updater.exe"

    def run(self):
        try:
            self.status.emit("Đang chờ ứng dụng chính thoát...")
            self._wait_for_main_exit()
            self.status.emit("Đang xác minh và áp dụng bản cập nhật...")
            self._extract_update()
            self.status.emit("Đã xác minh xong, đang khởi động lại...")
            self._restart_main_app()
        except Exception as exc:
            self.error.emit(str(exc))
            return
        self.finished.emit()

    def _wait_for_main_exit(self):
        """Kiểm tra và chờ App chính tắt hẳn."""
        main_exe_path = self.install_dir / self.main_exe_name
        
        # Nếu file không tồn tại (lần đầu cài hoặc bị xóa), không cần chờ
        if not main_exe_path.exists():
            time.sleep(1)
            return

        # Thử đổi tên file tạm thời để check lock (Windows File Lock)
        lock_probe = main_exe_path.with_suffix(main_exe_path.suffix + ".lockcheck")
        
        # Thử trong 15 lần (khoảng 3-5 giây)
        for _ in range(15):
            try:
                os.rename(main_exe_path, lock_probe)
                os.rename(lock_probe, main_exe_path)
                return # File không bị lock -> App đã tắt
            except OSError:
                time.sleep(0.3)

        raise RuntimeError(f"Ứng dụng '{self.main_exe_name}' vẫn đang chạy. Vui lòng tắt hẳn ứng dụng và thử lại.")

    def _extract_update(self):
        """Validate, install, verify, and roll back the update as one transaction."""
        if not self.zip_path.exists():
            raise RuntimeError(f"Không tìm thấy file cập nhật: {self.zip_path}")

        preserve_paths = {
            "data/downloader_settings.json",
            "data/downloader_settings_qt.json",
            "data/download_history.json",
            "data/token.json",
            "data/token_drive.json",
            "data/credentials.json",
            "data/proxy_settings.json",
            "data/cookies.txt",
            "cookies.txt",
            "youtube_cookies.txt",
            self.updater_exe_name,
        }
        applier = UpdatePackageApplier(
            install_dir=self.install_dir,
            preserve_relative_paths=preserve_paths,
            progress_callback=self.progress.emit,
        )
        with UpdateMutex(self.install_dir):
            result = applier.apply(self.zip_path, runtime_package=self.runtime_package)
        if not result.success:
            raise RuntimeError(f"{result.message}: {result.error}")

        try:
            self.zip_path.unlink()
        except OSError:
            pass
        if self.runtime_package is not None:
            try:
                self.runtime_package.unlink()
            except OSError:
                pass

    def _restart_main_app(self):
        main_exe_path = self.install_dir / self.main_exe_name
        if not main_exe_path.exists():
            raise RuntimeError(f"Không tìm thấy file chính để khởi động: {main_exe_path}")

        print(f"Khởi động lại: {main_exe_path}")
        if sys.platform == "win32":
            os.startfile(str(main_exe_path))
        else:
            subprocess.Popen(
                [str(main_exe_path)],
                cwd=str(self.install_dir),
                close_fds=True,
                start_new_session=True,
            )
        time.sleep(1)


class UpdaterWindow(QWidget):
    def __init__(
        self,
        zip_path: Path,
        install_dir: Path,
        main_exe_name: str,
        runtime_package: Path | None = None,
    ):
        super().__init__()
        self.zip_path = zip_path
        self.install_dir = install_dir
        self.main_exe_name = main_exe_name
        self.runtime_package = runtime_package
        self.worker = None

        # Giao diện không viền, luôn ở trên cùng
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(360, 140)
        
        # Style Dark Mode chuyên nghiệp
        self.setStyleSheet("""
            QWidget { 
                background-color: #1f1f23; 
                color: #f8fafc; 
                border: 1px solid #3b82f6; 
                border-radius: 12px; 
            }
            QProgressBar {
                background-color: #2b2b2f;
                color: #E2E8F0;
                border-radius: 8px;
                height: 18px;
                text-align: center;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #3B82F6;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        self.lbl_status = QLabel("Đang cập nhật phiên bản mới...")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.lbl_status.setStyleSheet("border: none; color: #E2E8F0;")
        layout.addWidget(self.lbl_status)

        self.pbar = QProgressBar()
        self.pbar.setRange(0, 100)
        self.pbar.setValue(0)
        self.pbar.setTextVisible(True)
        layout.addWidget(self.pbar)

    def start(self):
        self.worker = UpdateWorker(
            self.zip_path,
            self.install_dir,
            self.main_exe_name,
            self.runtime_package,
        )
        self.worker.progress.connect(self.pbar.setValue)
        self.worker.status.connect(self.lbl_status.setText)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_error(self, msg):
        QMessageBox.critical(self, "Lỗi Cập Nhật", msg)
        QApplication.exit(1)

    def on_finished(self):
        self.pbar.setValue(100)
        self.lbl_status.setText("Cập nhật xong! Đang khởi động lại...")
        # Đợi 1.5s để người dùng kịp đọc thông báo rồi tắt
        QTimer.singleShot(1500, lambda: QApplication.exit(0))


def _parse_args() -> tuple[Path, Path, str, Path | None]:
    # Arg 1: Đường dẫn file ZIP
    # Arg 2: Thư mục cài đặt (nơi chứa exe chính)
    # Arg 3: Tên file EXE chính
    
    if len(sys.argv) < 4:
        # Fallback cho chế độ debug (chạy thẳng bằng python)
        return (
            Path("app-update-v2.pkg").resolve(),
            Path(".").resolve(),
            "YouTube Downloader Pro.exe",
            None,
        )
        
    zip_path = Path(sys.argv[1]).expanduser().resolve()
    install_dir = Path(sys.argv[2]).expanduser().resolve()
    main_exe_name = str(sys.argv[3]).strip()
    
    runtime_package = Path(sys.argv[4]).expanduser().resolve() if len(sys.argv) >= 5 else None
    return zip_path, install_dir, main_exe_name, runtime_package


def main():
    app = QApplication(sys.argv)
    
    try:
        zip_path, install_dir, main_exe_name, runtime_package = _parse_args()
    except Exception as exc:
        QMessageBox.critical(None, "Lỗi Tham Số", str(exc))
        return 1

    win = UpdaterWindow(zip_path, install_dir, main_exe_name, runtime_package)
    
    # Căn giữa màn hình
    screen = app.primaryScreen()
    if screen:
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - win.width()) // 2
        y = geo.y() + (geo.height() - win.height()) // 2
        win.move(x, y)
        
    win.show()
    # Chạy sau 100ms để UI kịp render
    QTimer.singleShot(100, win.start)

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
