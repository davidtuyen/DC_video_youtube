import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtWidgets import QApplication, QPushButton, QWidget

from ui_script import MainWindow


class ErrorDialogTimerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_closing_dialog_after_copy_does_not_touch_deleted_button(self):
        host = QWidget()
        callback_errors = []
        original_excepthook = sys.excepthook

        def capture_exception(error_type, error, traceback):
            callback_errors.append((error_type, error, traceback))

        def copy_and_close_dialog():
            dialog = QApplication.activeModalWidget()
            self.assertIsNotNone(dialog)
            copy_button = next(
                button
                for button in dialog.findChildren(QPushButton)
                if "Sao ch" in button.text()
            )
            copy_button.click()
            dialog.accept()

        try:
            sys.excepthook = capture_exception
            QTimer.singleShot(0, copy_and_close_dialog)
            MainWindow._show_error_detail_dialog(host, "task-test", "download failed")

            wait_loop = QEventLoop()
            QTimer.singleShot(2100, wait_loop.quit)
            wait_loop.exec_()
        finally:
            sys.excepthook = original_excepthook
            host.deleteLater()
            self.app.processEvents()

        self.assertEqual(callback_errors, [])


if __name__ == "__main__":
    unittest.main()
