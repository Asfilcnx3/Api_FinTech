from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends, BackgroundTasks
from typing import List, Optional
import logging
import uuid

# --- Modelos ---
from ...models.responses_frontend import RespuestaProcesamientoIniciado, RespuestaEstadoTrabajo

# --- Core y Configuraciones ---
from ...core.motor_caratulas import MotorCaratulas 
from ...core.config import Settings
from ...utils.helpers_texto_fluxo import (
    TRIGGERS_CONFIG, BANCO_DETECTION_REGEX, PATRONES_COMPILADOS, PALABRAS_CLAVE_VERIFICACION, ALIAS_A_BANCO_MAP
)

# --- Servicios ---
from ...services.file_manager import FileManagerService 
from ...services.storage_service import StorageService
from ...services.caratulas_light_service import CaratulasLightService
from ...services.webhook_service import WebhookService
from ...services.webhook_general_orchestrator import OrquestadorWebhooks

logger = logging.getLogger(__name__)
router = APIRouter()

# =================================================================
# INSTANCIAS GLOBALES E INYECTORES
# =================================================================
motor_global = MotorCaratulas(
    triggers_config=TRIGGERS_CONFIG,
    palabras_clave_regex=PALABRAS_CLAVE_VERIFICACION,
    alias_banco_map=ALIAS_A_BANCO_MAP,
    banco_detection_regex=BANCO_DETECTION_REGEX,
    patrones_compilados=PATRONES_COMPILADOS,
    debug_flags=None
)

def get_settings() -> Settings: return Settings()
def get_motor() -> MotorCaratulas: return motor_global
def get_file_manager() -> FileManagerService: return FileManagerService()
def get_storage() -> StorageService: return StorageService()
def get_webhook_service() -> WebhookService: return WebhookService()

def get_caratulas_light_service(
    settings: Settings = Depends(get_settings),
    motor_base: MotorCaratulas = Depends(get_motor),
    file_manager: FileManagerService = Depends(get_file_manager),
    storage: StorageService = Depends(get_storage)
) -> CaratulasLightService:
    return CaratulasLightService(settings, motor_base, file_manager, storage)

# INYECTOR DEL ORQUESTADOR UNIVERSAL
def get_orquestador_general(
    storage: StorageService = Depends(get_storage),
    webhook_service: WebhookService = Depends(get_webhook_service)
) -> OrquestadorWebhooks:
    return OrquestadorWebhooks(storage, webhook_service)

# =================================================================
# ENDPOINTS
# =================================================================
@router.post("/extraer", response_model=RespuestaProcesamientoIniciado, status_code=status.HTTP_202_ACCEPTED)
async def extraer_datos_fluxo(
    background_tasks: BackgroundTasks,
    archivos: List[UploadFile] = File(..., description="Archivos PDF o ZIP"),
    webhook_url: Optional[str] = Form(None, description="URL para notificar al terminar"),
    file_manager: FileManagerService = Depends(get_file_manager),
    storage: StorageService = Depends(get_storage),
    caratulas_service: CaratulasLightService = Depends(get_caratulas_light_service),
    orquestador: OrquestadorWebhooks = Depends(get_orquestador_general) # <--- INYECTAMOS
):
    """
    Endpoint lazy: Recibe archivos, los guarda temporalmente y delega 
    el trabajo pesado al orquestador en background.
    """
    job_id = str(uuid.uuid4())
    lista_archivos_trabajo = []
    
    # 1. Guardar y descomprimir (Streaming a Disco)
    try:
        for archivo in archivos:
            resultado = file_manager.procesar_entrada(archivo)
            lista_archivos_trabajo.extend(resultado)
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error en carga de archivos: {e}")
        raise HTTPException(status_code=500, detail="Error procesando la subida de archivos.")

    if not lista_archivos_trabajo:
        raise HTTPException(status_code=400, detail="No se encontraron archivos PDF válidos en la subida.")

    # 2. Registrar el inicio del trabajo en disco
    storage.update_job(job_id, {
        "estatus": "procesando",
        "mensaje": "Iniciando lectura de archivos en paralelo..."
    })

    # 3. DELEGAMOS AL ORQUESTADOR GENERAL
    background_tasks.add_task(
        orquestador.ejecutar_y_notificar,
        caratulas_service.ejecutar_pipeline_concurrente, # 1. La función específica de carátulas
        job_id,                                          # 2. El Job ID
        webhook_url,                                     # 3. El webhook
        lista_archivos_trabajo                           # 4. Los argumentos (lista de archivos)
    )

    # 4. Responder de inmediato al cliente
    return RespuestaProcesamientoIniciado(
        mensaje="Procesamiento en segundo plano iniciado. Usa el job_id para consultar el estatus o espera el webhook.",
        job_id=job_id,
        estatus="procesando"
    )

@router.get("/resultado/{job_id}", response_model=RespuestaEstadoTrabajo, status_code=status.HTTP_200_OK)
async def consultar_resultado(
    job_id: str,
    storage: StorageService = Depends(get_storage)
):
    """
    Endpoint (Polling) para que el frontend consulte el estatus de su trabajo.
    """
    job_info = storage.obtener_datos_json(job_id)
    
    if not job_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Job ID no encontrado o el resultado ya expiró (superó 1 hora)."
        )
        
    estatus_actual = job_info.get("estatus")
    
    # Caso 1: Aún está procesando
    if estatus_actual == "procesando":
        return RespuestaEstadoTrabajo(
            job_id=job_id, 
            estatus="procesando", 
            mensaje="Los documentos siguen procesándose en paralelo. Por favor, intenta de nuevo en unos segundos."
        )
        
    # Caso 2: Terminó (con éxito o error)
    return RespuestaEstadoTrabajo(
        job_id=job_id,
        estatus=estatus_actual,
        indicador_caratulas_recientes=job_info.get("indicador_caratulas_recientes"),
        resultados_exitosos=job_info.get("resultados_exitosos", []),
        errores=job_info.get("errores", []),
        detalle_error=job_info.get("detalle_error")
    )