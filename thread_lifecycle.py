"""Helpers for safely owning QObject workers that run in QThreads."""

from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSlot


@dataclass
class _ThreadEntry:
    thread: QThread
    worker: Optional[QObject]
    stop_callback: Optional[Callable[[], None]]
    cleanup_callback: Optional[Callable[[], None]]


class ManagedThreadRegistry(QObject):
    """Keep threads alive until they really finish and coordinate shutdown."""

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._entries: dict[int, _ThreadEntry] = {}

    def track(
        self,
        thread: QThread,
        worker: Optional[QObject] = None,
        *,
        completion_signals: Iterable[object] = (),
        stop_callback: Optional[Callable[[], None]] = None,
        cleanup_callback: Optional[Callable[[], None]] = None,
    ) -> QThread:
        key = id(thread)
        if key in self._entries:
            raise ValueError("QThread is already managed")

        if stop_callback is None and worker is not None:
            candidate = getattr(worker, "stop", None)
            if callable(candidate):
                stop_callback = candidate

        self._entries[key] = _ThreadEntry(
            thread=thread,
            worker=worker,
            stop_callback=stop_callback,
            cleanup_callback=cleanup_callback,
        )

        for signal in completion_signals:
            signal.connect(thread.quit)

        thread.finished.connect(self._on_thread_finished)
        return thread

    @pyqtSlot()
    def _on_thread_finished(self) -> None:
        thread = self.sender()
        if thread is not None:
            self._forget(id(thread))

    def _forget(self, key: int) -> None:
        entry = self._entries.pop(key, None)
        if entry is None:
            return

        if entry.cleanup_callback is not None:
            entry.cleanup_callback()

        if entry.worker is not None and entry.worker is not entry.thread:
            entry.worker.deleteLater()
        entry.thread.deleteLater()

    def running_threads(self) -> list[QThread]:
        return [
            entry.thread
            for entry in self._entries.values()
            if entry.thread.isRunning()
        ]

    def is_tracked(self, thread: QThread) -> bool:
        return id(thread) in self._entries

    def request_shutdown(self) -> None:
        for entry in list(self._entries.values()):
            if entry.stop_callback is not None:
                try:
                    entry.stop_callback()
                except Exception as exc:
                    print(f"Không thể yêu cầu worker dừng: {exc}")

            if entry.thread.isRunning():
                entry.thread.requestInterruption()
                entry.thread.quit()
