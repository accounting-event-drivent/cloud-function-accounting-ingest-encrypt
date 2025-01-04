from google.cloud import vision

# Inicialización del cliente de Vision API
vision_client = vision.ImageAnnotatorClient()

def is_invoice_or_receipt(file):
    """Verifica si el archivo contiene texto relacionado con facturas o recibos."""
    # Leer contenido del archivo
    content = file.read()
    file.seek(0)  # Restablecer el puntero del archivo después de leerlo

    # Crear una instancia de imagen
    image = vision.Image(content=content)

    # Hacer una solicitud a la API de Vision
    response = vision_client.text_detection(image=image)

    # Manejar posibles errores
    if response.error.message:
        raise RuntimeError(f"Error en Vision API: {response.error.message}")

    # Extraer texto detectado
    text_annotations = response.text_annotations
    if not text_annotations:
        return False

    detected_text = text_annotations[0].description.lower()

    # Palabras clave relacionadas con facturas o recibos
    keywords = ["factura", "recibo", "invoice", "receipt"]
    return any(keyword in detected_text for keyword in keywords)
