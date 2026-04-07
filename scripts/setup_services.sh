#!/usr/bin/env bash
# =============================================================================
# setup_services.sh — Configuración inicial de servicios systemd en EC2
# Ejecutar UNA SOLA VEZ con sudo desde el repo:
#   sudo bash scripts/setup_services.sh
# =============================================================================
set -euo pipefail

REPO_DIR="/home/ubuntu/SD2026-GRUPO404-TP1"
SERVICES_DIR="$REPO_DIR/scripts/services"
SYSTEMD_DIR="/etc/systemd/system"

SERVICES=(
    hit1-server
    hit2-server
    hit3-server
    hit4-node-c1
    hit4-node-c2
    hit5-node-c1
    hit5-node-c2
    hit6-node-d
    hit7-node-d
    hit8-node-d
    hit-health
    tp2-hit1-server
    tp2-hit2-server
    tp2-hit3-cluster
)

echo "==> Copiando archivos .service a $SYSTEMD_DIR"
for svc in "${SERVICES[@]}"; do
    cp "$SERVICES_DIR/${svc}.service" "$SYSTEMD_DIR/${svc}.service"
    echo "    ✓ ${svc}.service"
done

echo ""
echo "==> Recargando systemd"
systemctl daemon-reload

echo ""
echo "==> Habilitando e iniciando servicios"
for svc in "${SERVICES[@]}"; do
    systemctl enable "$svc"
    systemctl start  "$svc"
    echo "    ✓ $svc — $(systemctl is-active $svc)"
done

echo ""
echo "==> Resumen de puertos en uso (todos abiertos en el Security Group de EC2):"
echo "    HIT1  server_b  → TCP  5000  (clientes locales: python client_a.py --remote)"
echo "    HIT2  server_b  → TCP  5001  (clientes locales: python client_a.py --remote)"
echo "    HIT3  server_b  → TCP  5002  (clientes locales: python client_a.py --remote)"
echo "    HIT4  node-c1   → TCP  5003  (clientes locales: python node_c.py --remote --listen-port <N>)"
echo "    HIT4  node-c2   → TCP  5004  (par interno en EC2)"
echo "    HIT5  node-c1   → TCP  5003  (clientes locales: python node_c.py --remote --listen-port <N>)"
echo "    HIT5  node-c2   → TCP  5004  (par interno en EC2)"
echo "    HIT6  node-d    → TCP  5005  (registro) / HTTP 8086 (interno)"
echo "    HIT7  node-d    → TCP  5006  (registro) / HTTP 8087 (interno)"
echo "    HIT8  node-d    → gRPC 5007               / HTTP 8088 (interno)"
echo "    Health check    → HTTP 5010  /health"
echo ""
echo "  TP2:"
echo "    HIT1  server    → TCP  6000  (orquestador con containers efímeros)"
echo "    HIT2  server    → TCP  6001  (pool de workers con Lamport)"
echo "    HIT3  cluster   → TCP  6080  (LB nginx) / 7001-7003 (nodos Bully)"
echo ""
echo "Setup completo."
