import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt5.QtCore import QObject, QThread, pyqtSignal as Signal
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QApplication, QMessageBox

from thread_lifecycle import ManagedThreadRegistry
from ui_script import MainWindow
from workers import ThumbnailFetcher, UpdateCheckerWorker, VerificationWorker


class _CompletingWorker(QObject):
    completed = Signal()

    def __init__(self):
        super().__init__()
        self.was_stopped = False

    def run(self):
        self.completed.emit()

    def stop(self):
        self.was_stopped = True


class ThreadLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.owner = QObject()
        self.registry = ManagedThreadRegistry(self.owner)

    def tearDown(self):
        self.registry.request_shutdown()
        for thread in self.registry.running_threads():
            thread.wait(2_000)
        self.app.processEvents()

    def test_worker_completion_quits_and_unregisters_thread(self):
        thread = QThread(self.owner)
        worker = _CompletingWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        finished_spy = QSignalSpy(thread.finished)

        self.registry.track(
            thread,
            worker,
            completion_signals=(worker.completed,),
        )
        thread.start()

        self.assertTrue(finished_spy.wait(2_000))
        self.assertFalse(thread.isRunning())
        self.app.processEvents()
        self.assertEqual(self.registry.running_threads(), [])

    def test_shutdown_calls_worker_stop_and_quits_thread(self):
        thread = QThread(self.owner)
        worker = _CompletingWorker()
        worker.moveToThread(thread)
        started_spy = QSignalSpy(thread.started)
        finished_spy = QSignalSpy(thread.finished)
        self.registry.track(thread, worker)
        thread.start()
        self.assertTrue(started_spy.wait(2_000))

        self.registry.request_shutdown()

        self.assertTrue(worker.was_stopped)
        self.assertTrue(finished_spy.wait(2_000))
        self.assertFalse(thread.isRunning())

    def test_thumbnail_emits_lifecycle_signal_when_cancelled(self):
        worker = ThumbnailFetcher("thumbnail-test", "https://example.invalid/thumbnail.jpg")
        lifecycle_spy = QSignalSpy(worker.lifecycle_finished)

        worker.stop()
        worker.fetch()

        self.assertEqual(len(lifecycle_spy), 1)

    def test_verification_emits_lifecycle_signal_when_cancelled(self):
        worker = VerificationWorker("missing-file.mp4", None)
        lifecycle_spy = QSignalSpy(worker.lifecycle_finished)

        worker.stop()
        worker.run()

        self.assertEqual(len(lifecycle_spy), 1)

    def test_update_checker_supports_cooperative_stop(self):
        worker = UpdateCheckerWorker(mode="check")

        worker.stop()

        self.assertTrue(worker.stop_requested)


class MainWindowThreadLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _create_window(self):
        with patch("ui_script.main_logic.load_settings_from_file", return_value={}):
            with patch.object(MainWindow, "_load_download_history"):
                with patch.object(MainWindow, "_initialize_proxy_manager"):
                    with patch.object(MainWindow, "_initialize_yt_dlp_non_blocking"):
                        window = MainWindow()
        window.proxy_manager = None
        return window

    def test_history_thumbnail_finishes_its_thread(self):
        window = self._create_window()
        try:
            with patch.object(ThumbnailFetcher, "_fetch", new=lambda _worker: None):
                window._request_thumbnail_for_history_item(
                    "history-thumbnail",
                    "https://www.youtube.com/watch?v=example",
                )
                thread = window.active_thumbnail_fetchers["history-thumbnail"]["thread"]
                finished_spy = QSignalSpy(thread.finished)

                self.assertTrue(finished_spy.wait(2_000))
                self.app.processEvents()
                self.assertNotIn("history-thumbnail", window.active_thumbnail_fetchers)
        finally:
            window._request_thread_shutdown()
            window.deleteLater()
            self.app.processEvents()

    def test_close_waits_for_running_download_worker(self):
        window = self._create_window()
        window._save_download_history = Mock()
        worker = _CompletingWorker()
        thread = QThread(window)
        worker.moveToThread(thread)
        window._track_thread(thread, worker)
        window.active_threads["download-test"] = {
            "thread": thread,
            "worker": worker,
            "status": "downloading",
        }
        started_spy = QSignalSpy(thread.started)
        finished_spy = QSignalSpy(thread.finished)
        thread.start()
        self.assertTrue(started_spy.wait(2_000))

        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as question:
            with patch("ui_script.main_logic.save_settings_to_file") as save_settings:
                window.close()
                self.assertTrue(window._shutdown_in_progress)
                self.assertTrue(worker.was_stopped)
                self.assertTrue(finished_spy.wait(2_000))
                QTest.qWait(150)
                self.app.processEvents()

        question.assert_called_once()
        window._save_download_history.assert_called_once()
        save_settings.assert_called_once()
        self.assertTrue(window._allow_final_close)
        self.assertEqual(window._thread_registry.running_threads(), [])

    def test_close_adopts_and_waits_for_unregistered_child_thread(self):
        window = self._create_window()
        window._save_download_history = Mock()
        child_thread = QThread(window)
        started_spy = QSignalSpy(child_thread.started)
        finished_spy = QSignalSpy(child_thread.finished)
        child_thread.start()
        self.assertTrue(started_spy.wait(2_000))

        with patch("ui_script.main_logic.save_settings_to_file"):
            window.close()
            self.assertTrue(finished_spy.wait(2_000))
            QTest.qWait(150)
            self.app.processEvents()

        self.assertTrue(window._allow_final_close)
        self.assertEqual(window._thread_registry.running_threads(), [])


if __name__ == "__main__":
    unittest.main()
