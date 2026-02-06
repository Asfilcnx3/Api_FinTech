import os
import json
import logging
import uuid
import time

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self):
        self.DOWNLOADS_DIR = "downloads"
        os.makedirs(self.DOWNLOADS_DIR, exist_ok=True)
        self.TTL_SECONDS = 3600 # 1 Hora

    def _limpiar_archivos_antiguos(self):
        """Borra archivos viejos."""
        try:
            ahora = time.time()
            archivos = os.listdir(self.DOWNLOADS_DIR)
            for archivo in archivos:
                ruta = os.path.join(self.DOWNLOADS_DIR, archivo)
                if os.path.isfile(ruta):
                    if ahora - os.path.getmtime(ruta) > self.TTL_SECONDS:
                        os.remove(ruta)
        except Exception as e:
            logger.warning(f"Error limpieza storage: {e}")

    def save_json_result(self, data: dict) -> str:
        """Guarda el JSON y retorna un JOB ID único."""
        self._limpiar_archivos_antiguos()
        job_id = str(uuid.uuid4())
        filename = f"syntage_{job_id}.json"
        filepath = os.path.join(self.DOWNLOADS_DIR, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        
        return job_id

    def get_json_result(self, job_id: str) -> dict | None:
        """Recupera el JSON por Job ID."""
        filename = f"syntage_{job_id}.json"
        filepath = os.path.join(self.DOWNLOADS_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return None