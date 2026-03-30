import logging
import math
import asyncio
from typing import List, Any
import re
import difflib
import unicodedata

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

    def _pre_clasificar_transacciones(self, transacciones: List[Any], nombre_cliente: str = "") -> tuple:
        """
        Actúa como la Capa 1 del embudo. 
        Separa las transacciones en dos cubetas...
        """
        resueltas_por_python = []
        pendientes_para_ia = []

        for idx_real, tx in enumerate(transacciones):
            # --- NORMALIZACIÓN BÁSICA ---
            tipo_lower = str(getattr(tx, "tipo", "")).lower().strip()
            desc_lower = str(getattr(tx, "descripcion", "")).lower()

            es_abono = tipo_lower in ["abono", "deposito", "depósito", "credito", "crédito"]

            # --- REGLA 1: DESCARTE DE CARGOS COMUNES ---
            # Si es un cargo, se va a GENERAL. La evaluación global de sospechosas los atrapará después.
            if not es_abono:
                tx.categoria = "GENERAL"
                resueltas_por_python.append((idx_real, tx))
                self._log_debug(1, f"Tx {idx_real} descartada (Es cargo) -> {desc_lower[:40]}...")
                continue

            # --- REGLA 2: PALABRAS CLAVE EXACTAS (Solo para Abonos) ---
            clasificado_estatico = False
            
            if any(p in desc_lower for p in self.diccionarios.get('excluidas', [])):
                tx.categoria = "GENERAL"
                clasificado_estatico = True
            elif any(p in desc_lower for p in self.diccionarios.get('tpv', [])):
                tx.categoria = "TPV"
                clasificado_estatico = True
            elif any(p in desc_lower for p in self.diccionarios.get('efectivo', [])):
                tx.categoria = "EFECTIVO"
                clasificado_estatico = True
            elif any(p in desc_lower for p in self.diccionarios.get('traspaso', [])):
                # CAMBIO: Usamos la nueva etiqueta
                tx.categoria = "TRASPASO_ABONO" 
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
                pendientes_para_ia.append((idx_real, tx))

        self._log_debug(2, f"Pre-clasificación lista: {len(resueltas_por_python)} resueltas estáticamente, {len(pendientes_para_ia)} enviadas a IA.")
        return resueltas_por_python, pendientes_para_ia
    
    async def clasificar_y_sumar_transacciones(
        self, 
        transacciones: List[Any], 
        banco: str, 
        funcion_ia_clasificadora, 
        batch_size: int = 100,
        nombre_cliente: str = ""
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
        resueltas, pendientes_ia = self._pre_clasificar_transacciones(transacciones, nombre_cliente)

        # --- CAPA 2: ANÁLISIS SEMÁNTICO (IA) ---
        mapa_ia = await self._procesar_lotes_ia(
            pendientes=pendientes_ia, 
            banco=banco, 
            funcion_ia_clasificadora=funcion_ia_clasificadora, 
            batch_size_max=batch_size
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
        batch_size_max: int = 100 # Lo renombramos semánticamente a "max"
    ) -> dict:
        """
        Divide las transacciones ambiguas en lotes dinámicos equilibrados, 
        llama a la IA concurrentemente y ensambla un diccionario absoluto.
        """
        if not pendientes:
            return {}

        total_pendientes = len(pendientes)
        
        # --- LÓGICA DE BALANCEO DINÁMICO ---
        # 1. Calculamos cuántos lotes necesitamos en total para no superar el máximo
        num_lotes = math.ceil(total_pendientes / batch_size_max)
        
        # 2. Dividimos el total entre el número de lotes para que queden parejos
        tamano_lote_dinamico = math.ceil(total_pendientes / num_lotes)

        self._log_debug(3, f"Balanceo Dinámico: {total_pendientes} txs a IA -> Dividido en {num_lotes} lotes de aprox {tamano_lote_dinamico} txs c/u.")

        tareas_lotes = []
        
        for i in range(0, total_pendientes, tamano_lote_dinamico):
            lote_tuplas = pendientes[i : i + tamano_lote_dinamico]
            
            lote_para_enviar = []
            for idx_real, tx in lote_tuplas:
                lote_para_enviar.append({
                    "id": idx_real, 
                    "tx_data": tx  
                })
            
            tareas_lotes.append(funcion_ia_clasificadora(banco, lote_para_enviar))

        resultados_lotes = await asyncio.gather(*tareas_lotes, return_exceptions=True)

        # Mapeo universal
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
        ÚNICA fuente de verdad para los totales base. 
        Nota: Los totales finales de traspasos se recalcularán en la capa global.
        """
        totales = {
            "EFECTIVO": 0.0, "TRASPASO_ABONO": 0.0, "TRASPASO_CARGO": 0.0, 
            "FINANCIAMIENTO": 0.0, "BMRCASH": 0.0, "MORATORIOS": 0.0, 
            "TPV": 0.0, "DEPOSITOS": 0.0
        }
        
        conteo_categorias = {"TPV": 0, "GENERAL": 0, "OTROS": 0}

        for tx in transacciones:
            try:
                monto_str = str(getattr(tx, "monto", "0")).replace("$", "").replace(",", "").strip()
                monto = float(monto_str)
            except: 
                monto = 0.0
            
            tipo_lower = str(getattr(tx, "tipo", "")).lower().strip()
            es_abono = tipo_lower in ["abono", "deposito", "depósito", "credito", "crédito"]
            
            if es_abono:
                totales["DEPOSITOS"] += monto
            
            cat_actual = str(getattr(tx, "categoria", "GENERAL")).upper().strip()

            if cat_actual == "TPV":
                totales["TPV"] += monto
                conteo_categorias["TPV"] += 1
            elif cat_actual in totales:
                totales[cat_actual] += monto
                conteo_categorias["OTROS"] += 1
            else:
                conteo_categorias["GENERAL"] += 1

        self._log_debug(4, f"Resumen -> TPV: {conteo_categorias['TPV']} | Otros: {conteo_categorias['OTROS']} | General: {conteo_categorias['GENERAL']}")
        
        return totales
    
    # ==========================================
    # MÉTODOS AUXILIARES: TRANSACCIONES PROPIAS
    # ==========================================
    def _limpiar_nombre_empresa(self, nombre: str) -> str:
        """Elimina sufijos legales, caracteres especiales y normaliza (ñ->n, acentos) para cruces limpios."""

        if not nombre or nombre.lower() in ["n/a", "desc.", "desconocido", ""]:
            return ""
            
        nombre_lower = nombre.lower()
        
        # 1. NORMALIZACIÓN: Quita acentos, diéresis y convierte 'ñ' en 'n'
        # NFKD separa los caracteres de sus modificadores (ej. 'ñ' -> 'n' + '~')
        # encode('ASCII', 'ignore') tira los modificadores porque no son ASCII
        nombre_norm = unicodedata.normalize('NFKD', nombre_lower).encode('ASCII', 'ignore').decode('utf-8')
        
        # Lista de sufijos legales a eliminar (ya sin acentos gracias al paso anterior)
        sufijos = [
            r"\bs\.a\. de c\.v\.\b", r"\bsa de cv\b", r"\bs\.a\.\b", r"\bs a\b",
            r"\bs\.a\.p\.i\. de c\.v\.\b", r"\bsapi de cv\b", r"\bsapi\b",
            r"\bs\. de r\.l\. de c\.v\.\b", r"\bs de rl de cv\b", r"\bs de rl\b", r"\bs\. de r\.l\.\b",
            r"\bc\.v\.\b", r"\bcv\b", r"\bde c\.v\.\b", r"\bde cv\b"
        ]
        
        nombre_limpio = nombre_norm
        for sufijo in sufijos:
            nombre_limpio = re.sub(sufijo, "", nombre_limpio)
            
        # 2. Quitar puntuación extra y dejar solo un espacio entre palabras
        nombre_limpio = re.sub(r"[^\w\s]", "", nombre_limpio)
        nombre_limpio = re.sub(r"\s+", " ", nombre_limpio).strip()
        
        return nombre_limpio

    def _es_transaccion_propia(self, descripcion: str, nombre_cliente_caratula: str) -> bool:
        """Valida si el nombre del cliente aparece en la descripción usando coincidencia exacta y heurística."""
        nombre_limpio = self._limpiar_nombre_empresa(nombre_cliente_caratula)
        
        if len(nombre_limpio) < 4:
            return False
            
        desc_lower = descripcion.lower()
        desc_norm = unicodedata.normalize('NFKD', desc_lower).encode('ASCII', 'ignore').decode('utf-8')
        desc_limpia = re.sub(r"[^\w\s]", "", desc_norm)
        
        # 1. Coincidencia Exacta (Vía rápida)
        if nombre_limpio in desc_limpia:
            return True
            
        # 2. Heurística de Texto (Fuzzy Matching) para OCR ruidoso
        palabras_desc = desc_limpia.split()
        largo_nombre = len(nombre_limpio.split())
        
        if largo_nombre == 0 or len(palabras_desc) < largo_nombre:
            return False

        # Ventana deslizante para comparar fragmentos
        for i in range(len(palabras_desc) - largo_nombre + 1):
            # Tomamos un bloque de palabras del mismo tamaño que el nombre del cliente
            fragmento = " ".join(palabras_desc[i:i+largo_nombre])
            
            # Calculamos el ratio de similitud (0.0 a 1.0)
            similitud = difflib.SequenceMatcher(None, nombre_limpio, fragmento).ratio()
            
            # Si se parece en un 85% o más, lo damos por bueno
            if similitud >= 0.85:
                return True
                
        return False