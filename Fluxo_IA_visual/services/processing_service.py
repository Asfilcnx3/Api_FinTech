import asyncio
import logging
from fastapi.encoders import jsonable_encoder
from concurrent.futures import ProcessPoolExecutor

# Imports del proyecto
from ..models.responses_analisisTPV import AnalisisTPV
from ..services.ia_extractor import clasificar_lote_con_ia
from ..core.exceptions import PDFCifradoError
from ..services.storage_service import guardar_excel_local, guardar_json_local
from ..utils.xlsx_converter import generar_excel_reporte

from ..utils.helpers import total_depositos_verificacion

from ..utils.helpers_texto_fluxo import prompt_base_fluxo

from ..utils.helpers_texto_fluxo import (
    PALABRAS_EXCLUIDAS,
    PALABRAS_EFECTIVO,
    PALABRAS_TRASPASO_ENTRE_CUENTAS,
    PALABRAS_TRASPASO_FINANCIAMIENTO,
    PALABRAS_BMRCASH,
    PALABRAS_TRASPASO_MORATORIO
)

# Imports de orquestadores
from ..services.orchestators import (
    obtener_y_procesar_portada, 
    procesar_digital_worker_sync, 
    procesar_ocr_worker_sync
)

logger = logging.getLogger(__name__)

class ProcessingService:
    def __init__(self, file_manager):
        self.file_manager = file_manager

    async def ejecutar_pipeline_background(self, job_id: str, lista_archivos: list):
        """
        Esta función encapsula TODA la lógica pesada.
        Recibe la lista de metadatos de archivos: [{'path': Path, 'filename': str, ...}]
        """
        logger.info(f"Iniciando Pipeline para Job {job_id}")
        
        tareas_analisis = []
        
        # --- ETAPA 1: ANÁLISIS DE PORTADA ---
        # Leemos archivos uno por uno para extraer texto inicial
        for doc_info in lista_archivos:
            path = doc_info["path"]
            try:
                with open(path, "rb") as f:
                    pdf_bytes = f.read()
                    # Analisis inicial (Portadas, Rangos, Texto base)
                    tarea = obtener_y_procesar_portada(prompt_base_fluxo, pdf_bytes)
                    tareas_analisis.append(tarea)
            except Exception as e:
                logger.error(f"Error leyendo archivo {path}: {e}")
                # Agregamos una excepción a la lista para manejarla después
                tareas_analisis.append(asyncio.create_task(self._return_exception(e)))

        # Ejecutamos análisis de portadas en paralelo (I/O bound + API Calls)
        try:
            resultados_portada = await asyncio.gather(*tareas_analisis, return_exceptions=True)
        except Exception as e:
            logger.critical(f"Error crítico en Etapa 1: {e}")
            return # Detener pipeline

        # --- LIMPIEZA TEMPRANA ---
        # Si ya extrajimos texto y rangos, ¿necesitamos el archivo en disco para los digitales?
        # Para OCR sí, para Digitales tal vez no (ya tenemos texto).
        # Por seguridad, los mantenemos hasta el final, pero aquí podrías optimizar.

        # --- ETAPA 2: SEPARACIÓN Y PREPARACIÓN ---
        documentos_digitales = []
        documentos_escaneados = []
        resultados_finales = [None] * len(lista_archivos)

        # Calculamos totales globales para decidir estrategia OCR
        total_depositos, es_mayor = total_depositos_verificacion(resultados_portada)

        for i, resultado_bruto in enumerate(resultados_portada):
            doc_meta = lista_archivos[i]
            filename = doc_meta["filename"]
            file_path = str(doc_meta["path"])

            # Manejo de Errores de Etapa 1
            if isinstance(resultado_bruto, Exception):
                error_msg = str(resultado_bruto)
                if isinstance(resultado_bruto, PDFCifradoError):
                    error_msg = "Documento protegido con contraseña."
                
                resultados_finales[i] = AnalisisTPV.ResultadoExtraccion(
                    AnalisisIA=None, 
                    DetalleTransacciones=AnalisisTPV.ErrorRespuesta(error=error_msg)
                )
                continue

            # Desempaquetado exitoso
            lista_cuentas, es_digital, texto_paginas, movimientos_paginas, texto_por_pagina, rangos = resultado_bruto

            try:
                for idx_cuenta, datos_cuenta in enumerate(lista_cuentas):
                    rango = rangos[idx_cuenta]
                    # parche de seguridad: si movs_pag es None, usar {}
                    movimientos_seguros = movimientos_paginas if movimientos_paginas is not None else {}
                    
                    item_info = {
                        "index": i, # Indice del archivo padre
                        "sub_index": idx_cuenta,
                        "filename": f"{filename} (Cta {idx_cuenta + 1})",
                        "file_path": file_path, # <--- PASAMOS EL PATH
                        "ia_data": datos_cuenta,
                        "texto_por_pagina": texto_por_pagina, # Pasamos el texto ya extraido
                        "movimientos": movimientos_seguros,
                        "rango_paginas": rango
                    }

                    if es_digital:
                        documentos_digitales.append(item_info)
                    else:
                        documentos_escaneados.append(item_info)

            except Exception as e:
                logger.error(f"Error separando cuentas {filename}: {e}")
                resultados_finales[i] = AnalisisTPV.ErrorRespuesta(error="Error interno separando cuentas.")

        # --- ETAPA 3: PROCESAMIENTO PARALELO (FASE 2 - ESCRIBA) ---
        loop = asyncio.get_running_loop()
        tareas_digitales = []
        tareas_ocr = []
        
        # Lógica de decisión OCR
        procesar_ocr = es_mayor and documentos_escaneados and len(documentos_escaneados) <= 15

        logger.info(f"Iniciando Workers. Digitales: {len(documentos_digitales)}, OCR: {len(documentos_escaneados)} (Activo: {procesar_ocr})")

        with ProcessPoolExecutor() as executor:
            # 3.A Digitales
            for doc in documentos_digitales:
                tarea = loop.run_in_executor(
                    executor,
                    procesar_digital_worker_sync,
                    doc["ia_data"],
                    doc["texto_por_pagina"],
                    doc["movimientos"],
                    doc["filename"],
                    doc["file_path"], # <--- Pasamos PATH
                    doc["rango_paginas"]
                )
                tareas_digitales.append((doc["index"], tarea))

            # 3.B OCR
            if procesar_ocr:
                for doc in documentos_escaneados:
                    tarea = loop.run_in_executor(
                        executor,
                        procesar_ocr_worker_sync,
                        doc["ia_data"],
                        doc["file_path"], # <--- Pasamos PATH (Ahorro RAM)
                        doc["filename"]
                    )
                    tareas_ocr.append((doc["index"], tarea))
            else:
                # 3.C Manejo de Omitidos (Lógica de negocio)
                self._manejar_ocr_omitidos(documentos_escaneados, resultados_finales, es_mayor)

            # 3.D Esperar resultados
            resultados_brutos_digitales = []
            if tareas_digitales:
                resultados_brutos_digitales = await asyncio.gather(*[t[1] for t in tareas_digitales], return_exceptions=True)

            resultados_brutos_ocr = []
            ocr_timed_out = False
            if tareas_ocr:
                try:
                    resultados_brutos_ocr = await asyncio.wait_for(
                        asyncio.gather(*[t[1] for t in tareas_ocr], return_exceptions=True),
                        timeout=13 * 60
                    )
                except asyncio.TimeoutError:
                    ocr_timed_out = True
                    self._manejar_timeout_ocr(tareas_ocr, documentos_escaneados, resultados_finales)

        # --- ETAPA 4: RECOLECCIÓN Y CLASIFICACIÓN (FASE 3 - AUDITOR) ---
        # 1. Ensamblar resultados crudos (Objetos Pydantic con categoría "GENERAL")
        resultados_fase_2 = self._ensamblar_resultados_crudos(
            resultados_finales, 
            tareas_digitales, resultados_brutos_digitales, 
            tareas_ocr, resultados_brutos_ocr, ocr_timed_out,
            lista_archivos,
            documentos_digitales, 
            documentos_escaneados 
        )

        # --- ETAPA INTERMEDIA: INYECCIÓN GEOMÉTRICA (SOLO OCR) ---
        for resultado_doc in resultados_fase_2:
            if not hasattr(resultado_doc, "file_path_origen"):
                continue

            if isinstance(resultado_doc.DetalleTransacciones, AnalisisTPV.ErrorRespuesta):
                continue

            # --- CAMBIO CRÍTICO ---
            # Si es digital, el Worker Sync YA HIZO la geometría perfecta.
            # Solo ejecutamos este bloque si NO es digital (es decir, OCR que vino de la IA antigua)
            if getattr(resultado_doc, "es_digital", True):
                continue 
            # ----------------------

        # --- ETAPA 4: CLASIFICACIÓN FINAL (FASE 3 - AUDITOR CON BATCHING) ---
        BATCH_SIZE = 100 # Procesamos de 100 en 100 para no saturar al LLM
        
        for resultado_doc in resultados_fase_2:
            if isinstance(resultado_doc.DetalleTransacciones, AnalisisTPV.ErrorRespuesta):
                continue

            transacciones = resultado_doc.DetalleTransacciones.transacciones
            if not transacciones:
                continue

            banco_actual = resultado_doc.AnalisisIA.banco
            total_tx = len(transacciones)
            logger.info(f"Clasificando {total_tx} movimientos de {banco_actual} en paralelo...")

            # 1. PREPARAR TODAS LAS TAREAS (Sin await aquí)
            tareas_lotes = []
            
            # Calculamos cuántos lotes necesitamos
            for i in range(0, total_tx, BATCH_SIZE):
                lote = transacciones[i : i + BATCH_SIZE]
                # Agregamos la corutina a la lista de tareas
                tareas_lotes.append(clasificar_lote_con_ia(banco_actual, lote))

            # 2. DISPARAR TODO DE GOLPE (Aquí ocurre la magia asíncrona)
            # Esto enviará todas las peticiones a OpenAI casi al mismo tiempo
            resultados_lotes = await asyncio.gather(*tareas_lotes)

            # 3. RECONSTRUIR EL MAPA COMPLETO
            mapa_clasificacion_total = {}
            
            for i_lote, mapa_lote in enumerate(resultados_lotes):
                offset = i_lote * BATCH_SIZE

                if isinstance(mapa_lote, Exception) or not isinstance(mapa_lote, dict):
                    logger.warning(f"Lote {i_lote} devolvió error o formato inválido: {mapa_lote}")
                    continue

                for idx_relativo, etiqueta in mapa_lote.items():
                    # Validamos que la llave sea un número antes de convertir
                    str_idx = str(idx_relativo).strip()
                    if not str_idx.isdigit():
                        logger.warning(f"Ignorando índice inválido de IA: '{idx_relativo}'")
                        continue

                    try:
                        idx_global = str(int(str_idx) + offset)
                        mapa_clasificacion_total[idx_global] = etiqueta
                    except Exception as e:
                        logger.error(f"Error calculando índice global: {e}")
                        continue

            # 4. APLICAR ETIQUETAS DE LA IA AL OBJETO (Solo TPV vs GENERAL)
            for idx, tx in enumerate(transacciones):
                str_idx = str(idx)
                etiqueta_ia = mapa_clasificacion_total.get(str_idx, "GENERAL")
                
                if tx.tipo == "cargo":
                    tx.categoria = "CARGO"
                else:
                    tx.categoria = etiqueta_ia # TPV o GENERAL (La IA no decide Efectivo/Traspasos)

            # --- FASE DE AGREGACIÓN ÚNICA (FINAL) ---
            # Aquí aplicamos las reglas de negocio de Python (Efectivo, Traspasos, etc.)
            # Y sumamos todo UNA SOLA VEZ.
            self._aplicar_reglas_negocio_y_calcular_totales(resultado_doc.AnalisisIA, transacciones)

        # --- ETAPA 5: GENERACIÓN DE REPORTES ---
        # Ahora 'resultados_fase_2' ya tiene las categorías actualizadas
        self._generar_y_guardar_reportes(resultados_fase_2, job_id)

        # --- LIMPIEZA FINAL ---
        rutas_a_borrar = [d["path"] for d in lista_archivos]
        self.file_manager.limpiar_temporales(rutas_a_borrar)
        logger.info(f"Job {job_id} finalizado exitosamente.")

    # --- MÉTODOS AUXILIARES PRIVADOS (Para mantener limpio el método principal) ---
    async def _return_exception(self, e):
        logger.error(f"Error en tarea asíncrona: {e}")
        return e

    def _manejar_ocr_omitidos(self, docs_escaneados, resultados_finales, es_mayor):
        if not docs_escaneados: return
        msg = "OCR omitido por seguridad o límites."
        if len(docs_escaneados) > 15: msg = "Límite de documentos escaneados excedido (>15)."
        elif not es_mayor: msg = "Monto total insuficiente para procesar OCR (<250k)."
        
        for doc in docs_escaneados:
            resultados_finales[doc["index"]] = AnalisisTPV.ResultadoExtraccion(
                AnalisisIA=doc["ia_data"],
                DetalleTransacciones=AnalisisTPV.ErrorRespuesta(error=msg)
            )

    def _manejar_timeout_ocr(self, tareas_ocr, docs_escaneados, resultados_finales):
        error_obj = AnalisisTPV.ErrorRespuesta(error="Timeout: Procesamiento OCR excedió 13 min.")
        for index, _ in tareas_ocr:
            # Buscamos la data original para no perder lo que ya teníamos (carátula)
            # Esto es ineficiente O(N), pero N es pequeño (<20)
            doc_data = next((d for d in docs_escaneados if d["index"] == index), None)
            ia_data = doc_data["ia_data"] if doc_data else None
            
            resultados_finales[index] = AnalisisTPV.ResultadoExtraccion(
                AnalisisIA=ia_data,
                DetalleTransacciones=error_obj
            )

    def _ensamblar_resultados_crudos(self, res_finales, t_dig, r_dig, t_ocr, r_ocr, timeout, lista_archivos, documentos_digitales, documentos_escaneados):
        """
        Recopila resultados e INYECTA la metadata necesaria (path, rangos) para la fase geométrica.
        Necesitamos recibir 'documentos_digitales' y 'documentos_escaneados' para saber el contexto.
        """
        acumulados = []
        
        # Helper interno
        def procesar_lista(tareas, resultados_brutos, lista_contexto, es_digital_flag):
            for i, (idx_orig, _) in enumerate(tareas):
                res = resultados_brutos[i]

                # Recuperamos el contexto original (path, rango) usando el índice
                # El orden de 'tareas' coincide con el orden de 'lista_contexto' (digitales o escaneados)
                contexto = lista_contexto[i] 
                
                if isinstance(res, list):
                    for item in res:
                        item.file_path_origen = contexto["file_path"]
                        item.rango_paginas = contexto.get("rango_paginas", (1, 100))
                        item.es_digital = es_digital_flag
                        acumulados.append(item)

                elif isinstance(res, list):
                    for item in res:
                        item.file_path_origen = contexto["file_path"]
                        item.rango_paginas = contexto.get("rango_paginas", (1, 100))
                        item.es_digital = es_digital_flag   
                        acumulados.append(item)
                else:
                    res.file_path_origen = contexto["file_path"]
                    res.rango_paginas = contexto.get("rango_paginas", (1, 100))
                    res.es_digital = es_digital_flag
                    acumulados.append(res)

        # Procesamos Digitales
        if t_dig: 
            procesar_lista(t_dig, r_dig, documentos_digitales, True)
        
        # Procesamos OCR
        if t_ocr and not timeout: 
            procesar_lista(t_ocr, r_ocr, documentos_escaneados, False)
        
        # Agregar resultados fallidos previos (Estos no necesitan geometría, tienen error)
        indices_procesados = {t[0] for t in t_dig} 
        if not timeout: indices_procesados.update({t[0] for t in t_ocr})
        
        for i, res in enumerate(res_finales):
            if i not in indices_procesados and res is not None:
                acumulados.append(res)
                
        return acumulados

    def _generar_y_guardar_reportes(self, resultados_acumulados, job_id):
        resultados_validos = [r for r in resultados_acumulados if r is not None]
        
        # Calcular totales finales
        total_dep = sum((r.AnalisisIA.depositos or 0) for r in resultados_validos if r.AnalisisIA)
        es_mayor = total_dep > 250000
        
        # Filtramos solo las carátulas para el resumen
        resultados_generales = [r.AnalisisIA for r in resultados_validos if r.AnalisisIA]

        respuesta_final = AnalisisTPV.ResultadoTotal(
            total_depositos=total_dep,
            es_mayor_a_250=es_mayor,
            resultados_generales=resultados_generales,
            resultados_individuales=resultados_validos
        )

        # Generar archivos
        datos_dict = jsonable_encoder(respuesta_final) # Necesitas importar jsonable_encoder de fastapi.encoders
        excel_bytes = generar_excel_reporte(datos_dict)
        
        guardar_json_local(datos_dict, job_id)
        guardar_excel_local(excel_bytes, job_id)
    
    def _aplicar_reglas_negocio_y_calcular_totales(self, analisis_ia, transacciones):
        """
        ÚNICA fuente de verdad. 
        1. Aplica filtros estrictos de Python (sobreescribiendo a la IA si es necesario).
        2. Calcula los totales finales para la carátula.
        """
        if not analisis_ia: return

        # Inicializar en 0
        totales = {
            "EFECTIVO": 0.0, "TRASPASO": 0.0, "FINANCIAMIENTO": 0.0,
            "BMRCASH": 0.0, "MORATORIOS": 0.0, "TPV": 0.0, "DEPOSITOS": 0.0
        }
        
        for tx in transacciones:
            try:
                monto = float(str(tx.monto).replace(",", ""))
            except: 
                monto = 0.0
            
            # Solo nos importan los abonos para las sumas de ingresos
            if tx.tipo != "abono":
                continue

            # Suma al total general de depósitos
            totales["DEPOSITOS"] += monto

            desc = str(tx.descripcion).lower()
            
            # --- JERARQUÍA DE REGLAS (Python manda) ---
            
            if any(p in desc for p in PALABRAS_EXCLUIDAS):
                continue 

            if any(p in desc for p in PALABRAS_EFECTIVO):
                totales["EFECTIVO"] += monto
                tx.categoria = "EFECTIVO" # Sobrescribimos categoría
                
            elif any(p in desc for p in PALABRAS_TRASPASO_ENTRE_CUENTAS):
                totales["TRASPASO"] += monto
                tx.categoria = "TRASPASO"
                
            elif any(p in desc for p in PALABRAS_TRASPASO_FINANCIAMIENTO):
                totales["FINANCIAMIENTO"] += monto
                tx.categoria = "FINANCIAMIENTO"
                
            elif any(p in desc for p in PALABRAS_BMRCASH):
                totales["BMRCASH"] += monto
                tx.categoria = "BMRCASH"
                
            elif any(p in desc for p in PALABRAS_TRASPASO_MORATORIO):
                totales["MORATORIOS"] += monto
                tx.categoria = "MORATORIOS"
                
            else:
                # Si no cayó en reglas de Python, respetamos lo que dijo la IA (TPV o GENERAL)
                if tx.categoria == "TPV":
                    totales["TPV"] += monto
                else:
                    # Es GENERAL
                    pass

        # Inyectamos los totales calculados al objeto padre
        analisis_ia.depositos_en_efectivo = totales["EFECTIVO"]
        analisis_ia.traspaso_entre_cuentas = totales["TRASPASO"]
        analisis_ia.total_entradas_financiamiento = totales["FINANCIAMIENTO"]
        analisis_ia.entradas_bmrcash = totales["BMRCASH"]
        analisis_ia.total_moratorios = totales["MORATORIOS"]
        analisis_ia.entradas_TPV_bruto = totales["TPV"]
        
        # Opcional: Actualizar el total de depósitos si queremos que coincida con la suma de partes
        # analisis_ia.depositos = totales["DEPOSITOS"] 

        # Calculamos Neto
        comisiones = analisis_ia.comisiones or 0.0
        analisis_ia.entradas_TPV_neto = totales["TPV"] - comisiones