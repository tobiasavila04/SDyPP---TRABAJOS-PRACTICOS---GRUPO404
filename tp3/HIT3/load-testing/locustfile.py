"""
Locust load test para la API de procesamiento Sobel distribuido.

Variables probadas:
  V1 — Tamaño de imagen : 1KB | 10KB | 100KB | 1MB | 10MB | 100MB
  V2 — Concurrencia     : controlada con --users y --spawn-rate de Locust
  V3 — Cantidad workers : variable externa (escalar el Deployment en K8s)

Uso:
  # Modo headless (sin UI):
  locust -f locustfile.py --host=http://<API_LOADBALANCER_IP> \
         --users 10 --spawn-rate 2 --run-time 2m --headless \
         --csv=results/run_10u

  # Con UI web (port 8089):
  locust -f locustfile.py --host=http://<API_LOADBALANCER_IP>
"""
import json
import os
import time

from locust import HttpUser, between, events, task

# ---------------------------------------------------------------------------
# Pre-carga de imágenes de prueba desde disco
# ---------------------------------------------------------------------------
IMAGES_DIR = os.path.join(os.path.dirname(__file__), "test_images")

_image_cache: dict[str, str] = {}


def _load_image(label: str) -> str:
    if label not in _image_cache:
        b64_path = os.path.join(IMAGES_DIR, f"{label}.b64")
        if not os.path.exists(b64_path):
            raise FileNotFoundError(
                f"Imagen '{label}' no encontrada. Ejecutar generate_test_images.py primero."
            )
        with open(b64_path, encoding="utf-8") as f:
            _image_cache[label] = f.read().strip()
    return _image_cache[label]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
POLL_TIMEOUT = 600   # 10 min máximos (100 MB puede tardar ~4-5 min con 2 workers)
POLL_INTERVAL = 1    # segundos entre polls


def _wait_for_result(client, job_id: str) -> tuple[bool, float]:
    """Espera hasta que el resultado esté disponible. Devuelve (ok, latencia_total)."""
    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT:
        url = f"/result/{job_id}"
        with client.get(url, catch_response=True, name="/result/[job_id]") as r:
            if r.status_code == 200:
                return True, time.time() - t0
            if r.status_code == 202:
                r.success()
            else:
                r.failure(f"Unexpected status {r.status_code}")
                return False, time.time() - t0
        time.sleep(POLL_INTERVAL)
    return False, time.time() - t0


def _process_image(user: "SobelUser", label: str):
    """Envía una imagen y espera el resultado midiendo latencia E2E."""
    img_b64 = _load_image(label)
    payload = json.dumps({"image_data": img_b64, "size_label": label})

    with user.client.post(
        "/process",
        data=payload,
        headers={"Content-Type": "application/json"},
        catch_response=True,
        name=f"/process [{label}]",
    ) as response:
        if response.status_code != 202:
            response.failure(f"POST /process devolvió {response.status_code}")
            return
        response.success()
        job_id = response.json().get("job_id")

    if not job_id:
        return

    ok, latency = _wait_for_result(user.client, job_id)
    # Registrar la latencia E2E como un evento personalizado para las estadísticas CSV
    events.request.fire(
        request_type="E2E",
        name=f"sobel_pipeline [{label}]",
        response_time=latency * 1000,
        response_length=0,
        exception=None if ok else Exception("Timeout esperando resultado"),
        context={},
    )


# ---------------------------------------------------------------------------
# Clases de usuario
# ---------------------------------------------------------------------------

class SobelUser(HttpUser):
    """Usuario genérico que prueba distintos tamaños con distribución uniforme."""
    wait_time = between(1, 3)

    @task(4)
    def process_small(self):
        _process_image(self, "1KB")

    @task(3)
    def process_medium(self):
        _process_image(self, "10KB")

    @task(2)
    def process_large(self):
        _process_image(self, "100KB")

    @task(1)
    def process_xlarge(self):
        _process_image(self, "1MB")

    @task
    def health_check(self):
        self.client.get("/health", name="/health")


class HeavyUser(HttpUser):
    """Usuario que solo manda imágenes grandes — útil para medir saturación."""
    wait_time = between(5, 15)

    @task(3)
    def process_heavy(self):
        _process_image(self, "10MB")

    @task(1)
    def process_extreme(self):
        _process_image(self, "100MB")
