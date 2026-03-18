#!/usr/bin/env bash
# Genera los stubs Python a partir de sd2026.proto.
# Ejecutar una vez desde la raiz del repositorio:
#   bash tp1/HIT8/generate_stubs.sh

set -e

PROTO_DIR="tp1/HIT8"
OUT_DIR="tp1/HIT8"

python -m grpc_tools.protoc \
  --proto_path="$PROTO_DIR" \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  "$PROTO_DIR/sd2026.proto"

echo "Stubs generados en $OUT_DIR:"
ls "$OUT_DIR"/sd2026_pb2*.py