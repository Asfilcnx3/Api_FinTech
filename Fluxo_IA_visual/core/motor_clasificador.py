import logging
import json
import asyncio
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class MotorClasificador:
    """
    Motor centralizado para la clasificación de transacciones bancarias.
    Aplica filtros deterministas de primera capa y delega la ambigüedad a modelos LLM.
    """
    def __init__(self, diccionarios_palabras: dict, debug_flags: list = None):
        """
        Inicializa el motor inyectando los diccionarios de palabras clave.
        """
        self.diccionarios = diccionarios_palabras
        # Banderas de debug:
        # 1 = Filtro de Cargos | 2 = Reglas de Texto | 3 = Payload IA | 4 = Sumatorias Totales
        self.debug_flags = debug_flags if debug_flags is not None else []

    def _log_debug(self, flag: int, mensaje: str):
        """Helper para imprimir logs granulares según la bandera activa."""
        if flag in self.debug_flags:
            etiquetas = {
                1: "[CARGOS] ", 
                2: "[REGLAS] ", 
                3: "[IA_LOTE]", 
                4: "[TOTALES]"
            }
            prefijo = etiquetas.get(flag, "[DEBUG]  ")
            logger.info(f"  {prefijo} {mensaje}")

    def _pre_clasificar_transacciones(self, transacciones: List[Any]) -> tuple:
        """
        Actúa como la Capa 1 del embudo. 
        Separa las transacciones en dos cubetas: las que Python puede resolver gratis
        y las que obligatoriamente necesitan análisis semántico de la IA.
        """
        resueltas_por_python = []
        pendientes_para_ia = []

        # Para mantener el orden original, guardamos el índice real de la transacción
        for idx_real, tx in enumerate(transacciones):
            
            # --- NORMALIZACIÓN BÁSICA ---
            tipo_lower = str(getattr(tx, "tipo", "")).lower().strip()
            desc_lower = str(getattr(tx, "descripcion", "")).lower()

            # --- REGLA 1: DESCARTE DE CARGOS ---
            if tipo_lower not in ["abono", "deposito", "depósito", "credito", "crédito"]:
                tx.categoria = "GENERAL"
                resueltas_por_python.append((idx_real, tx))
                self._log_debug(1, f"Tx {idx_real} descartada (Es cargo) -> {desc_lower[:40]}...")
                continue

            # --- REGLA 2: PALABRAS CLAVE EXACTAS (Solo para Abonos) ---
            clasificado_estatico = False
            
            if any(p in desc_lower for p in self.diccionarios.get('excluidas', [])):
                tx.categoria = "GENERAL"
                clasificado_estatico = True
            elif any(p in desc_lower for p in self.diccionarios.get('efectivo', [])):
                tx.categoria = "EFECTIVO"
                clasificado_estatico = True
            elif any(p in desc_lower for p in self.diccionarios.get('traspaso', [])):
                tx.categoria = "TRASPASO"
                clasificado_estatico = True
            elif any(p in desc_lower for p in self.diccionarios.get('financiamiento', [])):
                tx.categoria = "FINANCIAMIENTO"
                clasificado_estatico = True
            elif any(p in desc_lower for p in self.diccionarios.get('bmrcash', [])):
                tx.categoria = "BMRCASH"
                clasificado_estatico = True
            elif any(p in desc_lower for p in self.diccionarios.get('moratorio', [])):
                tx.categoria = "MORATORIOS"
                clasificado_estatico = True

            # --- REPARTO A LAS CUBETAS ---
            if clasificado_estatico:
                resueltas_por_python.append((idx_real, tx))
                self._log_debug(2, f"Tx {idx_real} clasificada como {tx.categoria} por regla -> {desc_lower[:40]}...")
            else:
                # Si es un abono y Python no sabe qué es, la IA debe decidir si es TPV o GENERAL
                pendientes_para_ia.append((idx_real, tx))

        self._log_debug(2, f"Pre-clasificación lista: {len(resueltas_por_python)} resueltas estáticamente, {len(pendientes_para_ia)} enviadas a IA.")
        return resueltas_por_python, pendientes_para_ia
    
    async def clasificar_y_sumar_transacciones(
        self, 
        transacciones: List[Any], 
        banco: str, 
        funcion_ia_clasificadora, 
        batch_size: int = 100
    ) -> dict:
        """
        El orquestador maestro del clasificador.
        1. Filtra estáticamente.
        2. Envía lotes pequeños a la IA.
        3. Ensambla y calcula totales.
        """
        if not transacciones:
            return {}

        self._log_debug(4, f"Iniciando clasificación de {len(transacciones)} transacciones para banco: {banco}")

        # --- CAPA 1: FILTRO DETERMINISTA (Python) ---
        resueltas, pendientes_ia = self._pre_clasificar_transacciones(transacciones)

        # --- CAPA 2: ANÁLISIS SEMÁNTICO (IA) ---
        mapa_ia = await self._procesar_lotes_ia(
            pendientes=pendientes_ia, 
            banco=banco, 
            funcion_ia_clasificadora=funcion_ia_clasificadora, 
            batch_size=batch_size
        )

        # --- CAPA 3: ENSAMBLAJE ---
        # Recorremos SOLO las que mandamos a la IA y les inyectamos la respuesta
        for idx_real, tx in pendientes_ia:
            str_idx = str(idx_real)
            nueva_cat = mapa_ia.get(str_idx)
            
            if nueva_cat:
                tx.categoria = nueva_cat
                self._log_debug(3, f"Tx {idx_real} clasificada por IA como -> {nueva_cat}")
            else:
                # Fallback de seguridad si la IA se saltó este índice
                tx.categoria = "GENERAL"
                self._log_debug(3, f"⚠️ Tx {idx_real} sin etiqueta IA -> GENERAL (Fallback)")

        # --- CAPA 4: SUMATORIAS FINALES ---
        # Ahora que TODAS las transacciones tienen su categoría final, sumamos.
        totales_calculados = self._calcular_totales(transacciones)
        
        return totales_calculados

    async def _procesar_lotes_ia(
        self, 
        pendientes: List[tuple], 
        banco: str, 
        funcion_ia_clasificadora, 
        batch_size: int
    ) -> dict:
        """
        Divide las transacciones ambiguas en lotes, llama a la IA concurrentemente
        y ensambla un diccionario absoluto de { "id_real": "CATEGORIA" }.
        """
        if not pendientes:
            return {}

        tareas_lotes = []
        
        # Iteramos sobre la lista de pendientes saltando de 'batch_size' en 'batch_size'
        for i in range(0, len(pendientes), batch_size):
            lote_tuplas = pendientes[i : i + batch_size]
            
            # Reconstruimos una lista plana de objetos/dicts solo para enviarla a la función IA,
            # pero AHORA la función IA respetará el 'id' real porque se lo pasaremos pre-formateado.
            lote_para_enviar = []
            for idx_real, tx in lote_tuplas:
                lote_para_enviar.append({
                    "id": idx_real, # Forzamos el ID absoluto
                    "tx_data": tx   # Pasamos el objeto original
                })
            
            # Ejecutamos la promesa (asumiendo que funcion_ia_clasificadora usa semáforos por dentro)
            tareas_lotes.append(funcion_ia_clasificadora(banco, lote_para_enviar))

        self._log_debug(3, f"Enviando {len(tareas_lotes)} lotes a la IA...")
        resultados_lotes = await asyncio.gather(*tareas_lotes, return_exceptions=True)

        # Mapeo universal (Soporta si la IA devuelve listas o diccionarios)
        mapa_clasificacion_total = {}
        for resultado_ia in resultados_lotes:
            if isinstance(resultado_ia, Exception):
                logger.error(f"[MotorClasificador] Fallo en un lote de IA: {resultado_ia}")
                continue
                
            if isinstance(resultado_ia, dict):
                for key, etiqueta in resultado_ia.items():
                    clean_key = ''.join(filter(str.isdigit, str(key)))
                    if clean_key:
                        mapa_clasificacion_total[str(clean_key)] = etiqueta

        return mapa_clasificacion_total

    def _calcular_totales(self, transacciones: List[Any]) -> dict:
        """
        ÚNICA fuente de verdad para los totales. 
        Reemplaza tu antiguo `_aplicar_reglas_negocio_y_calcular_totales`
        pero sin sobrescribir las etiquetas (porque ya se hizo en el filtro).
        """
        totales = {
            "EFECTIVO": 0.0, "TRASPASO": 0.0, "FINANCIAMIENTO": 0.0,
            "BMRCASH": 0.0, "MORATORIOS": 0.0, "TPV": 0.0, "DEPOSITOS": 0.0
        }
        
        conteo_categorias = {"TPV": 0, "GENERAL": 0, "OTROS": 0}

        for tx in transacciones:
            try:
                monto_str = str(getattr(tx, "monto", "0")).replace("$", "").replace(",", "").strip()
                monto = float(monto_str)
            except: 
                monto = 0.0
            
            tipo_lower = str(getattr(tx, "tipo", "")).lower().strip()
            
            # Solo sumamos ingresos
            if tipo_lower not in ["abono", "deposito", "depósito", "credito", "crédito"]:
                continue

            totales["DEPOSITOS"] += monto
            
            # Extraemos la categoría (que ya fue puesta por Python o por la IA)
            cat_actual = str(getattr(tx, "categoria", "GENERAL")).upper().strip()

            es_tpv = "TPV" in cat_actual or "TERMINAL" in cat_actual or "PUNTO DE VENTA" in cat_actual
            
            if es_tpv:
                totales["TPV"] += monto
                tx.categoria = "TPV" # Normalización estética para el Excel
                conteo_categorias["TPV"] += 1
            elif cat_actual in totales:
                totales[cat_actual] += monto
                conteo_categorias["OTROS"] += 1
            else:
                conteo_categorias["GENERAL"] += 1

        self._log_debug(4, f"Resumen -> TPV: {conteo_categorias['TPV']} | Otros: {conteo_categorias['OTROS']} | General: {conteo_categorias['GENERAL']}")
        self._log_debug(4, f"Monto TPV Neto Calculado: ${totales['TPV']:,.2f}")
        
        return totales