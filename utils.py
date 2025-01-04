from cryptography.fernet import Fernet
import os
from google.cloud import storage, secretmanager
from tenacity import retry, stop_after_attempt, wait_fixed

# Validación de configuración
REQUIRED_ENV_VARS = {"BUCKET_NAME", "KEY_NAME", "PROJECT_ID"}
missing_vars = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
if missing_vars:
    raise EnvironmentError(
        f"Faltan variables de entorno necesarias: {', '.join(missing_vars)}"
    )

# Variables de entorno opcionales con valores predeterminados
BUCKET_NAME         = os.getenv("BUCKET_NAME")
BUCKET_FOLDER_NAME  = os.getenv("BUCKET_FOLDER_NAME", "ingesta")
KEY_NAME            = os.getenv("KEY_NAME", "accounting-client-key")
SECRET_VERSION      = os.getenv("SECRET_VERSION", "latest")
PROJECT_ID          = os.getenv("PROJECT_ID")
ALLOWED_EXTENSIONS  = {"png", "jpg", "jpeg"}
MAX_FILE_SIZE       = 5 * 1024 * 1024  

# Clientes de Google Cloud
storage_client = storage.Client()
secret_manager_client = secretmanager.SecretManagerServiceClient()

# Obtener secretos
def get_secret():
    """Obtiene la clave de cifrado desde Secret Manager."""
    secret_path = f"projects/{PROJECT_ID}/secrets/{KEY_NAME}/versions/{SECRET_VERSION}"
    secret_response = secret_manager_client.access_secret_version(name=secret_path)
    return secret_response.payload.data.decode("UTF-8")

# Validación de archivos
def is_allowed_file(filename):
    """Verifica que el archivo tenga una extensión permitida."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_file(file):
    """Valida que el archivo sea permitido por tamaño y extensión."""
    if not file or not file.filename:
        raise ValueError("No se encontró el archivo o el archivo no tiene nombre.")
    if not is_allowed_file(file.filename):
        raise ValueError("Extensión de archivo no permitida.")
    if len(file.read()) > MAX_FILE_SIZE:
        raise ValueError("El archivo excede el tamaño máximo permitido.")
    file.seek(0)  # Resetear el puntero del archivo

# Encriptar archivo
def encrypt_file(file):
    """Cifra los datos del archivo usando la clave de Secret Manager."""
    secret_key = get_secret()
    fernet = Fernet(secret_key)
    encrypted_data = fernet.encrypt(file.read())
    file.seek(0)  # Resetear el puntero del archivo
    return encrypted_data

# Subida de archivos encriptados
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def upload_to_bucket(file):
    """Encripta y sube un archivo al bucket de Google Cloud Storage."""
    bucket = storage_client.bucket(BUCKET_NAME)
    blob_name = f"{BUCKET_FOLDER_NAME}/{file.filename}"
    blob = bucket.blob(blob_name)

    # Encriptar el archivo antes de subir
    encrypted_data = encrypt_file(file)
    blob.upload_from_string(encrypted_data)
    return blob_name

# Circuit Breaker
def circuit_breaker(func):
    """Circuit breaker para manejar fallos repetidos en funciones."""
    failures = 0
    MAX_FAILURES = 3

    def wrapper(*args, **kwargs):
        nonlocal failures
        if failures >= MAX_FAILURES:
            raise RuntimeError("Circuit breaker activado. Intenta más tarde.")
        try:
            result = func(*args, **kwargs)
            failures = 0
            return result
        except Exception as e:
            failures += 1
            raise RuntimeError(f"Error en la función: {str(e)}")
    return wrapper
