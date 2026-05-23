"""Genera imágenes sintéticas de escala de grises con distintos tamaños para load testing."""
import base64
import os

import cv2
import numpy as np

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "test_images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# (label, ancho, alto) — ajustados para que el archivo JPEG resultante sea ~el tamaño indicado
SIZES = [
    ("1KB",   32,   32),
    ("10KB",  100,  100),
    ("100KB", 320,  320),
    ("1MB",   1000, 1000),
    ("10MB",  3200, 3200),
    ("100MB", 10000, 10000),
]


def generate_image(width: int, height: int) -> np.ndarray:
    """Imagen con gradiente + ruido para que JPEG no la comprima a cero."""
    base = np.zeros((height, width), dtype=np.uint8)
    for y in range(height):
        base[y, :] = int(255 * y / height)
    noise = np.random.randint(0, 30, (height, width), dtype=np.uint8)
    return cv2.add(base, noise)


def save_b64(label: str, img: np.ndarray) -> str:
    path = os.path.join(OUTPUT_DIR, f"{label}.jpg")
    cv2.imwrite(path, img)
    size_bytes = os.path.getsize(path)
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    b64_path = os.path.join(OUTPUT_DIR, f"{label}.b64")
    with open(b64_path, "w") as f:
        f.write(b64)
    print(f"  {label:6s}  {width}x{height}  →  {size_bytes:>10,} bytes  →  {path}")
    return b64_path


if __name__ == "__main__":
    print("Generando imágenes de prueba...\n")
    for label, width, height in SIZES:
        img = generate_image(width, height)
        save_b64(label, img)
    print("\nListo. Archivos guardados en:", OUTPUT_DIR)
