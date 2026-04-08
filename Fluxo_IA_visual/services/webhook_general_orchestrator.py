import logging
import inspect
from typing import Optional, Callable, Any
from fastapi.concurrency import run_in_threadpool

from .storage_service import StorageService
from .webhook_service import WebhookService

logger = logging.getLogger(__name__)

class OrquestadorWebhooks:
    """
    Orquestador agnóstico. Ejecuta cualquier pipeline de procesamiento 
    y dispara un webhook si se solicita.
    """
    def __init__(self, storage: StorageService, webhook_service: WebhookService):
        self.storage = storage
        self.webhook_service = webhook_service

    async def ejecutar_y_notificar(
        self, 
        funcion_pipeline: Callable,  # <--- Recibe LA FUNCIÓN que debe ejecutar
        job_id: str, 
        webhook_url: Optional[str],
        *args,  # <--- Recibe cualquier parámetro extra que necesite tu función (ej. lista_archivos)
        **kwargs
    ):
        try:
            # 1. Ejecutar la lógica de negocio sin importar si es async o sync
            if inspect.iscoroutinefunction(funcion_pipeline):
                await funcion_pipeline(job_id, *args, **kwargs)
            else:
                await run_in_threadpool(funcion_pipeline, job_id, *args, **kwargs)
                
        except Exception as e:
            logger.error(f"Error crítico en background job {job_id}: {e}")
            self.storage.update_job(job_id, {"estatus": "error", "detalle_error": str(e)})

        # 2. Rescatar el estado final del storage (Asumimos que siempre se guarda en JSON)
        resultado_final = self.storage.obtener_datos_json(job_id)
        
        # 3. Disparar el Webhook (Solo si hay URL y hay un resultado válido)
        if webhook_url and resultado_final:
            resultado_final["job_id"] = job_id
            await self.webhook_service.notificar(webhook_url, resultado_final)