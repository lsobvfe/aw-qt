"""Asynchronous Command OS client using Qt networking."""

from __future__ import annotations

import json
from collections.abc import Callable
from uuid import uuid4

from PyQt6.QtCore import QByteArray, QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class CommandClient(QObject):
    completed = pyqtSignal(str, dict)
    failed = pyqtSignal(str, str)
    unauthorized = pyqtSignal()

    def __init__(self, base_url: str, token_provider: Callable[[], str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._execute_url = QUrl(base_url.rstrip("/") + "/api/v1/commands/execute")
        self._token_provider = token_provider
        self._network = QNetworkAccessManager(self)

    def execute(self, command: str, args: dict | None = None) -> str:
        token = self._token_provider().strip()
        if not token:
            request_id = f"desktop_{uuid4().hex}"
            QTimer.singleShot(
                0,
                lambda: self.failed.emit(
                    request_id,
                    "Desktop authorization is required",
                ),
            )
            return request_id
        request_id = f"desktop_{uuid4().hex}"
        request = QNetworkRequest(self._execute_url)
        request.setTransferTimeout(8_000)
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        request.setRawHeader(b"Authorization", f"Bearer {token}".encode("utf-8"))
        request.setRawHeader(b"Idempotency-Key", request_id.encode("ascii"))
        body = {
            "command": command,
            "args": args or {},
            "requestId": request_id,
            "sessionId": "activitywatch-floating-timer",
            "source": "api",
        }
        reply = self._network.post(request, QByteArray(json.dumps(body).encode("utf-8")))
        reply.setProperty("command_os_request_id", request_id)
        reply.finished.connect(lambda current=reply: self._handle_reply(current))
        return request_id

    def _handle_reply(self, reply: QNetworkReply) -> None:
        request_id = str(reply.property("command_os_request_id") or "")
        try:
            raw = bytes(reply.readAll()).decode("utf-8")
            if reply.error() != QNetworkReply.NetworkError.NoError:
                status = int(reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0)
                if status == 401:
                    self.unauthorized.emit()
                self.failed.emit(request_id, f"Command OS request failed: HTTP {reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0}")
                return
            payload = json.loads(raw)
            if not isinstance(payload, dict) or payload.get("status") != "success":
                message = payload.get("message") if isinstance(payload, dict) else ""
                self.failed.emit(request_id, str(message or "Command OS returned an invalid response"))
                return
            data = payload.get("data")
            if not isinstance(data, dict):
                self.failed.emit(request_id, "Command OS response data must be an object")
                return
            self.completed.emit(request_id, data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.failed.emit(request_id, f"Command OS response is not valid JSON: {exc}")
        finally:
            reply.deleteLater()
