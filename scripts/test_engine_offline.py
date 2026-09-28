"""Run the regression suite with live modules disabled and outbound sockets blocked.

Run from the repository root: .venv/Scripts/python scripts/test_engine_offline.py
Additional arguments are passed to pytest (for example a particular test file).
"""
from pathlib import Path
import os
import socket
import ipaddress
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    os.environ["SMARTBUY_LIVE_TESTS"] = "0"
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    report = root / "evaluation" / "reports" / "validation-offline.xml"
    report.parent.mkdir(parents=True, exist_ok=True)
    original_connect, original_connect_ex, original_create = socket.socket.connect, socket.socket.connect_ex, socket.create_connection

    def blocked(*args, **kwargs):
        raise RuntimeError("Outbound network disabled by SmartBuy offline test runner")

    def local_only(original):
        def connect(sock, address):
            # Windows asyncio uses a TCP loopback socketpair internally.
            if isinstance(address, tuple):
                try:
                    if ipaddress.ip_address(address[0]).is_loopback:
                        return original(sock, address)
                except ValueError:
                    pass
            return blocked()
        return connect

    socket.socket.connect = local_only(original_connect)
    socket.socket.connect_ex = local_only(original_connect_ex)
    socket.create_connection = blocked
    try:
        import pytest
        return pytest.main(["-q", "-p", "no:cacheprovider", "--junitxml=" + str(report), *sys.argv[1:]])
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection = original_connect, original_connect_ex, original_create


if __name__ == "__main__":
    raise SystemExit(main())
