import asyncio
import logging
from pathlib import Path

# Ajusta las rutas relativas según la ubicación exacta de tu carpeta services
from ..core.motor_caratulas_light import procesar_caratula_frontend
from ..core.motor_caratulas import MotorCaratulas
from ..core.config import Settings
from .file_manager import FileManagerService
from .storage_service import StorageService

logger = logging.getLogger(__name__)

class CaratulasLightService:
    """
    Servicio encargado de orquestar la extracción concurrente de carátulas ligeras.
    Mantiene el router limpio delegando aquí la lógica de negocio pesada.
    """
    def __init__(
        self,
        settings: Settings,
        motor_base: MotorCaratulas,
        file_manager: FileManagerService,
        storage: StorageService
    ):
        self.settings = settings
        self.motor_base = motor_base
        self.file_manager = file_manager
        self.storage = storage

    async def _procesar_archivo_individual(self, info_archivo: dict, semaforo: asyncio.Semaphore) -> dict:
        """Método privado: Procesa un solo archivo respetando el límite del semáforo."""
        async with semaforo:
            ruta_pdf = Path(info_archivo["path"])
            nombre_original = info_archivo["filename"]
            
            try:
                # A. Validar límite de peso
                tamanio_archivo = ruta_pdf.stat().st_size
                if tamanio_archivo > self.settings.max_file_size_bytes:
                    return {"error": f"{nombre_original}: Supera límite de {self.settings.MAX_FILE_SIZE_MB}MB."}

                # B. Leer de disco y validar Magic Bytes
                with open(ruta_pdf, "rb") as f:
                    magic_bytes = f.read(5)
                    if magic_bytes != b"%PDF-":
                        return {"error": f"{nombre_original}: Firma de archivo inválida (no es PDF)."}
                    
                    f.seek(0)
                    pdf_bytes = f.read()

                # C. Extracción real con el motor ligero
                res_estructurada = await procesar_caratula_frontend(
                    pdf_bytes=pdf_bytes, 
                    motor_base=self.motor_base
                )

                # D. Evaluar resultado
                if res_estructurada.error_procesamiento:
                    return {"error": f"{nombre_original}: {res_estructurada.error_procesamiento}"}
                
                # Convertimos el modelo Pydantic a diccionario para JSON
                resultados_dict = [item.model_dump() for item in res_estructurada.resultados]
                return {"exito": resultados_dict}
                
            except Exception as e:
                logger.error(f"Error procesando {nombre_original}: {str(e)}")
                return {"error": f"{nombre_original}: Error interno al extraer - {str(e)}"}

    async def ejecutar_pipeline_concurrente(self, job_id: str, lista_archivos: list):
        """Orquestador background: Dispara N archivos a la vez, guardando estado en disco (JSON)."""
        try:
            self.storage.update_job(job_id, {
                "estatus": "procesando", 
                "resultados_exitosos": [], 
                "errores": []
            })
            
            semaforo = asyncio.Semaphore(15)
            
            tareas = [
                self._procesar_archivo_individual(info, semaforo)
                for info in lista_archivos
            ]
            
            resultados_brutos = await asyncio.gather(*tareas)
            
            exitos = []
            errores = []
            
            for res in resultados_brutos:
                if "error" in res:
                    errores.append(res["error"])
                elif "exito" in res:
                    exitos.extend(res["exito"])
                    
            self.storage.update_job(job_id, {
                "estatus": "completado",
                "resultados_exitosos": exitos,
                "errores": errores
            })
            logger.info(f"Job {job_id} completado. {len(exitos)} éxitos, {len(errores)} errores.")

        except Exception as e:
            logger.error(f"Falla fatal en Job {job_id}: {e}")
            self.storage.update_job(job_id, {"estatus": "error", "detalle_error": str(e)})

        finally:
            rutas_a_borrar = [Path(info["path"]) for info in lista_archivos]
            self.file_manager.limpiar_temporales(rutas_a_borrar)