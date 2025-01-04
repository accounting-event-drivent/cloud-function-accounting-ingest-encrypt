from flask import Flask, request, jsonify, Response
from flask_cors import CORS 
from google.cloud import vision
from utils import validate_file, upload_to_bucket, get_secret, circuit_breaker

# Inicialización de Flask
app = Flask("internal")
CORS(app, resources={r"/*": {"origins": "*"}})

# Cliente de Vision API
vision_client = vision.ImageAnnotatorClient()

def is_invoice_or_receipt(file):
    """Verifica si el archivo contiene texto relacionado con facturas o recibos."""
    content = file.read()
    file.seek(0)  # Resetear el puntero del archivo después de leerlo
    image = vision.Image(content=content)
    response = vision_client.text_detection(image=image)

    if response.error.message:
        raise RuntimeError(f"Error en Vision API: {response.error.message}")

    # Extraer texto detectado
    text_annotations = response.text_annotations
    if not text_annotations:
        return False

    detected_text = text_annotations[0].description.lower()
    # Verificar palabras clave
    keywords = ["factura", "recibo", "invoice", "receipt"]
    if any(keyword in detected_text for keyword in keywords):
        return True

    return False

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

        filename = upload_to_bucket(file)
        return jsonify({
            "success": True,
            "message": f"Archivo subido y cifrado exitosamente: {filename}",
            "filename": filename
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
        response = jsonify({
            "success": False,
            "error": "Error interno del servidor"
        }), 500
    finally:
        internal_ctx.pop()

    return response

