from .core.config import settings
from .api.endpoints import router_fluxo, router_csf, router_nomi, router_precalificacion

import sys
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Configuramos el logging con un formato estructurado
LOGGING_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

logging.basicConfig(
    level = logging.INFO, # logging.DEBUG if settings.DEBUG else logging.INFO, # Solo aparecen las partes debug si estamos en modo debug
    format = LOGGING_FORMAT,
    handlers = [logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- Ciclo de Vida de la Aplicación (Lifespan) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Maneja los eventos de inicio y apagado de la aplicación."""
    # Código de inicio
    logger.info(f"Iniciando {settings.PROJECT_NAME} v{settings.APP_VERSION}")
    logger.info(f"Modo Debug: {settings.DEBUG}")
    logger.info(f"Creado por: {settings.DEV_NAME}")
        
    yield
    # Código de apagado
    logger.info("Cerrando la aplicación.")

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.APP_VERSION,
    description="API para la extracción de Texto (Entradas TPV) dentro de PDF's, mediante un flujo de trabajo.",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
) 

# Configurar CORS (Cross-Origin Resource Sharing)
# Es importante restringir los origines en un entorno de prooducción para mayor seguridad
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS if settings.ENVIRONMENT == "production" else ["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

# --- Inclusión de Rutas ---
app.include_router( # Ruta NomiFlash
    router_nomi.router,
    prefix=f"{settings.API_V1_STR}/NomiFlash",
    tags=["Extracción de NomiFlash"]
)

app.include_router( # Ruta CSF
    router_csf.router,
    prefix=f"{settings.API_V1_STR}/CSF",
    tags=["Extracción de Constancias"]
)

app.include_router( # Ruta Fluxo
    router_fluxo.router,
    prefix=f"{settings.API_V1_STR}/Fluxo",
    tags=["Extracción de Fluxo"]
)

app.include_router( # Ruta Pre-calificación
    router_precalificacion.router,
    prefix=f"{settings.API_V1_STR}/PreCalificacion",
    tags=["Pre-calificación RFC"]
)
    
# Endpoint Raíz
@app.get("/", tags=["General"])
async def home():
    """Endpoint Raiz que devuelve información Básica de la API y la URL de la documentación"""
    return {
        "Bienvenida": f"Hola! Esta API está hecha por {settings.DEV_NAME}",
        "message": "Hola, te equivocaste al momento de consumir la API, pero no te preocupes. Te comparto los enlaces de interés.",
        "version": settings.APP_VERSION,
        "docs_url": app.docs_url,
        "health_url" : ""
    }

# Endpoint de información
@app.get("/info", tags=["General"])
async def info():
    """Endpoint raíz con información detallada de la API."""
    return {
        "app_name": settings.PROJECT_NAME,
        "version": settings.APP_VERSION,
        "debug_mode": settings.DEBUG,
        "api_version": settings.API_V1_STR,
        "limits": {
            "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
            "allowed_extensions": settings.ALLOWED_EXTENSION
        },
        "ai_config_fluxo": {
            "model": settings.FLUXO_MODEL
        },
        "ai_config_nomiflash": {
            "model": settings.NOMI_MODEL
        },
        "endpoints": {
            "csf": f"{settings.API_V1_STR}/CSF",
            "fluxo": f"{settings.API_V1_STR}/Fluxo",
            "nomiflash": f"{settings.API_V1_STR}/NomiFlash",
            "precalificacion": f"{settings.API_V1_STR}/PreCalificacion"
        }
    }