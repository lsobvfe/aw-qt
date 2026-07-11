from PyQt6.QtCore import QObject, QCoreApplication, pyqtSignal

from aw_qt.command_os.controller import TimerController


class FakeClient(QObject):
    completed = pyqtSignal(str, dict)
    failed = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.request_count = 0

    def execute(self, _command: str, _args: dict) -> str:
        self.request_count += 1
        return f"request-{self.request_count}"


def test_failed_refresh_clears_pending_request() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    client = FakeClient()
    controller = TimerController(client)

    controller.refresh()
    client.failed.emit("request-1", "Desktop authorization is required")
    app.processEvents()
    controller.refresh()

    assert controller._pending == {"request-2": "refresh"}
