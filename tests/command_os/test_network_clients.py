import gc
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer

from aw_qt.command_os.client import CommandClient
from aw_qt.command_os.session_client import SessionClient


class CommandHandler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(content_length)
        data = (
            {"snapshot": "ready"}
            if self.path == "/api/v1/commands/execute"
            else {"access_token": "access", "refresh_token": "refresh"}
        )
        body = json.dumps({"status": "success", "data": data}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), CommandHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _wait(loop: QEventLoop) -> None:
    QTimer.singleShot(3_000, loop.quit)
    loop.exec()


def test_command_client_reply_survives_python_garbage_collection() -> None:
    QCoreApplication.instance() or QCoreApplication([])
    server = _server()
    try:
        client = CommandClient(
            f"http://127.0.0.1:{server.server_port}",
            lambda: "desktop-access-token",
        )
        completed = []
        failed = []
        loop = QEventLoop()
        client.completed.connect(
            lambda request_id, data: (completed.append((request_id, data)), loop.quit())
        )
        client.failed.connect(
            lambda request_id, message: (failed.append((request_id, message)), loop.quit())
        )

        request_id = client.execute("sp.time_log.desktop.snapshot", {})
        gc.collect()
        _wait(loop)

        assert failed == []
        assert completed == [(request_id, {"snapshot": "ready"})]
    finally:
        server.shutdown()
        server.server_close()


def test_session_client_reply_survives_python_garbage_collection() -> None:
    QCoreApplication.instance() or QCoreApplication([])
    server = _server()
    try:
        client = SessionClient(f"http://127.0.0.1:{server.server_port}")
        refreshed = []
        failed = []
        loop = QEventLoop()
        client.refreshed.connect(lambda data: (refreshed.append(data), loop.quit()))
        client.failed.connect(lambda message: (failed.append(message), loop.quit()))

        client.refresh("desktop-refresh-token")
        gc.collect()
        _wait(loop)

        assert failed == []
        assert refreshed == [
            {"access_token": "access", "refresh_token": "refresh"}
        ]
    finally:
        server.shutdown()
        server.server_close()
