"""
HIT #8 - Nodo D: Registro de Contactos via gRPC + HTTP /health

Reemplaza el servidor TCP del HIT #6 por un servidor gRPC que implementa
RegistryService (Register, Health, GetNodes).
El endpoint HTTP /health (FastAPI) se mantiene para verificacion publica.

Uso:
    uvicorn tp1.HIT8.node_d:app --host 0.0.0.0 --port 8080
    (el servidor gRPC arranca automaticamente en GRPC_PORT al importar)
"""

import os
import sys
import threading
import time
from concurrent import futures
from datetime import datetime, timezone
from pathlib import Path

# Asegurar que los stubs se puedan importar
sys.path.insert(0, str(Path(__file__).parent))

import grpc
import sd2026_pb2
import sd2026_pb2_grpc
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------

GRPC_PORT = int(os.getenv("GRPC_PORT", "50051"))

# ---------------------------------------------------------------------------
# Estado en memoria
# ---------------------------------------------------------------------------

_start_time = time.time()
_registry: list[dict] = []
_registry_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Implementacion gRPC — RegistryService
# ---------------------------------------------------------------------------


class RegistryServicer(sd2026_pb2_grpc.RegistryServiceServicer):
    """Implementa Register, Health y GetNodes sobre gRPC."""

    def Register(self, request, context):
        node = {
            "host": request.host,
            "port": request.port,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        with _registry_lock:
            already = any(
                n["host"] == node["host"] and n["port"] == node["port"]
                for n in _registry
            )
            if not already:
                _registry.append(node)
            peers_snapshot = [
                n
                for n in _registry
                if not (n["host"] == node["host"] and n["port"] == node["port"])
            ]

        print(
            f"[D-gRPC] Registrado {node['host']}:{node['port']} "
            f"— total: {len(_registry)}"
        )

        return sd2026_pb2.RegisterResponse(
            assigned_window="current",
            peers=[
                sd2026_pb2.NodeInfo(
                    host=p["host"],
                    port=p["port"],
                    registered_at=p["registered_at"],
                )
                for p in peers_snapshot
            ],
        )

    def Unregister(self, request, context):
        host, port = request.host, request.port
        with _registry_lock:
            before = len(_registry)
            _registry[:] = [
                n for n in _registry if not (n["host"] == host and n["port"] == port)
            ]
            removed = len(_registry) < before
        print(f"[D-gRPC] Desconectado {host}:{port} — total: {len(_registry)}")
        return sd2026_pb2.UnregisterResponse(removed=removed)

    def Health(self, request, context):
        with _registry_lock:
            count = len(_registry)
        return sd2026_pb2.HealthResponse(
            status="healthy",
            registered_nodes=count,
            uptime_seconds=round(time.time() - _start_time, 1),
            grpc_port=GRPC_PORT,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def GetNodes(self, request, context):
        with _registry_lock:
            nodes = list(_registry)
        return sd2026_pb2.NodesResponse(
            count=len(nodes),
            nodes=[
                sd2026_pb2.NodeInfo(
                    host=n["host"],
                    port=n["port"],
                    registered_at=n["registered_at"],
                )
                for n in nodes
            ],
        )


# ---------------------------------------------------------------------------
# Arrancar servidor gRPC en background
# ---------------------------------------------------------------------------


def _start_grpc_server() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    sd2026_pb2_grpc.add_RegistryServiceServicer_to_server(RegistryServicer(), server)
    server.add_insecure_port(f"0.0.0.0:{GRPC_PORT}")
    server.start()
    print(f"[D-gRPC] Servidor escuchando en 0.0.0.0:{GRPC_PORT}")
    server.wait_for_termination()


threading.Thread(target=_start_grpc_server, daemon=True, name="grpc-server").start()

# ---------------------------------------------------------------------------
# FastAPI — endpoint HTTP publico
# ---------------------------------------------------------------------------

app = FastAPI(title="SD2026-GRUPO404 Node D — HIT #8 gRPC", version="3.0.0")


@app.get("/")
def root():
    return {"service": "node-d", "hit": 8, "protocol": "gRPC+protobuf"}


@app.get("/health")
def health():
    with _registry_lock:
        count = len(_registry)
    return {
        "status": "healthy",
        "registered_nodes": count,
        "uptime_seconds": round(time.time() - _start_time, 1),
        "grpc_port": GRPC_PORT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/nodes")
def list_nodes():
    with _registry_lock:
        nodes = list(_registry)
    return {"count": len(nodes), "nodes": nodes}


@app.delete("/nodes")
def clear_nodes():
    with _registry_lock:
        _registry.clear()
    return {"message": "Registro limpiado."}