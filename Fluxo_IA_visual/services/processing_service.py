import asyncio
import logging
from fastapi.encoders import jsonable_encoder
from concurrent.futures import ProcessPoolExecutor

# Imports del proyecto
from ..models.responses_analisisTPV import AnalisisTPV
from ..services.ia_extractor import clasificar_lote_con_ia
from ..core.exceptions import PDFCifradoError
from ..core.motor_clasificador import MotorClasificador
from ..services.storage_service import guardar_excel_local, guardar_json_local
from ..utils.xlsx_converter import generar_excel_reporte

from .passport_service import PassportService

from ..utils.helpers import total_depositos_verificacion

from ..core.motor_caratulas import MotorCaratulas
from ..utils.helpers_texto_fluxo import (
    TRIGGERS_CONFIG, PALABRAS_CLAVE_VERIFICACION, 
    ALIAS_A_BANCO_MAP, BANCO_DETECTION_REGEX, 
    PATRONES_COMPILADOS, prompt_base_fluxo
)
from ..utils.helpers import extraer_json_del_markdown, sanitizar_datos_ia
from ..services.ia_extractor import analizar_gpt_fluxo, analizar_con_ocr_fluxo

from ..utils.helpers_texto_fluxo import (
    PALABRAS_EXCLUIDAS,
    PALABRAS_EFECTIVO,
    PALABRAS_TRASPASO_ENTRE_CUENTAS,
    PALABRAS_TRASPASO_FINANCIAMIENTO,
    PALABRAS_BMRCASH,
    PALABRAS_TRASPASO_MORATORIO
)

from ..services.orchestators import (
    procesar_digital_worker_sync, 
    procesar_ocr_worker_sync
)

logger = logging.getLogger(__name__)

class ProcessingService:
    def __init__(self, file_manager):
        self.file_manager = file_manager
        self.passport = PassportService() # Inyección manual del pasaporte

        # --- SEMÁFORO DE CONCURRENCIA ---
        self.sem_ia = asyncio.Semaphore(20)

        # --- INSTANCIA DEL MOTOR DE CARÁTULAS ---
        self.motor_caratulas = MotorCaratulas(
            triggers_config=TRIGGERS_CONFIG,
            palabras_clave_regex=PALABRAS_CLAVE_VERIFICACION,
            alias_banco_map=ALIAS_A_BANCO_MAP,
            banco_detection_regex=BANCO_DETECTION_REGEX,
            patrones_compilados=PATRONES_COMPILADOS,
            debug_flags=None
        )

        # --- INSTANCIA DEL MOTOR CLASIFICADOR (NUEVO) ---
        diccionarios_clasificacion = {
            'excluidas': PALABRAS_EXCLUIDAS,
            'efectivo': PALABRAS_EFECTIVO,
            'traspaso': PALABRAS_TRASPASO_ENTRE_CUENTAS,
            'financiamiento': PALABRAS_TRASPASO_FINANCIAMIENTO,
            'bmrcash': PALABRAS_BMRCASH,
            'moratorio': PALABRAS_TRASPASO_MORATORIO
        }
        self.motor_clasificador = MotorClasificador(
            diccionarios_palabras=diccionarios_clasificacion,
            debug_flags=None  # Silencioso para producción
        )

    async def ejecutar_pipeline_background(self, job_id: str, lista_archivos: list):
        """
        Esta función encapsula TODA la lógica pesada.
        Recibe la lista de metadatos de archivos: [{'path': Path, 'filename': str, ...}]
        """
        # 0. INICIO
        self.passport.crear_pasaporte(job_id)
        logger.info(f"Iniciando Pipeline V2 (Motor Híbrido) para Job {job_id}")
        
        tareas_analisis = []
        
        # --- ETAPA 1: PORTADAS (I/O Bound -> Threads o Async nativo) ---
        self.passport.actualizar(job_id, fase=1, nombre_fase="Análisis Inicial", descripcion="Escaneando estructura de archivos...")

        for doc_info in lista_archivos:
            self.passport.actualizar(job_id, descripcion=f"Analizando carátula: {doc_info['filename']}")
            path = doc_info["path"]
            try:
                with open(path, "rb") as f:
                    pdf_bytes = f.read()
                    
                    # --- LLAMADA AL MOTOR CENTRALIZADO ---
                    tarea = self.motor_caratulas.procesar_caratula_completa(
                        pdf_bytes=pdf_bytes,
                        prompt_base=prompt_base_fluxo,
                        analizar_gpt_fn=analizar_gpt_fluxo,
                        analizar_qwen_fn=analizar_con_ocr_fluxo,
                        extraer_json_fn=extraer_json_del_markdown,
                        sanitizar_fn=sanitizar_datos_ia
                    ) 
                    tareas_analisis.append(tarea)
                    
            except Exception as e:
                logger.error(f"Error lectura {path}: {e}")
                # Agregamos una excepción a la lista para manejarla después
                tareas_analisis.append(asyncio.create_task(self._return_exception(e)))

        # Ejecutamos análisis de portadas en paralelo (I/O bound + API Calls)
        try:
            resultados_portada = await asyncio.gather(*tareas_analisis, return_exceptions=True)

        except Exception as e:
            logger.critical(f"Error crítico en Etapa 1: {e}")
            self.passport.actualizar(job_id, error=f"Fallo crítico inicial: {e}")
            return # Detener pipeline

        # --- ETAPA 2: SEPARACIÓN (Digital vs OCR) ---
        self.passport.actualizar(job_id, fase=2, nombre_fase="Extracción", descripcion="Calculando carga de trabajo...", estado="PROCESANDO")
        
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
                    movimientos_seguros = movimientos_paginas if movimientos_paginas is not None else {}
                    
                    item_info = {
                        "index": i, 
                        "sub_index": idx_cuenta,
                        "filename": f"{filename} (Cta {idx_cuenta + 1})",
                        "file_path": file_path, 
                        "ia_data": datos_cuenta,
                        "texto_por_pagina": texto_por_pagina,
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

        # [IMPLEMENTACIÓN DE LÓGICA MATEMÁTICA 1]
        # Recorremos para saber cuántas páginas digitales vamos a procesar y ajustar el tiempo estimado
        total_pags_digitales = 0
        for doc in documentos_digitales:
            if "rango_paginas" in doc and doc["rango_paginas"]:
                start, end = doc["rango_paginas"]
                # Calculamos páginas reales (ej: de la 2 a la 5 son 4 páginas)
                total_pags_digitales += (end - start + 1)
        
        # Actualizamos el pasaporte con la carga de trabajo digital inicial
        self.passport.actualizar(
            job_id, 
            sumar_paginas_digitales=total_pags_digitales,
            descripcion=f"Carga detectada: {total_pags_digitales} páginas digitales."
        )

        # --- ETAPA 3: EJECUCIÓN PARALELA (CPU Bound -> ProcessPool) ---
        self.passport.actualizar(job_id, descripcion="Ejecutando motores de lectura...")

        loop = asyncio.get_running_loop()
        tareas_digitales = []
        tareas_ocr = []
        
        # Lógica OCR
        procesar_ocr = es_mayor and documentos_escaneados and len(documentos_escaneados) <= 15

        logger.info(f"Ejecutando Workers. Digitales: {len(documentos_digitales)} | OCR: {len(documentos_escaneados)}")

        with ProcessPoolExecutor() as executor:
            
            # A. Digitales
            for doc in documentos_digitales:
                tarea = loop.run_in_executor(
                    executor,
                    procesar_digital_worker_sync, 
                    doc["ia_data"],     
                    doc["filename"],
                    str(doc["file_path"]),   
                    doc["rango_paginas"]
                )
                tareas_digitales.append((doc["index"], tarea))

            # B. OCR
            if procesar_ocr:
                for doc in documentos_escaneados:
                    tarea = loop.run_in_executor(
                        executor,
                        procesar_ocr_worker_sync,
                        doc["ia_data"],
                        str(doc["file_path"]),
                        doc["filename"]
                    )
                    tareas_ocr.append((doc["index"], tarea))
            else:
                self._manejar_ocr_omitidos(documentos_escaneados, resultados_finales, es_mayor)

            # C. Esperar resultados y actualizar Pasaporte dinámicamente
            todos_los_futuros = []
            if tareas_digitales: todos_los_futuros.extend([t[1] for t in tareas_digitales])
            if tareas_ocr: todos_los_futuros.extend([t[1] for t in tareas_ocr])

            if todos_los_futuros:
                # [IMPLEMENTACIÓN DE LÓGICA MATEMÁTICA 2]
                # as_completed nos permite actualizar la barra de progreso conforme termina cada archivo
                for futuro_completado in asyncio.as_completed(todos_los_futuros):
                    try:
                        res = await futuro_completado
                        
                        # Intentamos extraer el nombre para el log
                        nombre_archivo = "Desconocido"
                        if hasattr(res, 'AnalisisIA') and res.AnalisisIA:
                            nombre_archivo = res.AnalisisIA.nombre_archivo_virtual or "Archivo"

                        # Verificamos si es OCR o Digital
                        # (Asegúrate de que tu modelo ResultadoExtraccion tenga 'es_digital' o úsalo por defecto)
                        es_digital = getattr(res, 'es_digital', True) 
                        
                        if es_digital:
                            # Digital: Ya sumamos las páginas al inicio, solo logueamos
                            self.passport.actualizar(job_id, descripcion=f"Leído: {nombre_archivo}")
                        else:
                            # OCR: Sumamos al contador de páginas OCR (que valen 1.5s cada una)
                            self.passport.actualizar(
                                job_id, 
                                descripcion=f"OCR Finalizado: {nombre_archivo}", 
                                sumar_paginas_ocr=1 # Asumimos 1 página por tarea OCR simple
                            )
                            
                    except Exception as e:
                        logger.error(f"Error en tarea individual: {e}")

            # D. Recoger resultados finales ordenados
            # (Requerido porque as_completed pierde el orden)
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

        # --- ETAPA 4: RECOLECCIÓN ---
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

            # Si es digital, el Worker Sync YA HIZO la geometría perfecta.
            # Solo ejecutamos este bloque si NO es digital (es decir, OCR que vino de la IA antigua)
            if getattr(resultado_doc, "es_digital", True):
                continue 

        # --- ETAPA 5: CLASIFICACIÓN FINAL Y REGLAS DE NEGOCIO ---
        self.passport.actualizar(job_id, fase=3, nombre_fase="Clasificación IA", descripcion="Analizando transacciones en paralelo...")
        logger.info(f"Disparando clasificación masiva para {len(resultados_fase_2)} documentos...")

        tareas_documentos = []
        BATCH_SIZE = 100 
        
        # Creamos todas las tareas (promesas) sin ejecutarlas aún
        for resultado_doc in resultados_fase_2:
            tarea = self._clasificar_documento_async(job_id, resultado_doc, BATCH_SIZE)
            tareas_documentos.append(tarea)

        # Ejecutamos todos los documentos simultáneamente
        if tareas_documentos:
            await asyncio.gather(*tareas_documentos)

        # --- SAFETY CHECK ---
        conteo_validos = len([r for r in resultados_fase_2 if r is not None])
        logger.info(f"PRE-REPORTE: Se enviarán {conteo_validos} documentos a generar reporte.")
        
        # --- ETAPA 6: GENERACIÓN DE REPORTES ---
        self.passport.actualizar(job_id, fase=4, nombre_fase="Generando Reportes", descripcion="Escribiendo Excel y JSON...")
        self._generar_y_guardar_reportes(resultados_fase_2, job_id)

        # --- LIMPIEZA FINAL ---
        rutas_a_borrar = [d["path"] for d in lista_archivos]
        self.file_manager.limpiar_temporales(rutas_a_borrar)
        logger.info(f"Job {job_id} finalizado exitosamente.")
        
        # FINAL
        self.passport.actualizar(job_id, fase=5, nombre_fase="Completado", terminado=True)

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
        Recopila resultados, CONVIERTE diccionarios a Pydantic e INYECTA metadata.
        """
        acumulados = []
        
        # Helper interno
        def procesar_lista(tareas, resultados_brutos, lista_contexto, es_digital_flag):
            for i, (idx_orig, _) in enumerate(tareas):
                res = resultados_brutos[i]
                contexto = lista_contexto[i] 
                
                # --- CASO 1: EXCEPCIÓN ---
                if isinstance(res, Exception):
                    # CORRECCIÓN AQUÍ: Usar ResultadoAnalisisIA
                    res_model = AnalisisTPV.ResultadoExtraccion(
                        AnalisisIA=AnalisisTPV.ResultadoAnalisisIA(banco="ERROR_PROCESAMIENTO"),
                        DetalleTransacciones=AnalisisTPV.ErrorRespuesta(error=str(res))
                    )
                    # Inyectar contexto
                    res_model.file_path_origen = contexto["file_path"]
                    res_model.rango_paginas = contexto.get("rango_paginas", (1, 100))
                    res_model.es_digital = es_digital_flag
                    acumulados.append(res_model)
                    continue

                # --- CASO 2: LISTA DE RESULTADOS (Normalmente del Engine) ---
                if isinstance(res, list):
                    for item in res:
                        # CORRECCIÓN CRÍTICA: Si es dict, convertir a Objeto Pydantic
                        if isinstance(item, dict):
                            # Mapeamos la salida del Engine a la estructura de Fluxo
                            txs_raw = item.get("transacciones", [])
                            
                            # Crear objetos Transaccion
                            txs_objs = []
                            for t in txs_raw:
                                txs_objs.append(AnalisisTPV.Transaccion(
                                    fecha=t.get("fecha", ""),
                                    descripcion=t.get("descripcion", ""),
                                    monto=str(t.get("monto", "0.0")),
                                    tipo=t.get("tipo", "DESCONOCIDO"),
                                    categoria="GENERAL" # Default
                                ))

                            # Crear ResultadoTPV
                            detalle_tpv = AnalisisTPV.ResultadoTPV(transacciones=txs_objs)
                            
                            # Crear ResultadoAnalisisIA (Caratula dummy o parcial si la tienes)
                            analisis_ia = AnalisisTPV.ResultadoAnalisisIA(
                                banco="DETECTADO_POR_GEOMETRIA",
                                nombre_archivo_virtual=str(contexto["file_path"])
                            )

                            # Empaquetar en ResultadoExtraccion
                            item_obj = AnalisisTPV.ResultadoExtraccion(
                                AnalisisIA=analisis_ia,
                                DetalleTransacciones=detalle_tpv,
                                metadata_tecnica=[item.get("metricas", {})]
                            )
                        else:
                            # Ya es un objeto (quizás vino de otro lado)
                            item_obj = item

                        # AHORA SÍ podemos usar notación de punto
                        item_obj.file_path_origen = contexto["file_path"]
                        item_obj.rango_paginas = contexto.get("rango_paginas", (1, 100))
                        item_obj.es_digital = es_digital_flag
                        acumulados.append(item_obj)

                # --- CASO 3: OBJETO ÚNICO ---
                else:
                    # Asumimos que si no es lista ni Exception, ya es un objeto Pydantic
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
        
        # Agregar resultados fallidos previos
        indices_procesados = {t[0] for t in t_dig} 
        if not timeout: indices_procesados.update({t[0] for t in t_ocr})
        
        for i, res in enumerate(res_finales):
            if i not in indices_procesados and res is not None:
                acumulados.append(res)
                
        return acumulados

    def _generar_y_guardar_reportes(self, resultados_acumulados, job_id):
        # 1. Filtro estricto
        resultados_validos = [r for r in resultados_acumulados if r is not None]
        
        if not resultados_validos:
            logger.warning("Alerta: Intentando generar reporte con 0 resultados válidos.")

        # 2. Recalcular métricas globales (Tu lógica)
        total_dep = 0.0
        resultados_generales = []
        
        for r in resultados_validos:
            if r.AnalisisIA:
                total_dep += (r.AnalisisIA.depositos or 0)
                resultados_generales.append(r.AnalisisIA)
        
        es_mayor = total_dep > 250000
        
        # 3. Construir Objeto Maestro
        respuesta_final = AnalisisTPV.ResultadoTotal(
            total_depositos=total_dep,
            es_mayor_a_250=es_mayor,
            resultados_generales=resultados_generales,
            resultados_individuales=resultados_validos
        )

        # --- SERIALIZACIÓN SEGURA ---
        try:
            # Opción A: Pydantic V2 (Recomendada)
            datos_dict = respuesta_final.model_dump(mode='json')
        except AttributeError:
            # Opción B: Pydantic V1 (Fallback)
            datos_dict = jsonable_encoder(respuesta_final)

        # 4. Generar Archivos
        # Pasamos el DICCIONARIO YA SERIALIZADO al excel, no el objeto
        try:
            excel_bytes = generar_excel_reporte(datos_dict)
            guardar_excel_local(excel_bytes, job_id)
        except Exception as e:
            logger.error(f"Error generando Excel: {e}")

        guardar_json_local(datos_dict, job_id)
    
    async def _clasificar_documento_async(self, job_id, resultado_doc, BATCH_SIZE=100):
        """
        Procesa UN documento completo de forma asíncrona delegando todo al Motor Clasificador.
        """
        # 0. VALIDACIÓN E HIDRATACIÓN (Se mantiene para compatibilidad Pydantic)
        if not resultado_doc or isinstance(resultado_doc.DetalleTransacciones, AnalisisTPV.ErrorRespuesta): 
            return

        if isinstance(resultado_doc.DetalleTransacciones, dict):
            raw_dict = resultado_doc.DetalleTransacciones
            lista_cruda = raw_dict.get("transacciones", [])
            
            tx_objs = []
            for tx in lista_cruda:
                if isinstance(tx, dict):
                    tx_objs.append(AnalisisTPV.Transaccion(
                        fecha=tx.get("fecha", ""),
                        descripcion=tx.get("descripcion", ""),
                        monto=str(tx.get("monto", "0.0")),
                        tipo=tx.get("tipo", "DESCONOCIDO"),
                        categoria="GENERAL"
                    ))
                else:
                    tx_objs.append(tx)
            
            resultado_doc.DetalleTransacciones = AnalisisTPV.ResultadoTPV(transacciones=tx_objs)

        transacciones = resultado_doc.DetalleTransacciones.transacciones
        if not transacciones: return

        if isinstance(resultado_doc.AnalisisIA, dict):
            resultado_doc.AnalisisIA = AnalisisTPV.ResultadoAnalisisIA(**resultado_doc.AnalisisIA)

        banco_actual = resultado_doc.AnalisisIA.banco
        
        self.passport.actualizar(job_id, sumar_transacciones=len(transacciones), descripcion=f"Clasificando {len(transacciones)} movs...")

        # --- MAGIA DEL MOTOR CLASIFICADOR ---
        totales = await self.motor_clasificador.clasificar_y_sumar_transacciones(
            transacciones=transacciones,
            banco=banco_actual,
            funcion_ia_clasificadora=clasificar_lote_con_ia,
            batch_size=BATCH_SIZE
        )

        # --- INYECCIÓN DE RESULTADOS AL OBJETO PADRE ---
        analisis_ia = resultado_doc.AnalisisIA
        analisis_ia.depositos_en_efectivo = totales.get("EFECTIVO", 0.0)
        analisis_ia.traspaso_entre_cuentas = totales.get("TRASPASO", 0.0)
        analisis_ia.total_entradas_financiamiento = totales.get("FINANCIAMIENTO", 0.0)
        analisis_ia.entradas_bmrcash = totales.get("BMRCASH", 0.0)
        analisis_ia.total_moratorios = totales.get("MORATORIOS", 0.0)
        analisis_ia.entradas_TPV_bruto = totales.get("TPV", 0.0)
        
        # Cálculo de Neto
        try:
            com_str = str(analisis_ia.comisiones).replace("$", "").replace(",", "")
            comisiones = float(com_str) if analisis_ia.comisiones else 0.0
        except:
            comisiones = 0.0
            
        analisis_ia.entradas_TPV_neto = totales.get("TPV", 0.0) - comisiones