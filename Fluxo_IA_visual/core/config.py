import logging
from enum import Enum
from typing import List

from dotenv import load_dotenv
from pydantic import field_validator, ValidationError, SecretStr
from pydantic_settings import BaseSettings

# Carga las variables de entorno desde un archivo .env si existe
load_dotenv()
logger = logging.getLogger(__name__)

class Environment(str, Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"

class Settings(BaseSettings):
    """
    Clase para gestionar la configuración de la aplicación
    Valida la presencia y formato de valirables crítivas al momento de la inicialización.
    """
    # --- Configuración del Entorno ---
    ENVIRONMENT: Environment = Environment.DEVELOPMENT

    # API Settings -- Configuración General
    API_V1_STR: str = "/api/v1"
    APP_VERSION: str = "1.0.0"
    PROJECT_NAME: str = "EXTRACCIÓN DE TEXTO DE PDF's CON IA"
    DEV_NAME: str = "Abraham from KiaB"
    
    # Lista de origenes permitidos para CORS
    # Pydantic-settings convierte automáticamente un string JSON en una lista de Python.
    # Ejemplo en .env: BACKEND_CORS_ORIGINS='["http://localhost:3000", "https://el-frontend.com"]'
    BACKEND_CORS_ORIGINS: List[str] = ["*"]  # Por defecto permite todo para desarrollo

    # OpenAI Settings Fluxo
    OPENAI_API_KEY_FLUXO: SecretStr # es obligatoria para que el servicio funcione
    FLUXO_MODEL: str = "gpt-5"

    # Configuración Syntage
    SYNTAGE_API_URL:str = "https://api.sandbox.syntage.com"
    SYNTAGE_API_KEY: SecretStr # es obligatoria para que el servicio funcione

    # OpenAI Settings Nomi
    OPENAI_API_KEY_NOMI: SecretStr # es obligatoria para que el servicio funcione
    NOMI_MODEL: str = "gpt-5"

    # OpenRouter Settings
    OPENROUTER_API_KEY: SecretStr
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    ## Development settings
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    # File Upload Settings
    MAX_FILE_SIZE_MB: int = 10
    UPLOAD_DIR: str = "uploads"
    ALLOWED_EXTENSION: List[str] = [".pdf"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True

    @field_validator("OPENAI_API_KEY_FLUXO")
    @classmethod
    def validate_fluxo_api_key(cls, secret: str) -> SecretStr:
        """
        Valida que la clave de OpenAI no esté vacía y tenga un formato plausible.
        """
        v = secret.get_secret_value()
        if not v:
            raise ValueError("La variable de entorno OPENAI_API_KEY_FLUXO no puede estar vacía.")
        if not v.startswith("sk-"):
            raise ValueError("OPENAI_API_KEY_FLUXO no comienza con 'sk-'. Podría ser inválida.")
        return secret
    
    @field_validator("OPENAI_API_KEY_NOMI")
    @classmethod
    def validate_nomi_api_key(cls, secret: str) -> SecretStr:
        """
        Valida que la clave de OpenAI no esté vacía y tenga un formato plausible.
        """
        v = secret.get_secret_value()
        if not v:
            raise ValueError("La variable de entorno OPENAI_API_KEY_NOMI no puede estar vacía.")
        if not v.startswith("sk-"):
            raise ValueError("OPENAI_API_KEY_NOMI no comienza con 'sk-'. Podría ser inválida.")
        return secret
    
    @field_validator("OPENROUTER_API_KEY")
    @classmethod
    def validate_openrouter_api_key(cls, secret: str) -> SecretStr:
        """
        Valida que la clave de OpenAI no esté vacía y tenga un formato plausible.
        """
        v = secret.get_secret_value()
        if not v:
            raise ValueError("La variable de entorno OPENROUTER_API_KEY no puede estar vacía.")
        if not v.startswith("sk-"):
            raise ValueError("OPENROUTER_API_KEY no comienza con 'sk-'. Podría ser inválida.")
        return secret


    @field_validator("SYNTAGE_API_KEY")
    @classmethod
    def validate_syntage_api_key(cls, secret: str) -> SecretStr:
        """
        Valida que la clave de Syntage no esté vacía y tenga un formato plausible.
        """
        v = secret.get_secret_value()
        if not v:
            raise ValueError("La variable de entorno SYNTAGE_API_KEY no puede estar vacía.")
        return secret   
    
# INICIALIZACIÓN SEGURA 
# Se envuelve la creación de la instancia en un bloque try/except para
# capturar errores de validación y terminar la aplicación de forma controlada.
try:
    settings = Settings()
    logger.info(f"Configuración cargada exitosamente para el entorno: {settings.ENVIRONMENT.value}")
    # En producción, se recomienda usar un gestor de secretos (ej. AWS Secrets Manager, HashiCorp Vault) en lugar de archivos .env para manejar claves de API 
    # y otras credenciales sensibles. La validación de Pydantic seguirá siendo útil.
except ValidationError as e:
    # Si falta una variable crítica o tiene un formato incorrecto, el programa no se iniciará y mostrará un error claro.
    logger.critical(f"Error fatal: Faltan configuraciones críticas o son inválidas. No se puede iniciar la aplicación.")
    logger.critical(e)
    # Termina el proceso si la configuración es inválida.
    exit(1)