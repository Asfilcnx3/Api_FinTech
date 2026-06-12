# core/exceptions.py

# ----- Excepciones lógicas ----- (diferentes a los modelos de datos)
# Clase de excepción
class PDFCifradoError(Exception):
    """Excepción personalizada para PDFs protegidos por contraseña."""
    pass