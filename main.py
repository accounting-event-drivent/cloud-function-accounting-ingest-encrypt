from flask import Flask, request, jsonify, Response
from utils import validate_file, upload_to_bucket, get_secret, circuit_breaker

# Inicialización de Flask
app = Flask("internal")

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response

@app.route("/api/v1/uploads", methods=["POST"])
@circuit_breaker
def handle_upload():
    try:
        file = request.files.get("file")
        validate_file(file)
        filename = upload_to_bucket(file)
        secret_payload = get_secret()
        return jsonify({
            "message": f"Archivo subido y cifrado exitosamente: {filename}"
        }), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503
    except Exception:
        return jsonify({"error": "Error interno del servidor"}), 500

@app.route("/api/v1/status", methods=["HEAD"])
def check_status():
    return Response(status=200)

# Enrutador personalizado
def main(request):
    """Enrutador para manejar las solicitudes."""
    # Crear contexto interno de Flask
    internal_ctx = app.test_request_context(
        path=request.full_path,
        method=request.method,
        query_string=request.query_string
    )

    # Copiar datos y encabezados de la solicitud original
    internal_ctx.request.data = request.get_data()
    internal_ctx.request.headers = request.headers

    # Copiar archivos si existen
    if request.files:
        internal_ctx.request.files = request.files

    # Procesar la solicitud con Flask
    try:
        internal_ctx.push()
        response = app.full_dispatch_request()
    except Exception:
        response = jsonify({"error": "Error interno del servidor"}), 500
    finally:
        internal_ctx.pop()

    return response
