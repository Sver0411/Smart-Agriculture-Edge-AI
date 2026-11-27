"""Connect one gateway's JSON-lines TCP session to the live Linux XQUIC endpoint."""

import argparse
import asyncio
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import struct
import sys

MAX_LINE = 65537
METADATA = struct.Struct("!BI")
EVENT_TYPES = {"ALERT", "CONTROL_COMMAND", "CONTROL_RESULT", "PERSISTED_ACK", "SERVER_POLICY", "ACK"}


def endpoint(text):
    host, separator, port = text.rpartition(":")
    try:
        number = int(port)
        if not separator or not 0 < number < 65536:
            raise ValueError("invalid port")
        return str(ipaddress.IPv4Address(host)), number
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected IPv4:port") from error


def emit(event, role, **values):
    print(json.dumps(dict(event=event, role=role, **values), separators=(",", ":")), file=sys.stderr, flush=True)


def identify(line):
    if not line.endswith(b"\n") or len(line) > MAX_LINE or b"\n" in line[:-1]:
        raise ValueError("expected a single bounded JSON line")
    message = json.loads(line)
    if (not isinstance(message, dict) or not isinstance(message.get("message_id"), str)
            or not isinstance(message.get("type"), str)):
        raise ValueError("missing message type or identity")
    return message["type"], message["message_id"]


async def pump(reader, writer, ipc, args):
    loop = asyncio.get_running_loop()

    async def send():
        while line := await reader.readline():
            kind, identity = identify(line)
            event = kind in EVENT_TYPES
            budget = args.event_budget_ms if event else args.state_budget_ms
            packet = METADATA.pack(2 if event else 1, budget * 1000) + line
            # One sequenced packet represents one complete JSON message, including its original newline.
            await loop.sock_sendall(ipc, packet)
            emit("frame", args.role, direction="tcp_to_quic", message_id=identity, message_type=kind, bytes=len(line))

    async def receive():
        while line := await loop.sock_recv(ipc, MAX_LINE + 1):
            kind, identity = identify(line)
            writer.write(line)
            await writer.drain()
            emit("frame", args.role, direction="quic_to_tcp", message_id=identity, message_type=kind, bytes=len(line))

    tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def session(reader, writer, args):
    ipc, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    ipc.setblocking(False)
    native = None
    tasks = []
    try:
        addresses = [f"{host}:{port}" for host, port in (*args.local, *args.peer)]
        tls = [str(args.cert), str(args.key)] if args.role == "cloud" else [args.pin]
        native = await asyncio.create_subprocess_exec(
            str(args.binary), args.role, str(peer.fileno()), *addresses, *tls,
            pass_fds=(peer.fileno(),), stdout=None if args.trace else asyncio.subprocess.DEVNULL,
        )
        peer.close()
        emit("session_started", args.role, pid=native.pid)
        tasks = [asyncio.create_task(pump(reader, writer, ipc, args)), asyncio.create_task(native.wait())]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (OSError, ValueError, asyncio.IncompleteReadError) as error:
        emit("session_error", args.role, error=str(error))
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        ipc.close()
        peer.close()
        writer.close()
        if native is not None and native.returncode is None:
            try:
                await asyncio.wait_for(native.wait(), 1)
            except asyncio.TimeoutError:
                native.kill()
                await native.wait()
        try:
            await writer.wait_closed()
        except OSError:
            pass
        emit("session_closed", args.role, returncode=native.returncode if native else None)


async def run(args):
    if args.role == "cloud":
        while True:
            try:
                reader, writer = await asyncio.open_connection(*args.tcp, limit=MAX_LINE)
            except OSError:
                await asyncio.sleep(0.5)
                continue
            await session(reader, writer, args)
            await asyncio.sleep(0.2)
    else:
        clients = set()

        async def accept(reader, writer):
            if clients:
                writer.close()
                await writer.wait_closed()
                return
            task = asyncio.current_task()
            clients.add(task)
            try:
                await session(reader, writer, args)
            finally:
                clients.remove(task)

        listener = await asyncio.start_server(accept, *args.tcp, limit=MAX_LINE)
        emit("listening", args.role, address=args.tcp)
        try:
            async with listener:
                await listener.serve_forever()
        finally:
            active = list(clients)
            for task in active:
                task.cancel()
            await asyncio.gather(*active, return_exceptions=True)


def parse(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("gateway", "cloud"))
    parser.add_argument("--tcp", required=True, type=endpoint, help="local gateway listen or cloud backend address")
    parser.add_argument("--local", required=True, nargs=2, type=endpoint, metavar=("PATH_A", "PATH_B"))
    parser.add_argument("--peer", required=True, nargs=2, type=endpoint, metavar=("PATH_A", "PATH_B"))
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--cert", required=True, type=Path, help="cloud TLS certificate, pinned by the gateway")
    parser.add_argument("--key", type=Path, help="cloud TLS private key")
    parser.add_argument("--event-budget-ms", type=int, default=1000)
    parser.add_argument("--state-budget-ms", type=int, default=5000)
    parser.add_argument("--trace", action="store_true", help="write native XQUIC path/packet text traces to stdout")
    args = parser.parse_args(argv)
    if len(set(args.local)) != 2 or len(set(args.peer)) != 2:
        parser.error("each side needs two distinct UDP endpoints")
    if not all(1 <= v <= (2**32 - 1) // 1000 for v in (args.event_budget_ms, args.state_budget_ms)):
        parser.error("budgets must fit positive wire-format microseconds")
    if not args.binary.is_file() or not os.access(args.binary, os.X_OK):
        parser.error("--binary must point to the compiled agri-mpquic executable")
    args.binary = args.binary.resolve()
    if args.role == "cloud" and (not args.key or not args.key.is_file()):
        parser.error("cloud requires --key")
    if args.role == "gateway" and args.key:
        parser.error("the gateway only needs the public certificate")
    try:
        args.pin = hashlib.sha256(ssl.PEM_cert_to_DER_cert(args.cert.read_text())).hexdigest()
    except (OSError, ValueError) as error:
        parser.error(f"invalid --cert: {error}")
    return args


async def main(args):
    task = asyncio.create_task(run(args))
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
    try:
        await task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main(parse()))
