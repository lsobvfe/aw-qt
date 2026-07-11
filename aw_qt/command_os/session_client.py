"""Desktop auth-session refresh client."""

from __future__ import annotations

import json

from PyQt6.QtCore import QByteArray, QObject, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class SessionClient(QObject):
    refreshed = pyqtSignal(dict)
    failed = pyqtSignal(str)
    authorization_required = pyqtSignal()

    def __init__(self, base_url: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._url = QUrl(base_url.rstrip("/") + "/api/v1/auth/refresh")
        self._network = QNetworkAccessManager(self)

    def refresh(self, refresh_token: str) -> None:
        request = QNetworkRequest(self._url)
        request.setTransferTimeout(8_000)
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        reply = self._network.post(
            request,
            QByteArray(json.dumps({"refresh_token": refresh_token}).encode("utf-8")),
        )
        reply.finished.connect(lambda current=reply: self._handle(current))

    def _handle(self, reply: QNetworkReply) -> None:
        try:
            raw = bytes(reply.readAll()).decode("utf-8")
            payload = json.loads(raw)
            status = int(
                reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0
            )
            if status == 401:
                self.authorization_required.emit()
                return
            payload_is_object = isinstance(payload, dict)
            response_status_is_valid = (
                payload_is_object and payload.get("status") == "success"
            )
            response_data_is_valid = (
                payload_is_object and isinstance(payload.get("data"), dict)
            )
            invalid_response = any(
                (
                    reply.error() != QNetworkReply.NetworkError.NoError,
                    not payload_is_object,
                    not response_status_is_valid,
                    not response_data_is_valid,
                )
            )
            if invalid_response:
                self.failed.emit("Desktop session refresh failed")
                return
            self.refreshed.emit(payload["data"])
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.failed.emit("Desktop session refresh returned invalid JSON")
        finally:
            reply.deleteLater()
