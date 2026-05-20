import json
import logging
import os
import socket
import struct
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app_paths import get_upload_queue_dir

try:
    import bluetooth
except ImportError:
    bluetooth = None


DEFAULT_SERVICE_UUID = "5e0ec070-4ef1-4f8e-9c12-7b0ac8cb3a11"
DEFAULT_TCP_PORT = 8765
DEFAULT_BT_CHANNEL = 4
HEADER_STRUCT = struct.Struct("!I")


class LinkError(RuntimeError):
    pass


def _safe_filename(name: str | None) -> str:
    candidate = (name or "").strip()
    if not candidate:
        candidate = f"clip_{int(time.time())}.mp4"
    return os.path.basename(candidate)


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise LinkError("Socket closed while receiving data")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def send_message(
    sock: socket.socket,
    payload: dict[str, Any],
    *,
    file_path: str | None = None,
) -> None:
    message = dict(payload)
    if file_path:
        message["content_length"] = os.path.getsize(file_path)

    encoded = json.dumps(message).encode("utf-8")
    sock.sendall(HEADER_STRUCT.pack(len(encoded)))
    sock.sendall(encoded)

    if file_path:
        with open(file_path, "rb") as handle:
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                sock.sendall(chunk)


def receive_message(
    sock: socket.socket,
    *,
    output_dir: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    header_size = HEADER_STRUCT.unpack(_recv_exact(sock, HEADER_STRUCT.size))[0]
    payload = json.loads(_recv_exact(sock, header_size).decode("utf-8"))
    content_length = int(payload.get("content_length", 0) or 0)
    if content_length <= 0:
        return payload, None

    if not output_dir:
        raise LinkError("output_dir is required when receiving a file payload")

    os.makedirs(output_dir, exist_ok=True)
    suffix = Path(_safe_filename(payload.get("filename"))).suffix or ".bin"
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=output_dir,
        prefix="incoming_",
        suffix=suffix,
    ) as handle:
        remaining = content_length
        while remaining > 0:
            chunk = sock.recv(min(64 * 1024, remaining))
            if not chunk:
                raise LinkError("Socket closed while receiving file body")
            handle.write(chunk)
            remaining -= len(chunk)
        file_path = handle.name

    return payload, file_path


def _get_transport() -> str:
    return os.getenv("WILDLIFE_LINK_TRANSPORT", "bluetooth").strip().lower() or "bluetooth"


def _get_port(transport: str) -> int:
    value = os.getenv("WILDLIFE_LINK_PORT", "").strip()
    if not value:
        return DEFAULT_BT_CHANNEL if transport == "bluetooth" else DEFAULT_TCP_PORT

    port = int(value)
    if transport == "bluetooth" and not (1 <= port <= 30):
        raise LinkError("Bluetooth RFCOMM channel must be between 1 and 30")
    return port


def _get_service_uuid() -> str:
    return os.getenv("WILDLIFE_LINK_SERVICE_UUID", DEFAULT_SERVICE_UUID).strip() or DEFAULT_SERVICE_UUID


class ParentLinkServer:
    def __init__(self):
        self._log = logging.getLogger("wildlife_cam")
        self.transport = _get_transport()
        self.port = _get_port(self.transport)
        self.service_uuid = _get_service_uuid()

    def _create_server_socket(self) -> socket.socket:
        if self.transport == "tcp":
            host = os.getenv("WILDLIFE_PARENT_BIND_HOST", "0.0.0.0").strip() or "0.0.0.0"
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, self.port))
            server.listen(1)
            self._log.info("Parent link server listening on tcp://%s:%d", host, self.port)
            return server

        if self.transport != "bluetooth":
            raise LinkError(f"Unsupported WILDLIFE_LINK_TRANSPORT: {self.transport}")
        if bluetooth is None:
            raise LinkError("PyBluez is required for bluetooth transport. Install with pip3 install pybluez2")

        server = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        server.bind(("", self.port))
        server.listen(1)
        channel = server.getsockname()[1]
        try:
            bluetooth.advertise_service(
                server,
                "WildlifeCamParent",
                service_id=self.service_uuid,
                service_classes=[self.service_uuid, bluetooth.SERIAL_PORT_CLASS],
                profiles=[bluetooth.SERIAL_PORT_PROFILE],
            )
        except Exception as exc:
            # BlueZ setups on Raspberry Pi often omit an SDP path for custom RFCOMM services.
            # The child can still connect directly to the configured channel.
            self._log.warning("Bluetooth SDP advertise failed, continuing without service discovery: %s", exc)
        self._log.info(
            "Parent link server listening on bluetooth RFCOMM channel %s (uuid=%s)",
            channel,
            self.service_uuid,
        )
        return server

    def serve_forever(self, handler) -> None:
        server = self._create_server_socket()
        try:
            while True:
                client, client_info = server.accept()
                self._log.info("Child connected: %s", client_info)
                try:
                    request, file_path = receive_message(
                        client,
                        output_dir=os.getenv("WILDLIFE_QUEUE_DIR", get_upload_queue_dir()),
                    )
                    response = handler(request, file_path)
                    send_message(client, response)
                except Exception as exc:
                    self._log.exception("Parent link request failed: %s", exc)
                    try:
                        send_message(client, {"ok": False, "error": str(exc)})
                    except Exception:
                        pass
                finally:
                    client.close()
        finally:
            server.close()


class ChildLinkClient:
    def __init__(self, *, trap_id: str):
        self._log = logging.getLogger("wildlife_cam")
        self.transport = _get_transport()
        self.port = _get_port(self.transport)
        self.service_uuid = _get_service_uuid()
        self.trap_id = trap_id
        self._cached_arm_state = True
        self._cached_arm_state_at = 0.0

    def _connect(self) -> socket.socket:
        if self.transport == "tcp":
            host = os.getenv("WILDLIFE_PARENT_HOST", "").strip()
            if not host:
                raise LinkError("WILDLIFE_PARENT_HOST is required for tcp transport")
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect((host, self.port))
            return client

        if self.transport != "bluetooth":
            raise LinkError(f"Unsupported WILDLIFE_LINK_TRANSPORT: {self.transport}")
        if bluetooth is None:
            raise LinkError("PyBluez is required for bluetooth transport. Install with pip3 install pybluez2")

        address = os.getenv("WILDLIFE_PARENT_BT_ADDR", "").strip()
        if not address:
            raise LinkError("WILDLIFE_PARENT_BT_ADDR is required for bluetooth transport")

        services = bluetooth.find_service(uuid=self.service_uuid, address=address)
        port = self.port
        if services:
            port = int(services[0]["port"])

        client = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        client.connect((address, port))
        return client

    def _request(self, payload: dict[str, Any], *, file_path: str | None = None) -> dict[str, Any]:
        client = self._connect()
        try:
            send_message(client, payload, file_path=file_path)
            response, _ = receive_message(client)
        finally:
            client.close()

        if not response.get("ok", False):
            raise LinkError(str(response.get("error", "Unknown parent response error")))
        return response

    def is_armed(self, cache_ttl_seconds: float = 10.0) -> bool:
        now = time.time()
        if now - self._cached_arm_state_at < cache_ttl_seconds:
            return self._cached_arm_state

        response = self._request(
            {
                "action": "get_arm_state",
                "trap_id": self.trap_id,
            }
        )
        self._cached_arm_state = bool(response.get("is_armed", True))
        self._cached_arm_state_at = now
        return self._cached_arm_state

    def send_video(self, file_path: str, *, trap_id: str, captured_at: str) -> bool:
        response = self._request(
            {
                "action": "upload_video",
                "trap_id": trap_id,
                "captured_at": captured_at,
                "filename": _safe_filename(file_path),
            },
            file_path=file_path,
        )
        accepted_at = response.get("accepted_at")
        if accepted_at:
            self._log.info("Parent accepted video at %s", accepted_at)
        return True


def apply_timestamp(file_path: str, captured_at: str | None) -> None:
    if not captured_at:
        return
    timestamp = datetime.fromisoformat(captured_at).timestamp()
    os.utime(file_path, (timestamp, timestamp))
