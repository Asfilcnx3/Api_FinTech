# core/motor_clasificador.py

import logging
import math
import asyncio
from typing import List, Any
import re
import difflib
import unicodedata

from ..utils.tags_y_pesos_fluxo import CategoriaTag, CONFIGURACION_TAGS

logger = logging.getLogger(__name__)

class MotorClasificador:
    """
    Motor centralizado para la clasificación de transacciones bancarias.
    Aplica filtros deterministas de primera capa y delega la ambigüedad a modelos LLM.
    """
    def __init__(self, debug_flags: list = None):
        """
        Inicializa el motor inyectando los diccionarios de palabras clave.
        """
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
    
    def _aplicar_matriz_conflictos(self, tags_encontrados: dict, es_abono: bool) -> tuple:
        """
        Fase 2 y 3: Evalúa los tags.
        Retorna: (categoría_final, razón_de_la_clasificación) o (None, None) si va a la IA.
        """
        if not tags_encontrados:
            return None, None

        # --- 1. DEFENSA POR NATURALEZA DEL MOVIMIENTO (Abono vs Cargo) ---
        if es_abono:
            # Los abonos NUNCA son comisiones ni IVA (Evita el falso positivo de "terminales punto de venta")
            tags_encontrados.pop(CategoriaTag.IVA, None)
            tags_encontrados.pop(CategoriaTag.COMISION_CR, None)
            tags_encontrados.pop(CategoriaTag.COMISION_DB, None)
            tags_encontrados.pop(CategoriaTag.COMISION_AMEX, None)
            tags_encontrados.pop(CategoriaTag.COMISION_MIXTA, None)
        else:
            # Los cargos tienen defensas especiales
            # A) Pago Financiamiento tiene máxima prioridad en salidas (mata IVA y Comisiones)
            if CategoriaTag.PAGO_FINANCIAMIENTO in tags_encontrados:
                return CategoriaTag.PAGO_FINANCIAMIENTO.value, "Defensa de cargos: Pago a financiamiento tiene prioridad máxima."
            
            # B) Si es un Traspaso o BMRCASH saliente, anulamos falsos positivos de IVA/Comisión
            es_traspaso = CategoriaTag.TRASPASO in tags_encontrados
            es_bmrcash = CategoriaTag.BMRCASH in tags_encontrados
            if es_traspaso or es_bmrcash:
                tags_encontrados.pop(CategoriaTag.IVA, None)
                tags_encontrados.pop(CategoriaTag.COMISION_CR, None)
                tags_encontrados.pop(CategoriaTag.COMISION_DB, None)
                tags_encontrados.pop(CategoriaTag.COMISION_AMEX, None)
                tags_encontrados.pop(CategoriaTag.COMISION_MIXTA, None)

        # Validamos si nos quedamos sin tags después de la defensa
        if not tags_encontrados:
            return None, None

        # --- 2. SUPREMACÍA DE COMISIONES E IVA ---
        # Evaluar esto ANTES de las excluidas las vuelve "inmunes" a que la palabra "comision" las mate.
        if CategoriaTag.IVA in tags_encontrados:
            return CategoriaTag.IVA.value, "Regla de supremacía: IVA mata cualquier otra categoría."
            
        tags_comision = [
            CategoriaTag.COMISION_CR, CategoriaTag.COMISION_DB, 
            CategoriaTag.COMISION_AMEX, CategoriaTag.COMISION_MIXTA
        ]
        
        comisiones_presentes = [t for t in tags_comision if t in tags_encontrados]
        if comisiones_presentes:
            # Si hay choque de comisiones, gana la de mayor peso (Ej. COMISION_CR > COMISION_MIXTA)
            comisiones_presentes.sort(key=lambda x: tags_encontrados[x], reverse=True)
            return comisiones_presentes[0].value, f"Regla de supremacía: Comisión detectada ({comisiones_presentes[0].value})."

        # --- 3. MUERTE SÚBITA: EXCLUSIONES ---
        # Si no fue IVA ni Comisión, y tiene una palabra prohibida, muere a GENERAL.
        if CategoriaTag.EXCLUIDA in tags_encontrados:
            return "GENERAL", "Muerte Súbita: Contiene palabra en lista de exclusiones."

        # --- 4. MATRIZ DE CONFLICTOS ESTÁNDAR ---
        if CategoriaTag.TPV in tags_encontrados:
            return CategoriaTag.TPV.value, "Matriz de conflictos: TPV tiene prioridad sobre financiamientos/traspasos."

        # --- 5. FALLBACK HEURÍSTICO (Desempate por Pesos) ---
        tags_ordenados = sorted(tags_encontrados.items(), key=lambda item: item[1], reverse=True)
        mejor_tag, mejor_peso = tags_ordenados[0]

        razon_heuristica = f"Resolución heurística: Gana el Tag '{mejor_tag.value}' con peso de {mejor_peso} puntos."

        # Traducción Dinámica
        if mejor_tag == CategoriaTag.TRASPASO:
            cat = "TRASPASO_ABONO" if es_abono else "TRASPASO_CARGO"
            return cat, razon_heuristica
        elif mejor_tag == CategoriaTag.FINANCIAMIENTO:
            cat = "FINANCIAMIENTO" if es_abono else "PAGO_FINANCIAMIENTO"
            return cat, razon_heuristica
        elif mejor_tag == CategoriaTag.PAGO_FINANCIAMIENTO:
            return "PAGO_FINANCIAMIENTO", razon_heuristica
            
        return mejor_tag.value, razon_heuristica

    def _pre_clasificar_transacciones(self, transacciones: List[Any], nombre_cliente: str = "") -> tuple:
        """
        Capa 1 Refactorizada: Sistema Multi-Etiqueta + Matriz de Conflictos.
        Extrae tags en O(N) por transacción y delega la resolución.
        """
        resueltas_por_python = []
        pendientes_para_ia = []

        for idx_real, tx in enumerate(transacciones):
            # --- NORMALIZACIÓN PLANA ---
            tipo_lower = str(getattr(tx, "tipo", "")).lower().strip()
            desc_raw = str(getattr(tx, "descripcion", "")).lower()
            desc_norm = unicodedata.normalize('NFKD', desc_raw).encode('ASCII', 'ignore').decode('utf-8')
            desc_plana = re.sub(r'\s+', ' ', desc_norm).strip()

            # FILTRO ANTI-BASURA OCR
            if tipo_lower == "importe":
                tx.categoria = "BASURA_OCR"
                tx.razon_clasificacion = "Descarte automático: Identificado como Basura OCR / CFDI." # <-- NUEVO
                resueltas_por_python.append((idx_real, tx))
                self._log_debug(1, f"Tx {idx_real} descartada (Basura OCR/CFDI) -> {desc_plana[:40]}...")
                continue
            
            es_abono = tipo_lower in ["abono", "deposito", "depósito", "credito", "crédito"]

            # FASE 1: MULTI-ETIQUETADO (Scoring)
            tags_encontrados = {} # Formato: {CategoriaTag.TPV: 80, CategoriaTag.FINANCIAMIENTO: 50}
            
            for tag, config in CONFIGURACION_TAGS.items():
                palabras = config["palabras"]
                peso = config["peso"]
                
                # Búsqueda en el diccionario
                if any(p in desc_plana for p in palabras):
                    tags_encontrados[tag] = peso

            # Hack de compatibilidad: Conservamos tu regex especial de domiciliación Dru
            if CategoriaTag.PAGO_FINANCIAMIENTO not in tags_encontrados and re.search(r'\bdru\d+\s*domiciliacion\b', desc_plana):
                tags_encontrados[CategoriaTag.PAGO_FINANCIAMIENTO] = CONFIGURACION_TAGS[CategoriaTag.PAGO_FINANCIAMIENTO]["peso"]

            # FASE 2 y 3: MATRIZ DE CONFLICTOS
            categoria_final, razon = self._aplicar_matriz_conflictos(tags_encontrados, es_abono)

            # DISPATCHER
            if categoria_final:
                # Si es excluido, la matriz nos devolvió "GENERAL".
                # Lo mandamos a resueltas_por_python para que no ensucie la cola de la IA.
                tx.categoria = categoria_final
                tx.razon_clasificacion = razon
                resueltas_por_python.append((idx_real, tx))
                self._log_debug(2, f"Tx {idx_real} clasificada como {tx.categoria} por Matriz/Pesos -> {desc_plana[:40]}...")
            else:
                # Si no hubo tags, se va a la IA
                pendientes_para_ia.append((idx_real, tx))

        self._log_debug(2, f"Pre-clasificación Híbrida lista: {len(resueltas_por_python)} resueltas estáticamente, {len(pendientes_para_ia)} a IA.")
        return resueltas_por_python, pendientes_para_ia

    def _procesar_sub_comisiones(self, transacciones: List[Any]):
        """
        Sub-motor heurístico para clasificar las comisiones previamente atrapadas.
        Toma todo lo que diga 'COMISION_PENDIENTE' y lo separa por tipo de tarjeta.
        """

        for _, tx in enumerate(transacciones):
            if getattr(tx, "categoria", "") == "COMISION_PENDIENTE":
                # Limpieza agresiva (aplanar texto y quitar acentos/símbolos)
                desc_raw = str(getattr(tx, "descripcion", "")).lower()
                desc_norm = unicodedata.normalize('NFKD', desc_raw).encode('ASCII', 'ignore').decode('utf-8')
                desc_plana = re.sub(r'\s+', ' ', desc_norm).strip()

                # Sub-clasificación heurística
                if re.search(r'\b(cr|cre|credito)\b', desc_plana):
                    tx.categoria = "COMISION_CR"
                elif re.search(r'\b(db|deb|debito)\b', desc_plana):
                    tx.categoria = "COMISION_DB"
                elif re.search(r'\b(amex|american express|amexco)\b', desc_plana):
                    tx.categoria = "COMISION_AMEX"
                else:
                    # Si dice comisión pero no especifica tarjeta, se va a mixta/genérica
                    tx.categoria = "COMISION_TPV_MIXTA"
                
                self._log_debug(2, f"Sub-motor resolvió: {tx.categoria} -> {desc_plana[:40]}...")
    
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
        1. Filtra estáticamente (La Atarraya).
        2. Envía lotes pequeños a la IA.
        3. Ensambla resultados.
        4. Pasa por el Sub-Motor de Comisiones.
        5. Calcula totales.
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

        # --- CAPA 3: ENSAMBLAJE DE LA IA ---
        for idx_real, tx in pendientes_ia:
            str_idx = str(idx_real)
            nueva_cat = mapa_ia.get(str_idx)
            
            if nueva_cat:
                # --- TRADUCTOR DE IA A SISTEMA ---
                cat_limpia = nueva_cat.lower().strip()
                tipo_lower = str(getattr(tx, "tipo", "")).lower().strip()
                es_abono = tipo_lower in ["abono", "deposito", "depósito", "credito", "crédito"]
                
                if cat_limpia == "traspaso entre cuentas":
                    tx.categoria = "TRASPASO_ABONO" if es_abono else "TRASPASO_CARGO"
                elif cat_limpia == "financiamiento":
                    tx.categoria = "FINANCIAMIENTO" if es_abono else "PAGO_FINANCIAMIENTO"
                else:
                    # Fallback general para etiquetas estandarizadas (ej. tpv -> TPV)
                    tx.categoria = cat_limpia.upper()

                tx.razon_clasificacion = "Delegado a IA: Clasificación semántica en lote."
                self._log_debug(3, f"Tx {idx_real} clasificada por IA como -> {tx.categoria}")
            else:
                tx.categoria = "GENERAL"
                tx.razon_clasificacion = "IA Fallback: No se pudo clasificar, asignado a GENERAL."
                self._log_debug(3, f"⚠️ Tx {idx_real} sin etiqueta IA -> GENERAL (Fallback)")

        # --- CAPA 3.5: SUB-MOTOR DE COMISIONES ---
        # Pasamos TODAS las transacciones para que convierta las "COMISION_PENDIENTE" en su tipo real
        self._procesar_sub_comisiones(transacciones)

        # --- CAPA 4: SUMATORIAS FINALES ---
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

        # --- LOG TEMPORAL DE DIAGNÓSTICO ---
        # logger.info(f"[DEBUG IA RAW] Payload devuelto por gather: {resultados_lotes}")

        # Mapeo universal
        mapa_clasificacion_total = {}
        for resultado_ia in resultados_lotes:
            if isinstance(resultado_ia, Exception):
                logger.error(f"[MotorClasificador] Fallo en un lote de IA: {resultado_ia}")
                continue
                
            if isinstance(resultado_ia, dict):
                for key, etiqueta in resultado_ia.items():
                    # clean_key = ''.join(filter(str.isdigit, str(key)))  <- ANTERIOR
                    clean_key = str(key).strip() # <- NUEVO: La IA ya devuelve el ID limpio, pero por si acaso le metemos un strip() para evitar espacios raros. No queremos perder clasificaciones por un espacio de más.
                    if clean_key:
                        mapa_clasificacion_total[clean_key] = etiqueta

        return mapa_clasificacion_total

    def _calcular_totales(self, transacciones: List[Any]) -> dict:
        """
        ÚNICA fuente de verdad para los totales base. 
        Nota: Los totales finales de traspasos se recalcularán en la capa global.
        """
        totales = {
            "EFECTIVO": 0.0, "TRASPASO_ABONO": 0.0, "TRASPASO_CARGO": 0.0, 
            "FINANCIAMIENTO": 0.0, "BMRCASH": 0.0, "MORATORIOS": 0.0, 
            "TPV": 0.0, "DEPOSITOS": 0.0,
            "COMISION_CR": 0.0, "COMISION_DB": 0.0, "COMISION_AMEX": 0.0, "COMISION_TPV_MIXTA": 0.0,
            "PAGO_FINANCIAMIENTO": 0.0
        }
        
        conteo_categorias = {"TPV": 0, "GENERAL": 0, "OTROS": 0}

        for tx in transacciones:
            try:
                monto_str = str(getattr(tx, "monto", "0")).replace("$", "").replace(",", "").strip()
                monto = float(monto_str)
            except (ValueError, TypeError, AttributeError): # <- EXCEPT ACOTADO
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
            elif cat_actual == "BASURA_OCR": # Evita que la basura sume a GENERAL
                pass
            else:
                conteo_categorias["GENERAL"] += 1

        self._log_debug(4, f"Resumen -> TPV: {conteo_categorias['TPV']} | Otros: {conteo_categorias['OTROS']} | General: {conteo_categorias['GENERAL']}")

        logger.info(f"--- DEBUG MOTOR ---")
        logger.info(f"CR: {totales.get('COMISION_CR', 0)} | DB: {totales.get('COMISION_DB', 0)} | AMEX: {totales.get('COMISION_AMEX', 0)} | MIXTA: {totales.get('COMISION_TPV_MIXTA', 0)}")
        
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