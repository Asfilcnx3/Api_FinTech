# Fluxo_IA_visual/services/storage_service.py
import os
import json
import logging
import uuid
import time
from typing import Optional

logger = logging.getLogger(__name__)

class StorageService:
    """
    Servicio encargado de gestionar el almacenamiento temporal en disco 
    de los resultados JSON y archivos Excel generados.
    """
    def __init__(self):
        self.DOWNLOADS_DIR = "downloads"
        os.makedirs(self.DOWNLOADS_DIR, exist_ok=True)
        self.TTL_SECONDS = 3600 # 1 Hora de vida para los archivos

    def _limpiar_archivos_antiguos(self):
        """
        Recorre la carpeta de descargas y elimina archivos que superen el tiempo de vida.
        Se ejecuta de manera silenciosa de forma interna.
        """
        try:
            ahora = time.time()
            archivos = os.listdir(self.DOWNLOADS_DIR)
            contador_borrados = 0

            for archivo in archivos:
                ruta_completa = os.path.join(self.DOWNLOADS_DIR, archivo)
                if os.path.isfile(ruta_completa):
                    tiempo_modificacion = os.path.getmtime(ruta_completa)
                    if ahora - tiempo_modificacion > self.TTL_SECONDS:
                        os.remove(ruta_completa)
                        contador_borrados += 1

            if contador_borrados > 0:
                    logger.info(f"Limpieza automática: Se eliminaron {contador_borrados} archivos antiguos.")
        except Exception as e:
            logger.warning(f"Error menor durante la limpieza de archivos antiguos: {e}")

    # =========================================================
    # MÉTODOS FLUXO
    # =========================================================

    def guardar_json_local(self, datos: dict, job_id: str):
        """Guarda el objeto de respuesta completo en JSON."""
        self._limpiar_archivos_antiguos()
        filename = f"data_{job_id}.json"
        filepath = os.path.join(self.DOWNLOADS_DIR, filename)
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=4)
            logger.info(f"JSON guardado localmente: {filepath}")
        except Exception as e:
            logger.error(f"Error guardando JSON local: {e}")

    def obtener_datos_json(self, job_id: str) -> Optional[dict]:
        """Lee el JSON del disco y lo devuelve como diccionario."""
        filename = f"data_{job_id}.json"
        filepath = os.path.join(self.DOWNLOADS_DIR, filename)
        
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error leyendo JSON: {e}")
                return None
        return None

    def guardar_excel_local(self, contenido_bytes: bytes, job_id: str) -> Optional[str]:
        """Guarda el archivo Excel en disco local (Modo Binario)."""
        self._limpiar_archivos_antiguos()
        filename = f"reporte_{job_id}.xlsx"
        filepath = os.path.join(self.DOWNLOADS_DIR, filename)
        
        try:
            with open(filepath, "wb") as f: 
                f.write(contenido_bytes)
            logger.info(f"Excel guardado localmente: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Error guardando Excel local: {e}")
            return None

    def obtener_ruta_archivo(self, job_id: str) -> Optional[str]:
        """Busca el archivo .xlsx"""
        filename = f"reporte_{job_id}.xlsx"
        filepath = os.path.join(self.DOWNLOADS_DIR, filename)
        
        if os.path.exists(filepath):
            return filepath
        return None

    # =========================================================
    # MÉTODOS DE ESTADO 
    # =========================================================

    def create_pending_job(self, rfc: str) -> str:
        """Crea un archivo temporal indicando que el proceso inició."""
        self._limpiar_archivos_antiguos()
        job_id = str(uuid.uuid4())
        filepath = os.path.join(self.DOWNLOADS_DIR, f"data_{job_id}.json")
        
        initial_data = {"status": "processing", "rfc": rfc}
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(initial_data, f, ensure_ascii=False)
            
        return job_id

    def update_job(self, job_id: str, data: dict):
        """Sobrescribe el archivo temporal con los datos finales (o error)."""
        filepath = os.path.join(self.DOWNLOADS_DIR, f"data_{job_id}.json")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Error actualizando Job {job_id}: {e}")