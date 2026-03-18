"""
HIT #8 - Nodo C: Saludos via gRPC + registro en D via gRPC

Reemplaza toda la comunicacion JSON/TCP por gRPC con Protocol Buffers:
  - Levanta un servidor gRPC implementando GreetingService
  - Se registra en D llamando a RegistryService.Register via gRPC
  - Saluda a cada peer llamando a GreetingService.Greet via gRPC

Uso:
    python3 node_c.py --registry-host <ip_D> --registry-grpc-port <puerto_gRPC_D>
                      [--own-host <mi_ip_visible>]
"""

import argparse
import sys
import threading
import time
from concurrent import futures
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import grpc
import sd2026_pb2
import sd2026_pb2_grpc

RECONNECT_DELAY = 2


# ---------------------------------------------------------------------------
# Implementacion gRPC — GreetingService
# ---------------------------------------------------------------------------


class GreetingServicer(sd2026_pb2_grpc.GreetingServiceServicer):
    """Recibe saludos de otros nodos C y responde."""

    def __init__(self, own_port: int):
        self._own_port = own_port

    def Greet(self, request, context):
        print(
            f"[C-SERVER] Saludo gRPC recibido — "
            f"from_port={request.from_port} msg='{request.message}'"
        )
        return sd2026_pb2.GreetingResponse(
            from_port=self._own_port,
            message=f"Hola! Soy C en puerto {self._own_port}. Saludo recibido.",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


def start_greeting_server() -> int:
    """Arranca el servidor gRPC de saludos. Retorna el puerto asignado."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    # Obtener el puerto real antes de crear el servicer
    assigned_port = server.add_insecure_port("[::]:0")
    sd2026_pb2_grpc.add_GreetingServiceServicer_to_server(
        GreetingServicer(assigned_port), server
    )
    server.start()
    print(f"[C-SERVER] Servidor gRPC de saludos en puerto {assigned_port}")
    threading.Thread(target=server.wait_for_termination, daemon=True).start()
    return assigned_port


# ---------------------------------------------------------------------------
# Registro en D y saludo a peers
# ---------------------------------------------------------------------------


def register_and_greet(
    registry_host: str,
    registry_grpc_port: int,
    own_host: str,
    own_grpc_port: int,
) -> None:
    """Llama a RegistryService.Register en D y saluda a los peers devueltos."""
    channel = grpc.insecure_channel(f"{registry_host}:{registry_grpc_port}")
    stub = sd2026_pb2_grpc.RegistryServiceStub(channel)

    attempt = 1
    while True:
        print(
            f"[C] Intento #{attempt} — registrandose en D "
            f"({registry_host}:{registry_grpc_port})..."
        )
        try:
            response = stub.Register(
                sd2026_pb2.RegisterRequest(host=own_host, port=own_grpc_port),
                timeout=5,
            )
            break
        except grpc.RpcError as e:
            print(f"[C] Error gRPC: {e.code()}. Reintentando en {RECONNECT_DELAY}s...")
            attempt += 1
            time.sleep(RECONNECT_DELAY)

    channel.close()

    peers = list(response.peers)
    print(f"[C] Registrado. Peers activos: {len(peers)}")

    for peer in peers:
        _greet_peer(peer.host, peer.port, own_grpc_port)


def _greet_peer(host: str, port: int, own_port: int) -> None:
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        stub = sd2026_pb2_grpc.GreetingServiceStub(channel)
        response = stub.Greet(
            sd2026_pb2.GreetingRequest(
                from_port=own_port,
                message=f"Hola! Soy C en puerto {own_port}.",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
            timeout=5,
        )
        print(
            f"[C-CLIENT] Respuesta gRPC de {host}:{port} — "
            f"from_port={response.from_port} msg='{response.message}'"
        )
        channel.close()
    except grpc.RpcError as e:
        print(f"[C-CLIENT] No se pudo saludar a {host}:{port} — {e.code()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _unregister(
    registry_host: str, registry_grpc_port: int, own_host: str, own_grpc_port: int
) -> None:
    try:
        channel = grpc.insecure_channel(f"{registry_host}:{registry_grpc_port}")
        stub = sd2026_pb2_grpc.RegistryServiceStub(channel)
        stub.Unregister(
            sd2026_pb2.UnregisterRequest(host=own_host, port=own_grpc_port),
            timeout=3,
        )
        channel.close()
        print("[C] Desinscripto de D.")
    except grpc.RpcError:
        pass


def _get_own_ip() -> str:
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Nodo C gRPC (HIT #8)")
    parser.add_argument("--registry-host", required=True)
    parser.add_argument("--registry-grpc-port", type=int, default=50051)
    parser.add_argument("--own-host", default=None)
    args = parser.parse_args()

    if args.own_host:
        own_host = args.own_host
    elif args.registry_host in ("127.0.0.1", "localhost"):
        own_host = "127.0.0.1"
    else:
        own_host = _get_own_ip()

    # Arrancar servidor gRPC de saludos (puerto asignado por el SO)
    own_grpc_port = start_greeting_server()

    print(f"[C] Iniciando en {own_host}:{own_grpc_port}")

    threading.Thread(
        target=register_and_greet,
        args=(args.registry_host, args.registry_grpc_port, own_host, own_grpc_port),
        daemon=True,
        name="c-register",
    ).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[C] Terminando.")
        _unregister(
            args.registry_host, args.registry_grpc_port, own_host, own_grpc_port
        )


if __name__ == "__main__":
    main()