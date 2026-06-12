# main.py

from .core.config import settings
from .api.endpoints import router_fluxo, router_csf, router_nomi, router_precalificacion, router_front

import sys
from concurrent.futures import ProcessPoolExecutor
import os
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
    # Determinamos un número seguro de workers (ej. total de cores físicos menos 1)
    max_workers = max(1, os.cpu_count() - 1)
    app.state.process_pool = ProcessPoolExecutor(max_workers=max_workers)
    
    logger.info(f"Iniciando {settings.PROJECT_NAME} v{settings.APP_VERSION}")
    logger.info(f"Pool global de procesos iniciado con {max_workers} workers.")
    logger.info(f"Modo Debug: {settings.DEBUG}")
    logger.info(f"Creado por: {settings.DEV_NAME}")
        
    yield
    
    # Código de apagado: liberamos la RAM y cerramos procesos
    app.state.process_pool.shutdown(wait=True)
    logger.info("Cerrando la aplicación y limpiando el pool de procesos.")

# Definimos los tags visuales para Swagger
tags_metadata = [
    {
        "name": "Extracción de Fluxo",
        "description": "Análisis profundo de transacciones TPV y estados de cuenta usando motores espaciales y OCR.",
    },
    {
        "name": "Extracción de NomiFlash",
        "description": "Procesamiento y extracción de datos de recibos de nómina.",
    },
    {
        "name": "General",
        "description": "Endpoints de estado, métricas e información del sistema.",
    }
]

# Descripción en Markdown para la cabecera de /docs
description_md = """
Esta API orquesta un flujo de trabajo avanzado para la extracción y clasificación de texto dentro de documentos financieros.

## Características Principales
* **Resiliencia:** Mitigación de Zip Bombs y ataques de Path Traversal.
* **Escalabilidad:** Procesamiento asíncrono con control de memoria para archivos de gran volumen.
* **Inteligencia:** Motores híbridos (Determinista + Modelos Multimodales) para clasificación de transacciones.
* **Flexibilidad:** Orquestador agnóstico que puede ejecutar cualquier pipeline y notificar resultados vía Webhooks.
"""

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title=f"{settings.PROJECT_NAME} API",
    version=settings.APP_VERSION,
    description=description_md,
    openapi_tags=tags_metadata,
    contact={
        "name": settings.DEV_NAME
    },
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

app.include_router( # Ruta FrontEnd (Solo para la extracción ligera de carátulas)
    router_front.router,
    prefix=f"{settings.API_V1_STR}/ExtraccionCaratulaLigera",
    tags=["Extracción de Carátulas Ligeras"]
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