#!/usr/bin/env python3
"""Print local ReliefQueue portal URLs for browser, phone, and Android emulator."""
from __future__ import annotations

import os
import socket
from urllib.parse import urlencode


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "<laptop-ip>"
    finally:
        sock.close()


def field_path(worker_id: str, role: str | None = None) -> str:
    query = {"worker_id": worker_id}
    if role:
        query["role"] = role
    return "/field/my-cases?" + urlencode(query)


def main() -> int:
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    port = os.environ.get("DASHBOARD_PORT", "5173")
    worker = os.environ.get("FIELD_WORKER_ID", "worker-alpha-boat")
    preferred = os.environ.get("RELIEFQUEUE_PREFERRED_PORTAL", "dashboard")
    laptop_ip = local_ip()
    phone_host = laptop_ip if host in {"0.0.0.0", "::"} else host
    android_host = "10.0.2.2" if host in {"127.0.0.1", "0.0.0.0", "::"} else host

    dashboard = f"http://{host}:{port}/dashboard"
    field = f"http://{host}:{port}{field_path(worker)}"
    phone_field = f"http://{phone_host}:{port}{field_path(worker)}"
    emulator_field = f"http://{android_host}:{port}{field_path(worker)}"

    print("ReliefQueue local portal URLs")
    print(f"preferred={preferred}")
    print(f"server=http://{host}:{port}")
    print(f"command_center={dashboard}")
    print(f"command_center_messaging_panel={dashboard}#messaging-channels")
    print(f"field_mobile={field}")
    print(f"field_mobile_local_coordinator=http://{host}:{port}{field_path(worker, 'local_coordinator')}")
    print(f"field_mobile_hub_staff=http://{host}:{port}{field_path(worker, 'hub_staff')}")
    print(f"phone_same_wifi={phone_field}")
    print(f"android_emulator={emulator_field}")
    print("")
    print("Start server with one of:")
    print("  make view-dashboard")
    print("  make view-field")
    print("  make view-field-mobile DASHBOARD_HOST=0.0.0.0")
    print("")
    print("For a real phone, keep laptop and phone on the same Wi-Fi and use phone_same_wifi.")
    print("For Android Emulator, use android_emulator while the dev server runs on the laptop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
