import logging

from flask import Flask, jsonify, request

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [TAREA] %(message)s")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/run", methods=["POST"])
def ejecutarServidorTarea():
    data = request.get_json()

    operacion = data.get("operation")
    valores = data.get("values")

    if not operacion or not valores:
        return jsonify({"error": "Faltan los campos 'operation' o 'values'"}), 400

    logging.info(f"Recibida tarea: {operacion} con valores {valores}")

    if operacion == "suma":
        resultado = sum(valores)

    elif operacion == "resta":
        resultado = valores[0] - sum(valores[1:])

    elif operacion == "multiplicacion":
        resultado = 1
        for valor in valores:
            resultado *= valor

    elif operacion == "division":
        resultado = valores[0]
        for v in valores[1:]:
            if v == 0:
                return jsonify({"error": "División por cero no permitida"}), 400
            resultado /= v
    else:
        return jsonify({"error": "Operación no soportada"}), 400

    logging.info(f"Resultado de la tarea: {resultado}")

    return jsonify({"resultado": resultado, "operacion": operacion, "valores": valores})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
