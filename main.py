from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from utils import validate_file, upload_to_bucket, circuit_breaker
from vision_utils import is_invoice_or_receipt  

# Inicialización de Flask
app = Flask("internal")
CORS(app, resources={r"/*": {"origins": "*"}})

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

        # Validar si es factura o recibo
        if not is_invoice_or_receipt(file):
            return jsonify({
                "success": False,
                "error": "El archivo no parece ser una factura o recibo."
            }), 400

        # Subir el archivo al bucket
        filename = upload_to_bucket(file)
        return jsonify({
            "success": True,
            "message": f"Archivo subido y cifrado exitosamente: {filename}",
            "filename": filename  # Solo el nombre del archivo
        }), 200

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    except RuntimeError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 503
    except Exception as e:
        return jsonify({
            "success": False,
            "error": "Error interno del servidor"
        }), 500

@app.route("/api/v1/status", methods=["HEAD", "GET"])
def check_status():
    if request.method == "HEAD":
        return Response(status=200)
    return jsonify({"status": "ok"}), 200


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
        response = jsonify({
            "success": False,
            "error": "Error interno del servidor"
        }), 500
    finally:
        internal_ctx.pop()

    return response
