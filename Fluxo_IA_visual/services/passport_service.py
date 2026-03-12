# services/passport_service.py
import json
import os
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta
from ..models.passport import PassportData, DetalleFase, MetricasTecnicas

logger = logging.getLogger(__name__)

class PassportService:
    def __init__(self, passport_dir: str = "downloads/passports"):
        self.passport_dir = Path(passport_dir)
        self.passport_dir.mkdir(parents=True, exist_ok=True)
        self.TTL_SECONDS = 3600 # 1 hora de vida
    
    def _limpiar_archivos_antiguos(self):
        """Limpia pasaportes (JSON) que tengan más de 1 hora de antigüedad."""
        try:
            ahora = time.time()
            contador = 0
            
            # iterdir() recorre el contenido usando la elegancia de pathlib
            for ruta in self.passport_dir.iterdir():
                if ruta.is_file() and ruta.suffix == ".json":
                    tiempo_modificacion = ruta.stat().st_mtime
                    if ahora - tiempo_modificacion > self.TTL_SECONDS:
                        ruta.unlink() # Equivale a os.remove()
                        contador += 1
                        
            if contador > 0:
                logger.info(f"Limpieza de Pasaportes: Se eliminaron {contador} archivos antiguos.")
        except Exception as e:
            logger.warning(f"Error limpiando pasaportes antiguos: {e}")
    
    def _get_path(self, job_id: str) -> str:
        # Convertimos a string para asegurar compatibilidad con open()
        return str(self.passport_dir / f"{job_id}.json")

    def crear_pasaporte(self, job_id: str):
        """Inicializa el archivo JSON en disco."""
        self._limpiar_archivos_antiguos() # Disparamos la limpieza aquí
        
        now = datetime.now()
        passport = PassportData(
            job_id=job_id,
            inicio=now.isoformat(),
            ultima_actualizacion=now.isoformat(),
            eta_estimado="Calculando...",
            detalle=DetalleFase(fase_actual=1, nombre_fase="Inicio", descripcion="Validando archivos..."),
            metricas=MetricasTecnicas()
        )
        self._guardar(passport)
        logger.info(f"[{job_id}] Pasaporte creado exitosamente.")

    def leer_pasaporte(self, job_id: str) -> dict:
        """Lee el JSON del disco. Si no existe, retorna None."""
        path = self._get_path(job_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[{job_id}] Error leyendo pasaporte: {e}")
            return None

    def actualizar(self, job_id: str, 
                    fase: int = None, 
                    nombre_fase: str = None, 
                    descripcion: str = None,
                    estado: str = None,  
                    sumar_paginas_ocr: int = 0,
                    sumar_paginas_digitales: int = 0,
                    sumar_transacciones: int = 0,
                    terminado: bool = False,
                    error: str = None):
        
        path = self._get_path(job_id)
        if not os.path.exists(path):
            logger.warning(f"[{job_id}] Intento de actualizar un pasaporte que no existe o expiró.")
            return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        passport = PassportData(**data)
        now = datetime.now()
        passport.ultima_actualizacion = now.isoformat()

        # 1. Actualizar Estado (Prioridad al argumento explícito)
        if estado: 
            passport.estado = estado
        
        # 2. Actualizar Métricas Acumulativas
        if sumar_paginas_ocr: passport.metricas.paginas_ocr += sumar_paginas_ocr
        if sumar_paginas_digitales: passport.metricas.paginas_digitales += sumar_paginas_digitales
        if sumar_transacciones: passport.metricas.transacciones_detectadas += sumar_transacciones

        # 3. Actualizar Fase y Descripción
        if fase: passport.detalle.fase_actual = fase
        if nombre_fase: passport.detalle.nombre_fase = nombre_fase
        if descripcion: passport.detalle.descripcion = descripcion
        
        if error:
            passport.estado = "ERROR"
            passport.detalle.descripcion = f"Error: {error}"
            self._guardar(passport)
            logger.error(f"[{job_id}] Pasaporte marcado con ERROR: {error}")
            return

        if terminado:
            passport.estado = "TERMINADO"
            passport.progreso_porcentaje = 100.0
            passport.detalle.descripcion = "Proceso finalizado con éxito."
            passport.eta_estimado = "Completado"
            self._guardar(passport)
            logger.info(f"[{job_id}] Pasaporte completado al 100%.")
            return

        # 4. FÓRMULA MATEMÁTICA DINÁMICA
        tiempo_ocr = passport.metricas.paginas_ocr * 1.5      
        tiempo_digital = passport.metricas.paginas_digitales * 0.05 
        tiempo_clasif = passport.metricas.transacciones_detectadas * 0.03 
        tiempo_base_sistema = 5.0 
        
        tiempo_total_estimado = tiempo_base_sistema + tiempo_ocr + tiempo_digital + tiempo_clasif
        passport.metricas.tiempo_estimado_total_seg = round(tiempo_total_estimado, 2)

        # 5. Calcular Porcentaje Real
        start_time = datetime.fromisoformat(passport.inicio)
        elapsed = (now - start_time).total_seconds()
        passport.metricas.tiempo_transcurrido_seg = round(elapsed, 2)

        if tiempo_total_estimado > 0:
            porcentaje_calc = (elapsed / tiempo_total_estimado) * 100
            porcentaje_calc = min(98.0, porcentaje_calc) # Tope en 98%
            passport.progreso_porcentaje = round(porcentaje_calc, 1)
        
        # 6. Calcular ETA
        segundos_restantes = max(0, tiempo_total_estimado - elapsed)
        eta_time = now + timedelta(seconds=segundos_restantes)
        passport.eta_estimado = eta_time.strftime("%H:%M:%S")

        # 7. Logs
        if descripcion:
            passport.logs_recientes.insert(0, f"[{now.strftime('%H:%M:%S')}] {descripcion}")
            passport.logs_recientes = passport.logs_recientes[:5]
            # Imprimimos en terminal un log en nivel DEBUG para no saturar si hay muchas actualizaciones
            logger.debug(f"[{job_id}] Fase {fase if fase else 'N/A'}: {descripcion}")

        self._guardar(passport)

    def _guardar(self, passport: PassportData):
        with open(self._get_path(passport.job_id), "w", encoding="utf-8") as f:
            f.write(passport.model_dump_json(indent=2))