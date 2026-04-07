"""
Benchmark de throughput para el servidor del HIT2.
Envia N tareas concurrentes y mide tareas completadas por minuto.

Uso:
    python benchmark.py --tareas 10
    python benchmark.py --tareas 10 --remote
    python benchmark.py --completo          # Corre para workers=1,2,4,8
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time

import requests

REMOTE_URL = "http://3.144.148.19:6000"
LOCAL_URL = "http://localhost:6000"


def enviar_tarea(server_url, resultados, lock):
    payload = {
        "operation": "suma",
        "values": [10.0, 20.0, 30.0],
    }
    inicio = time.time()
    try:
        resp = requests.post(f"{server_url}/task", json=payload, timeout=180)
        duracion = time.time() - inicio
        exito = resp.status_code == 200
        with lock:
            resultados.append(
                {
                    "exito": exito,
                    "duracion": duracion,
                    "status": resp.status_code,
                }
            )
    except Exception as e:
        duracion = time.time() - inicio
        with lock:
            resultados.append(
                {
                    "exito": False,
                    "duracion": duracion,
                    "error": str(e),
                }
            )


def correr_benchmark(server_url, num_tareas):
    resultados = []
    lock = threading.Lock()
    hilos = []

    print(f"  Enviando {num_tareas} tareas concurrentes...")
    inicio_total = time.time()

    for i in range(num_tareas):
        t = threading.Thread(
            target=enviar_tarea,
            args=(server_url, resultados, lock),
        )
        hilos.append(t)
        t.start()

    for t in hilos:
        t.join()

    duracion_total = time.time() - inicio_total
    exitosas = sum(1 for r in resultados if r["exito"])
    throughput = (exitosas / duracion_total) * 60 if duracion_total > 0 else 0
    duraciones = [r["duracion"] for r in resultados if r["exito"]]
    promedio = sum(duraciones) / len(duraciones) if duraciones else 0

    return {
        "tareas_totales": num_tareas,
        "exitosas": exitosas,
        "fallidas": num_tareas - exitosas,
        "duracion_total_seg": round(duracion_total, 2),
        "throughput_por_min": round(throughput, 2),
        "latencia_promedio_seg": round(promedio, 2),
    }


def limpiar_workers():
    for i in range(1, 9):
        subprocess.run(["docker", "rm", "-f", f"worker-{i}"], capture_output=True)


def main():
    parser = argparse.ArgumentParser(description="Benchmark de throughput HIT2")
    parser.add_argument(
        "--tareas",
        type=int,
        default=8,
        help="Numero de tareas concurrentes a enviar.",
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Usar servidor remoto AWS.",
    )
    parser.add_argument(
        "--completo",
        action="store_true",
        help="Correr benchmark completo con workers=1,2,4,8.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Segundos de delay simulado por tarea (default: 2.0).",
    )
    args = parser.parse_args()

    server_url = REMOTE_URL if args.remote else LOCAL_URL

    if args.completo:
        configs_workers = [1, 2, 4, 8]
        todos_los_resultados = []

        for n_workers in configs_workers:
            print(f"\n{'=' * 60}")
            print(f"Benchmark con {n_workers} worker(s) y {args.tareas} tareas")
            print(f"{'=' * 60}")

            # Matar servidor previo y limpiar containers
            subprocess.run(
                ["pkill", "-f", "python.*server.py"],
                capture_output=True,
            )
            limpiar_workers()
            time.sleep(2)

            # Iniciar servidor con N workers
            env = os.environ.copy()
            env["MAX_WORKERS"] = str(n_workers)
            env["TASK_DELAY"] = str(args.delay)
            server_dir = os.path.dirname(os.path.abspath(__file__))
            server_proc = subprocess.Popen(
                [sys.executable, os.path.join(server_dir, "server.py")],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Esperar a que el servidor y containers esten listos
            listo = False
            for _ in range(60):
                try:
                    r = requests.get(f"{LOCAL_URL}/health", timeout=2)
                    if r.status_code == 200:
                        listo = True
                        break
                except Exception:
                    pass
                time.sleep(1)

            if not listo:
                print(f"  ERROR: Servidor no arranco con {n_workers} workers.")
                server_proc.kill()
                limpiar_workers()
                continue

            metricas = correr_benchmark(LOCAL_URL, args.tareas)
            metricas["workers"] = n_workers
            todos_los_resultados.append(metricas)

            print(f"  Throughput: {metricas['throughput_por_min']} tareas/min")
            print(f"  Latencia promedio: {metricas['latencia_promedio_seg']}s")
            print(f"  Exitosas: {metricas['exitosas']}/{metricas['tareas_totales']}")
            print(f"  Duracion total: {metricas['duracion_total_seg']}s")

            server_proc.kill()
            server_proc.wait()
            limpiar_workers()
            time.sleep(2)

        # Tabla resumen
        print(f"\n{'=' * 60}")
        print("TABLA RESUMEN DE THROUGHPUT")
        print(f"{'=' * 60}")
        header = f"{'Workers':<10} {'Throughput/min':<18} {'Latencia(s)':<15} {'Duracion(s)':<15} {'Exitosas':<10}"
        print(header)
        print("-" * 68)

        base_tp = None
        for r in todos_los_resultados:
            if base_tp is None:
                base_tp = r["throughput_por_min"]
            print(
                f"{r['workers']:<10} "
                f"{r['throughput_por_min']:<18} "
                f"{r['latencia_promedio_seg']:<15} "
                f"{r['duracion_total_seg']:<15} "
                f"{r['exitosas']}/{r['tareas_totales']}"
            )

        # Speedup
        print(f"\n{'Workers':<10} {'Speedup':<10}")
        print("-" * 20)
        for r in todos_los_resultados:
            sp = r["throughput_por_min"] / base_tp if base_tp and base_tp > 0 else 0
            print(f"{r['workers']:<10} {round(sp, 2):<10}")

        # Guardar JSON
        out_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resultados_benchmark.json",
        )
        with open(out_path, "w") as f:
            json.dump(todos_los_resultados, f, indent=2)
        print(f"\nResultados guardados en {out_path}")

    else:
        print(f"Benchmark: {args.tareas} tareas contra {server_url}")
        print("(Asegurate de que el servidor este corriendo)")
        metricas = correr_benchmark(server_url, args.tareas)
        print("\nResultados:")
        print(json.dumps(metricas, indent=2))


if __name__ == "__main__":
    main()
