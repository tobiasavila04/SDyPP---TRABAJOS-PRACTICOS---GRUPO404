#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Actualiza el código y reinicia todos los servicios HIT
# Llamado por el CI/CD en cada push a main.
# =============================================================================
set -euo pipefail

REPO_DIR="/home/ubuntu/SD2026-GRUPO404-TP1"
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

echo "==> [1/4] Actualizando código"
cd "$REPO_DIR"
git pull origin main

echo ""
echo "==> [2/4] Instalando dependencias"
source .venv/bin/activate
pip install --quiet -r requirements.txt

echo ""
echo "==> [3/4] Sincronizando archivos .service"
# Si los service files cambiaron en el repo, copiarlos y recargar
updated=0
for svc in "${SERVICES[@]}"; do
    src="$REPO_DIR/scripts/services/${svc}.service"
    dst="$SYSTEMD_DIR/${svc}.service"
    if ! cmp -s "$src" "$dst" 2>/dev/null; then
        sudo cp "$src" "$dst"
        echo "    ↺ ${svc}.service actualizado"
        updated=1
    fi
done
if [ "$updated" -eq 1 ]; then
    sudo systemctl daemon-reload
fi

echo ""
echo "==> [4/4] Reiniciando servicios"
for svc in "${SERVICES[@]}"; do
    if systemctl is-enabled "$svc" &>/dev/null; then
        sudo systemctl restart "$svc"
        status=$(systemctl is-active "$svc" || true)
        echo "    ✓ $svc → $status"
    else
        echo "    ⚠ $svc no está habilitado (ejecutá setup_services.sh primero)"
    fi
done

echo ""
echo "Deploy completado."
