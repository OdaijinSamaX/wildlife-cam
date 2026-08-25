#!/usr/bin/env python3
"""Phase-1 raw-HCI BLE advertiser/scanner probe for wildlife-cam.

Python 3.13 cannot express sockaddr_hci.hci_channel, so libc.bind(2) is
used for HCI_CHANNEL_USER.  Exactly one HCI command is outstanding: every
command waits for its matching Command Complete/Status before another is sent.
"""

from __future__ import annotations

import argparse
import io
import ctypes
import hashlib
import hmac
import os
import select
import socket
import struct
import time

AF_BLUETOOTH = 31
BTPROTO_HCI = 1
HCI_CHANNEL_USER = 1
HCI_COMMAND_PKT = 0x01
HCI_EVENT_PKT = 0x04
EVT_CMD_COMPLETE = 0x0E
EVT_CMD_STATUS = 0x0F

OGF_HOST_CTL = 0x03
OGF_LE_CTL = 0x08


def opcode(ogf: int, ocf: int) -> int:
    return (ogf << 10) | ocf


OP_RESET = opcode(OGF_HOST_CTL, 0x0003)
OP_LE_SET_RANDOM_ADDRESS = opcode(OGF_LE_CTL, 0x0005)
OP_LE_SET_ADV_PARAMETERS = opcode(OGF_LE_CTL, 0x0006)
OP_LE_SET_ADV_DATA = opcode(OGF_LE_CTL, 0x0008)
OP_LE_SET_ADV_ENABLE = opcode(OGF_LE_CTL, 0x000A)
OP_LE_SET_SCAN_PARAMETERS = opcode(OGF_LE_CTL, 0x000B)
OP_LE_SET_SCAN_ENABLE = opcode(OGF_LE_CTL, 0x000C)
OP_LE_CLEAR_ACCEPT_LIST = opcode(OGF_LE_CTL, 0x0010)
OP_LE_ADD_ACCEPT_LIST = opcode(OGF_LE_CTL, 0x0011)


class SockaddrHCI(ctypes.Structure):
    _fields_ = [
        ("hci_family", ctypes.c_ushort),
        ("hci_dev", ctypes.c_ushort),
        ("hci_channel", ctypes.c_ushort),
    ]


class HCIError(RuntimeError):
    pass


class HCIUser:
    def __init__(self, device: int, timeout: float = 2.0):
        self.device = device
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.outstanding = 0
        self.max_outstanding = 0
        self.command_timeouts = 0

    def open(self) -> None:
        libc = ctypes.CDLL(None, use_errno=True)
        libc.bind.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
        libc.bind.restype = ctypes.c_int
        address = SockaddrHCI(AF_BLUETOOTH, self.device, HCI_CHANNEL_USER)
        sock = socket.socket(AF_BLUETOOTH, socket.SOCK_RAW, BTPROTO_HCI)
        sock.setblocking(False)
        if libc.bind(sock.fileno(), ctypes.byref(address), ctypes.sizeof(address)):
            error_number = ctypes.get_errno()
            sock.close()
            raise OSError(error_number, os.strerror(error_number))
        self.sock = sock
        print(f"USER_BIND_OK dev={self.device}", flush=True)

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None
            print("USER_SOCKET_CLOSED", flush=True)

    def command(self, command_opcode: int, parameters: bytes = b"") -> bytes:
        if self.sock is None:
            raise HCIError("HCI socket is not open")
        if self.outstanding != 0:
            raise HCIError("flow violation: another HCI command is outstanding")
        packet = struct.pack("<BHB", HCI_COMMAND_PKT, command_opcode, len(parameters)) + parameters
        self.outstanding = 1
        self.max_outstanding = max(self.max_outstanding, self.outstanding)
        try:
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    sent = self.sock.send(packet)
                    if sent != len(packet):
                        raise HCIError(f"short HCI send: {sent}/{len(packet)}")
                    break
                except BlockingIOError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("HCI socket remained non-writable")
                    select.select([], [self.sock], [], remaining)

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.command_timeouts += 1
                    raise TimeoutError(f"HCI command 0x{command_opcode:04x} timed out")
                readable, _, _ = select.select([self.sock], [], [], remaining)
                if not readable:
                    continue
                event = self.sock.recv(260)
                if len(event) < 3 or event[0] != HCI_EVENT_PKT:
                    continue
                event_code = event[1]
                payload = event[3:3 + event[2]]
                if event_code == EVT_CMD_COMPLETE and len(payload) >= 4:
                    returned_opcode = struct.unpack_from("<H", payload, 1)[0]
                    if returned_opcode != command_opcode:
                        continue
                    status = payload[3]
                    if status:
                        raise HCIError(f"command 0x{command_opcode:04x} status=0x{status:02x}")
                    return payload[4:]
                if event_code == EVT_CMD_STATUS and len(payload) >= 4:
                    returned_opcode = struct.unpack_from("<H", payload, 2)[0]
                    if returned_opcode != command_opcode:
                        continue
                    status = payload[0]
                    if status:
                        raise HCIError(f"command 0x{command_opcode:04x} status=0x{status:02x}")
                    return b""
        finally:
            self.outstanding = 0


def address_bytes(address: str) -> bytes:
    octets = bytes(int(part, 16) for part in address.split(":"))
    if len(octets) != 6:
        raise ValueError("Bluetooth address must contain six octets")
    return octets[::-1]


def command_payload(seq: int, epoch: int, link_id: int, key: bytes) -> bytes:
    # company_id is little-endian on air. HMAC covers ver through reserved.
    authenticated = struct.pack(
        "<BBBIBBBBB", 1, 1, link_id, seq, 0, 0, 0, 0, 0
    )
    # Insert epoch between link_id and seq to match design section 4.1.
    authenticated = authenticated[:3] + struct.pack("<H", epoch) + authenticated[3:]
    mac = hmac.new(key, authenticated, hashlib.sha256).digest()[:8]
    payload = struct.pack("<H", 0xFFFF) + authenticated + mac
    if len(payload) != 24:
        raise AssertionError(f"manufacturer payload length is {len(payload)}, expected 24")
    return payload


def advertising_data(seq: int, epoch: int, link_id: int, key: bytes) -> bytes:
    manufacturer = command_payload(seq, epoch, link_id, key)
    ad = bytes((1 + len(manufacturer), 0xFF)) + manufacturer
    if len(ad) > 31:
        raise AssertionError("advertising data exceeds legacy 31-byte limit")
    return bytes((len(ad),)) + ad.ljust(31, b"\0")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--duration", type=float, default=610.0)
    parser.add_argument("--epoch", type=int, default=1)
    parser.add_argument("--link-id", type=lambda value: int(value, 0), default=0x42)
    parser.add_argument("--key", default="phase1-public-test-key")
    parser.add_argument("--key-file", default=None,
                        help="鍵をファイルから読む(argv/ps に出さない)。--key より優先")
    parser.add_argument("--peer-address", default="C2:00:00:00:00:01")
    parser.add_argument(
        "--leave-enabled-until-close",
        action="store_true",
        help="skip explicit scan/advertising disable to test USER close semantics",
    )
    args = parser.parse_args()

    if args.key_file:
        with io.open(args.key_file, "r", encoding="ascii") as fh:
            args.key = fh.read().strip()
        if len(args.key) < 16:
            raise SystemExit("key-file の中身が短すぎます (16 文字以上)")


    hci = HCIUser(args.device)
    advertising_enabled = False
    scanning_enabled = False
    seq = 0
    seq_updates = 0
    max_seq_gap = 0.0
    started = time.monotonic()
    last_update = started
    try:
        hci.open()
        hci.command(OP_RESET)
        # Static random address: two top bits of the most-significant octet are 1.
        hci.command(OP_LE_SET_RANDOM_ADDRESS, address_bytes("C2:57:49:4C:44:01"))
        hci.command(OP_LE_CLEAR_ACCEPT_LIST)
        hci.command(OP_LE_ADD_ACCEPT_LIST, b"\x01" + address_bytes(args.peer_address))

        # min/max 0x00a0 = 100 ms; type 0x03 = ADV_NONCONN_IND;
        # own address random; all three advertising channels; allow all scanners.
        adv_parameters = struct.pack(
            "<HHBBB6sBB", 0x00A0, 0x00A0, 0x03, 0x01, 0x00,
            b"\0" * 6, 0x07, 0x00,
        )
        hci.command(OP_LE_SET_ADV_PARAMETERS, adv_parameters)
        # Passive scan, 100 ms interval, 50 ms window, random own address,
        # filter policy 0x01 = accept-list only.
        scan_parameters = struct.pack("<BHHBB", 0x00, 0x00A0, 0x0050, 0x01, 0x01)
        hci.command(OP_LE_SET_SCAN_PARAMETERS, scan_parameters)
        hci.command(OP_LE_SET_ADV_DATA, advertising_data(seq, args.epoch, args.link_id, args.key.encode()))
        hci.command(OP_LE_SET_ADV_ENABLE, b"\x01")
        advertising_enabled = True
        # Filter_Duplicates=0x00 is mandatory.
        hci.command(OP_LE_SET_SCAN_ENABLE, b"\x01\x00")
        scanning_enabled = True
        print("ADV_SCAN_ENABLED interval_ms=100 adv=ADV_NONCONN_IND filter_duplicates=0 filter_policy=1", flush=True)

        next_update = time.monotonic() + 0.1
        end = started + args.duration
        while time.monotonic() < end:
            delay = next_update - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            seq += 1
            hci.command(
                OP_LE_SET_ADV_DATA,
                advertising_data(seq, args.epoch, args.link_id, args.key.encode()),
            )
            now = time.monotonic()
            max_seq_gap = max(max_seq_gap, now - last_update)
            last_update = now
            seq_updates += 1
            if seq_updates % 100 == 0:
                print(f"PROGRESS seq={seq} elapsed={now-started:.1f}s max_gap_ms={max_seq_gap*1000:.1f}", flush=True)
            next_update += 0.1
    finally:
        if hci.sock is not None:
            try:
                if not args.leave_enabled_until_close:
                    if scanning_enabled:
                        hci.command(OP_LE_SET_SCAN_ENABLE, b"\x00\x00")
                    if advertising_enabled:
                        hci.command(OP_LE_SET_ADV_ENABLE, b"\x00")
            except Exception as exc:
                print(f"DISABLE_ERROR {exc!r}", flush=True)
            print(
                f"SUMMARY seq={seq} updates={seq_updates} max_gap_ms={max_seq_gap*1000:.1f} "
                f"max_outstanding={hci.max_outstanding} command_timeouts={hci.command_timeouts}",
                flush=True,
            )
            hci.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
