"""One-click Bolo-LAN: join an existing LAN game or host one automatically.

Usage:
    python launcher.py
    python launcher.py --host 192.168.1.20
"""
import argparse
import random
import socket
import threading
import time

from shared import PORT


def find_host(port, timeout=1.4):
    # Lazy import prevents bringing Pygame up before host discovery.
    from client import discover
    return discover(port, timeout=timeout)


def run(argv=None):
    parser = argparse.ArgumentParser(description="Bolo-LAN auto-host / auto-join launcher")
    parser.add_argument("--host", help="Skip discovery and join a specific server IP")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--name", help="Player nickname")
    args = parser.parse_args(argv)
    host = args.host

    if not host:
        print("Looking for an existing Bolo-LAN game...")
        host = find_host(args.port)

    if not host:
        # Stagger startup so computers launched together are less likely to
        # each create their own lobby. The port bind decides local ownership.
        time.sleep(random.uniform(0.25, 1.15))
        host = find_host(args.port, timeout=0.65)

    if not host:
        from server import GameServer
        try:
            server = GameServer(args.port)
        except OSError as exc:
            # Another local instance may already be starting.
            print(f"Cannot host ({exc}); searching again...")
            host = find_host(args.port, timeout=2.0)
            if not host:
                raise SystemExit("Could not host or find a LAN game. Check UDP firewall/port.")
        else:
            thread = threading.Thread(target=server.run, name="BoloLAN-Host", daemon=True)
            thread.start()
            host = "127.0.0.1"
            print("No existing game found. Hosting a new LAN game on this machine.")

    print(f"Joining {host}:{args.port}")
    from client import main
    client_args = ["--host", host, "--port", str(args.port)]
    if args.name:
        client_args.extend(["--name", args.name])
    main(client_args)


if __name__ == "__main__":
    run()
