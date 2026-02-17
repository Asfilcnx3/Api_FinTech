from ..utils.helpers import (
    es_escaneado_o_no, extraer_datos_por_banco, extraer_json_del_markdown, limpiar_monto, sanitizar_datos_ia, 
    reconciliar_resultados_ia, detectar_tipo_contribuyente, crear_objeto_resultado,
    construir_fecha_completa
    
)
from .ia_extractor import (
    analizar_gpt_fluxo, analizar_gemini_fluxo, _extraer_datos_con_ia, llamar_agente_ocr_vision
)
from ..utils.helpers_texto_fluxo import (
    PALABRAS_BMRCASH, PALABRAS_EXCLUIDAS, PALABRAS_EFECTIVO, PALABRAS_TRASPASO_ENTRE_CUENTAS, PALABRAS_TRASPASO_FINANCIAMIENTO, PALABRAS_TRASPASO_MORATORIO
)

from ..utils.helpers_texto_csf import (
    PATRONES_CONSTANCIAS_COMPILADO
)

from .pdf_processor import (
    detectar_rangos_y_texto, extraer_texto_de_pdf
)

from ..core.extraction_motor import BankStatementEngine
from ..models.responses_motor_estados import RespuestasMotorEstados

from ..models.responses_analisisTPV import AnalisisTPV
from ..models.responses_csf import CSF

from fastapi import UploadFile
from ..core.nomiflash_engine import NomiFlashEngine
from ..models.responses_nomiflash import NomiFlash

from typing import Dict, Any, Tuple, Optional, Union, List
from fastapi import UploadFile
import logging
import fitz
import asyncio

logger = logging.getLogger(__name__)

# Singleton del Motor
_engine = NomiFlashEngine()

async def procesar_nomina(archivo: UploadFile) -> NomiFlash.RespuestaNomina:
    return await _engine.procesar_nomina(archivo)

async def procesar_segunda_nomina(archivo: UploadFile) -> NomiFlash.SegundaRespuestaNomina:
    return await _engine.procesar_segunda_nomina(archivo)

async def procesar_estado_cuenta(archivo: UploadFile) -> NomiFlash.RespuestaEstado:
    return await _engine.procesar_estado_cuenta(archivo)

async def procesar_comprobante(archivo: UploadFile) -> NomiFlash.RespuestaComprobante:
    return await _engine.procesar_comprobante(archivo)


# ----- FUNCIONES ORQUESTADORAS DE FLUXO -----
async def analizar_metadatos_rango(
    pdf_bytes: bytes, 
    paginas_a_analizar: List[int],
    prompt: str
) -> Dict[str, Any]:
    """
    Ejecuta el análisis de IA (Visión) para un conjunto específico de páginas 
    (usualmente la primera de una cuenta nueva) para obtener metadatos.
    """
    # 1. Llamadas en paralelo a las IAs
    tarea_gpt = analizar_gpt_fluxo(prompt, pdf_bytes, paginas_a_procesar=paginas_a_analizar)
    tarea_gemini = analizar_gemini_fluxo(prompt, pdf_bytes, paginas_a_procesar=paginas_a_analizar)
    
    resultados_ia_brutos = await asyncio.gather(tarea_gpt, tarea_gemini, return_exceptions=True)
    res_gpt_str, res_gemini_str = resultados_ia_brutos

    # 2. Extracción de JSON
    datos_gpt = extraer_json_del_markdown(res_gpt_str) if not isinstance(res_gpt_str, Exception) else {}
    datos_gemini = extraer_json_del_markdown(res_gemini_str) if not isinstance(res_gemini_str, Exception) else {}

    # 3. Sanitización
    datos_gpt_sanitizados = sanitizar_datos_ia(datos_gpt)
    datos_gemini_sanitizados = sanitizar_datos_ia(datos_gemini)

    # 4. Reconciliación
    datos_reconciliados = reconciliar_resultados_ia(datos_gpt_sanitizados, datos_gemini_sanitizados)
    
    return datos_reconciliados

# ESTA FUNCIÓN ES PARA OBTENER Y PROCESAR LAS PORTADAS DE LOS PDF
async def obtener_y_procesar_portada(prompt:str, pdf_bytes: bytes) -> Tuple[Dict[str, Any], bool, str, Dict[int, Any]]:
    """
    Orquesta el proceso detectando múltiples cuentas dentro del mismo PDF.
    Devuelve una lista de resultados (uno por cada cuenta detectada).
    """
    loop = asyncio.get_running_loop()

    # --- 1. PRIMERO: Extraer Texto Y Movimientos (Detectar cortes) ---
    # Esta función ya nos devuelve los puntos donde cambia de cuenta
    texto_por_pagina, rangos_cuentas = await loop.run_in_executor(
        None,
        detectar_rangos_y_texto,
        pdf_bytes
    )

    # Construimos el texto completo
    texto_verificacion_global = "\n".join(texto_por_pagina.values())
    es_documento_digital = es_escaneado_o_no(texto_verificacion_global)

    logger.info(f"Se detectaron {len(rangos_cuentas)} cuentas en los rangos: {rangos_cuentas}")

    resultados_acumulados = []

    # --- BUCLE PRINCIPAL: PROCESAR CADA CUENTA (RANGO) ---
    for inicio_rango, fin_rango in rangos_cuentas:
        logger.info(f"Procesando cuenta en rango: {inicio_rango} a {fin_rango}")

        # A. Construir texto específico de este rango para regex
        # (Esto aísla el contexto: el regex solo verá texto de ESTA cuenta)
        texto_rango = []
        for p in range(inicio_rango, fin_rango + 1):
            texto_rango.append(texto_por_pagina.get(p, ""))
        texto_verificacion_rango = "\n".join(texto_rango)

        # B. Reconocer banco y datos por Regex para ESTE rango
        datos_regex = extraer_datos_por_banco(texto_verificacion_rango.lower())
        banco_estandarizado = datos_regex.get("banco")
        rfc_estandarizado = datos_regex.get("rfc")
        comisiones_est = datos_regex.get("comisiones")
        depositos_est = datos_regex.get("depositos")

        # C. Decidir qué páginas enviar a la IA (Relativo al rango actual)
        # Lógica: Mandamos la primera del rango y la segunda (si existe)
        paginas_para_ia = [inicio_rango]
        if (inicio_rango + 1) <= fin_rango:
            paginas_para_ia.append(inicio_rango + 1)

        # Lógica especial para BANREGIO (u otros que requieran final del documento)
        if banco_estandarizado == "BANREGIO":
            longitud_rango = (fin_rango - inicio_rango) + 1
            if longitud_rango > 5:
                # Primeras del rango + Últimas 5 DEL RANGO
                paginas_finales = list(range(fin_rango - 4, fin_rango + 1))
                paginas_para_ia = sorted(list(set(paginas_para_ia + paginas_finales)))
            else:
                # Todas las páginas del rango si es corto
                paginas_para_ia = list(range(inicio_rango, fin_rango + 1))

        # D. Llamar a las IA (Enviando las páginas calculadas)
        tarea_gpt = analizar_gpt_fluxo(prompt, pdf_bytes, paginas_a_procesar=paginas_para_ia)
        tarea_gemini = analizar_gemini_fluxo(prompt, pdf_bytes, paginas_a_procesar=paginas_para_ia)

        resultados_ia_brutos = await asyncio.gather(tarea_gpt, tarea_gemini, return_exceptions=True)
        res_gpt_str, res_gemini_str = resultados_ia_brutos

        # Extracción segura de JSON (Validamos que no sea Exception Y que tenga contenido)
        datos_gpt = {}
        if res_gpt_str and not isinstance(res_gpt_str, Exception):
            datos_gpt = extraer_json_del_markdown(res_gpt_str)
        
        datos_gemini = {}
        if res_gemini_str and not isinstance(res_gemini_str, Exception):
            datos_gemini = extraer_json_del_markdown(res_gemini_str)

        # E. Sanitización y Reconciliación
        datos_gpt_sanitizados = sanitizar_datos_ia(datos_gpt)
        datos_gemini_sanitizados = sanitizar_datos_ia(datos_gemini)
        
        datos_ia_reconciliados = reconciliar_resultados_ia(datos_gpt_sanitizados, datos_gemini_sanitizados)

        # F. Merge con datos Regex (Prioridad al texto detectado)
        if banco_estandarizado: datos_ia_reconciliados["banco"] = banco_estandarizado
        if rfc_estandarizado: datos_ia_reconciliados["rfc"] = rfc_estandarizado
        if comisiones_est: datos_ia_reconciliados["comisiones"] = comisiones_est
        if depositos_est: datos_ia_reconciliados["depositos"] = depositos_est

        # Agregamos metadatos útiles para saber de qué páginas vino en el frontend/DB
        datos_ia_reconciliados["_metadatos_paginas"] = {
            "inicio": inicio_rango,
            "fin": fin_rango,
            "paginas_analizadas_ia": paginas_para_ia
        }
        
        resultados_acumulados.append(datos_ia_reconciliados)

    # Retornamos la lista de resultados y los datos globales
    # OJO: Ahora el primer elemento es una LISTA, no un Dict único.
    return resultados_acumulados, es_documento_digital, texto_verificacion_global, None, texto_por_pagina, rangos_cuentas
    
def clasificar_transacciones_extraidas(
    ia_data_cuenta: dict,
    transacciones_objetos: List["RespuestasMotorEstados.TransaccionDetectada"],
    filename: str,
    rango_paginas: Tuple[int, int]
) -> Dict[str, Any]:
    
    start_pg, end_pg = rango_paginas
    nombre_cuenta = f"{filename} (Págs {start_pg}-{end_pg})"
    logger.info(f"Clasificando {len(transacciones_objetos)} movs para: {nombre_cuenta}")
    
    # Metadata Fechas
    p_inicio = ia_data_cuenta.get("periodo_inicio")
    p_fin = ia_data_cuenta.get("periodo_fin")

    # 1. SI NO HAY TRANSACCIONES
    if not transacciones_objetos:
        return {
            **ia_data_cuenta,
            "nombre_archivo_virtual": nombre_cuenta,
            "transacciones": [],
            "depositos_en_efectivo": 0.0, "traspaso_entre_cuentas": 0.0,
            "total_entradas_financiamiento": 0.0, "entradas_bmrcash": 0.0,
            "total_moratorios": 0.0, "entradas_TPV_bruto": 0.0, "entradas_TPV_neto": 0.0,
            "error_transacciones": "El motor no detectó transacciones válidas."
        }

    # 2. PROCESAMIENTO DE REGLAS DE NEGOCIO
    total_depositos_efectivo = 0.0
    total_traspaso_entre_cuentas = 0.0
    total_entradas_financiamiento = 0.0
    total_entradas_bmrcash = 0.0
    total_entradas_tpv = 0.0
    total_moratorios = 0.0
    todas_las_transacciones = []

    for trx in transacciones_objetos:
        # --- CAMBIO CRÍTICO: ACCESO POR ATRIBUTOS ---
        monto_float = trx.monto  
        descripcion_limpia = trx.descripcion.lower()
        
        # Manejo seguro del Enum de tipo
        tipo_detectado = trx.tipo.value if hasattr(trx.tipo, 'value') else str(trx.tipo)
        
        # Fecha
        dia_raw = trx.fecha
        fecha_final = construir_fecha_completa(dia_raw, p_inicio, p_fin)

        trx_procesada = {
            "fecha": fecha_final,
            "descripcion": trx.descripcion,
            "monto": f"{monto_float:,.2f}", 
            "tipo": tipo_detectado,
            "categoria": "GENERAL",
            # Obtenemos el valor del Enum de metodo_match
            "debug_match": trx.metodo_match.value if hasattr(trx.metodo_match, 'value') else str(trx.metodo_match)
        }

        # --- LÓGICA DE CLASIFICACIÓN (KEYWORDS - IGUAL QUE ANTES) ---
        if tipo_detectado == "abono":
            if any(p in descripcion_limpia for p in PALABRAS_EXCLUIDAS):
                pass 
            else:
                if any(p in descripcion_limpia for p in PALABRAS_EFECTIVO):
                    total_depositos_efectivo += monto_float
                    trx_procesada["categoria"] = "EFECTIVO"
                elif any(p in descripcion_limpia for p in PALABRAS_TRASPASO_ENTRE_CUENTAS):
                    total_traspaso_entre_cuentas += monto_float
                    trx_procesada["categoria"] = "TRASPASO"
                elif any(p in descripcion_limpia for p in PALABRAS_TRASPASO_FINANCIAMIENTO):
                    total_entradas_financiamiento += monto_float
                    trx_procesada["categoria"] = "FINANCIAMIENTO"
                elif any(p in descripcion_limpia for p in PALABRAS_BMRCASH):
                    total_entradas_bmrcash += monto_float
                    trx_procesada["categoria"] = "BMRCASH"
                elif any(p in descripcion_limpia for p in PALABRAS_TRASPASO_MORATORIO):
                    total_moratorios += monto_float
                    trx_procesada["categoria"] = "MORATORIOS"
                else:
                    trx_procesada["categoria"] = "GENERAL" 
        
        elif tipo_detectado == "cargo":
            trx_procesada["categoria"] = "CARGO"

        todas_las_transacciones.append(trx_procesada)

    # 3. CÁLCULO DE TOTALES (Igual que antes)
    comisiones_str = ia_data_cuenta.get("comisiones", "0.0")
    if comisiones_str is None: comisiones_str = "0.0"
    comisiones = limpiar_monto(str(comisiones_str))
    
    entradas_TPV_neto = total_entradas_tpv - comisiones

    return {
        **ia_data_cuenta,
        "nombre_archivo_virtual": nombre_cuenta,
        "transacciones": todas_las_transacciones,
        "depositos_en_efectivo": total_depositos_efectivo,
        "traspaso_entre_cuentas": total_traspaso_entre_cuentas,
        "total_entradas_financiamiento": total_entradas_financiamiento,
        "entradas_bmrcash": total_entradas_bmrcash,
        "total_moratorios": total_moratorios,
        "entradas_TPV_bruto": total_entradas_tpv, 
        "entradas_TPV_neto": entradas_TPV_neto, 
        "error_transacciones": None
    }

async def procesar_documento_escaneado_con_agentes_async(
    ia_data: dict, 
    pdf_bytes: bytes, 
    filename: str
) -> List[Dict[str, Any]]: 
    
    logger.info(f"Iniciando procesamiento OCR-Visión para: {filename}")
    banco = ia_data.get("banco", "generico")
    
    # --- METADATA FECHAS ---
    p_inicio = ia_data.get("periodo_inicio")
    p_fin = ia_data.get("periodo_fin")
    
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            total_paginas = len(doc)
    except Exception:
        return [{**ia_data, "error_transacciones": "No se pudo leer el PDF (corrupto)."}]

    # Chunking por páginas
    TAMANO_CHUNK, SUPERPOSICION = 2, 1
    chunks_paginas = []
    i = 0
    while i < total_paginas:
        paginas = list(range(i + 1, min(i + TAMANO_CHUNK, total_paginas) + 1))
        if not paginas: break
        chunks_paginas.append(paginas)
        i += (TAMANO_CHUNK - SUPERPOSICION)

    # Llamadas a Agente
    tareas = [llamar_agente_ocr_vision(banco, pdf_bytes, pags) for pags in chunks_paginas]
    res_chunks = await asyncio.gather(*tareas, return_exceptions=True)

    # Consolidación
    transacciones_totales = []
    ids_unicos = set()
    for res in res_chunks:
        if not isinstance(res, Exception):
            for trx in res:
                id_trx = f"{trx.get('fecha')}-{trx.get('monto')}-{trx.get('descripcion', '')[:15]}"
                if id_trx not in ids_unicos:
                    transacciones_totales.append(trx)
                    ids_unicos.add(id_trx)

    # --- E. CLASIFICACIÓN DE NEGOCIO Y FECHAS ---
    total_depositos_efectivo = 0.0
    total_traspaso_entre_cuentas = 0.0
    total_entradas_financiamiento = 0.0
    total_entradas_bmrcash = 0.0
    total_moratorios = 0.0
    total_entradas_tpv = 0.0
    transacciones_clasificadas = []

    for trx in transacciones_totales:
        monto_float = trx.get("monto", 0.0)
        if not isinstance(monto_float, (int, float)):
            monto_float = limpiar_monto(str(monto_float))

        descripcion_limpia = trx.get("descripcion", "").lower()
        es_tpv_ia = trx.get("categoria", False)

        # --- CONSTRUIR FECHA ---
        dia_raw = trx.get("fecha")
        fecha_final = construir_fecha_completa(dia_raw, p_inicio, p_fin)

        trx_procesada = {
            "fecha": fecha_final, # Fecha formateada
            "descripcion": trx.get("descripcion"),
            "monto": f"{monto_float:,.2f}",
            "tipo": trx.get("tipo", "abono"),
            "categoria": "GENERAL"
        }

        tipo_trx = trx.get("tipo", "abono").lower()

        if "abono" in tipo_trx or "depósito" in tipo_trx:
            if any(p in descripcion_limpia for p in PALABRAS_EXCLUIDAS):
                pass 
            else:
                if any(p in descripcion_limpia for p in PALABRAS_EFECTIVO):
                    total_depositos_efectivo += monto_float
                    trx_procesada["categoria"] = "EFECTIVO"
                elif any(p in descripcion_limpia for p in PALABRAS_TRASPASO_ENTRE_CUENTAS):
                    total_traspaso_entre_cuentas += monto_float
                    trx_procesada["categoria"] = "TRASPASO"
                elif any(p in descripcion_limpia for p in PALABRAS_TRASPASO_FINANCIAMIENTO):
                    total_entradas_financiamiento += monto_float
                    trx_procesada["categoria"] = "FINANCIAMIENTO"
                elif any(p in descripcion_limpia for p in PALABRAS_BMRCASH):
                    total_entradas_bmrcash += monto_float
                    trx_procesada["categoria"] = "BMRCASH"
                elif any(p in descripcion_limpia for p in PALABRAS_TRASPASO_MORATORIO):
                    total_moratorios += monto_float
                    trx_procesada["categoria"] = "MORATORIOS"
                else:
                    # Lógica Doble Validación
                    if es_tpv_ia:
                        total_entradas_tpv += monto_float
                        trx_procesada["categoria"] = "TPV"
                    else:
                        trx_procesada["categoria"] = "GENERAL"
        
        elif "cargo" in tipo_trx or "retiro" in tipo_trx:
            trx_procesada["categoria"] = "CARGO"

        transacciones_clasificadas.append(trx_procesada)

    # --- F. ENSAMBLE FINAL ---
    comisiones_str = ia_data.get("comisiones", "0.0")
    if comisiones_str is None: comisiones_str = "0.0"
    comisiones = limpiar_monto(str(comisiones_str))
    
    entradas_TPV_neto = total_entradas_tpv - comisiones

    return [{
        **ia_data, 
        "nombre_archivo_virtual": filename,
        "transacciones": transacciones_clasificadas,
        "depositos_en_efectivo": total_depositos_efectivo,
        "traspaso_entre_cuentas": total_traspaso_entre_cuentas,
        "total_entradas_financiamiento": total_entradas_financiamiento,
        "entradas_bmrcash": total_entradas_bmrcash,
        "total_moratorios": total_moratorios,
        "entradas_TPV_bruto": total_entradas_tpv,
        "entradas_TPV_neto": entradas_TPV_neto,
        "error_transacciones": None
    }]

def procesar_digital_worker_sync(
    ia_data_inicial: dict, 
    texto_por_pagina_sucio: Dict[int, str], 
    movimientos_por_pagina: Dict[int, Any], 
    filename: str,
    file_path: str,
    rango_paginas: Tuple[int, int]
) -> Union[AnalisisTPV.ResultadoExtraccion, Exception]:
    
    # --- CLASE ADAPTADORA INTERNA ---
    # Usamos esto para convertir el dict del motor en el objeto que espera 
    # 'clasificar_transacciones_extraidas' (que usa .monto, .descripcion, etc.)
    class TransaccionAdapter:
        def __init__(self, data_dict):
            self.fecha = data_dict.get("fecha")
            self.descripcion = data_dict.get("descripcion")
            self.monto = data_dict.get("monto")
            self.tipo = data_dict.get("tipo") # String, ej: "CARGO"
            self.metodo_match = data_dict.get("metodo_match")
            self.coords_box = data_dict.get("coords_box")
    # --------------------------------

    try:
        # 1. DETERMINAR PÁGINAS
        start, end = rango_paginas
        lista_paginas = list(range(start, end + 1))
        
        # 2. INSTANCIAR Y EJECUTAR MOTOR
        engine = BankStatementEngine(debug_mode=False) 

        logger.info(f"Iniciando Motor v2 para {filename} en páginas {lista_paginas}")

        # OJO: Esto devuelve una lista de DICCIONARIOS
        resultados_paginas = engine.procesar_documento_entero(file_path, paginas=lista_paginas)

        # 3. APLANAR RESULTADOS Y RECOLECTAR MÉTRICAS (CORREGIDO)
        todas_las_transacciones_objs = []
        metricas_consolidado = []

        for res_pag in resultados_paginas:
            # CORRECCIÓN 1: Accedemos como Diccionario, no como objeto
            txs_dicts = res_pag.get("transacciones", [])
            
            # CORRECCIÓN 2: Convertimos los dicts a Objetos (Adapters)
            # porque 'clasificar_transacciones_extraidas' espera objetos con atributos
            for t_dict in txs_dicts:
                tx_obj = TransaccionAdapter(t_dict)
                todas_las_transacciones_objs.append(tx_obj)

            # CORRECCIÓN 3: Accedemos a métricas como Diccionario
            met_dict = res_pag.get("metricas", {})
            
            metricas_consolidado.append({
                "pagina": res_pag.get("pagina"),
                "tiempo_ms": met_dict.get("tiempo_procesamiento_ms", 0),
                "calidad_score": met_dict.get("calidad_promedio_pagina", 0),
                "metodo_predominante": "MIXTO",
                "bloques": met_dict.get("cantidad_bloques_detectados", 0),
                "transacciones": met_dict.get("cantidad_transacciones_finales", 0),
                "alertas": "; ".join(met_dict.get("alertas", [])) if met_dict.get("alertas") else "OK"
            })

        logger.info(f"Motor finalizado. Transacciones encontradas: {len(todas_las_transacciones_objs)}")

        # 4. CLASIFICACIÓN
        # Ahora 'todas_las_transacciones_objs' es una lista de objetos, no dicts.
        resultado_dict = clasificar_transacciones_extraidas(
            ia_data_inicial, 
            todas_las_transacciones_objs, 
            filename, 
            rango_paginas
        )
        
        # 5. INYECCIÓN AL DICCIONARIO
        resultado_dict["metadata_tecnica"] = metricas_consolidado 
        
        # 6. CREACIÓN DEL OBJETO RESULTADO
        obj_res = crear_objeto_resultado(resultado_dict) 
        
        # Restaurar campos excluidos manualmente
        obj_res.file_path_origen = file_path 
        
        return obj_res
        
    except Exception as e:
        logger.error(f"Error Worker Digital: {e}", exc_info=True) # Agregué exc_info para ver trace completo
        return e

def procesar_ocr_worker_sync(
    ia_data: dict, 
    file_path: str, #Recibe ruta
    filename: str
) -> Union[List[AnalisisTPV.ResultadoExtraccion], Exception]:
    try:
        # Leemos el archivo DESDE EL DISCO dentro del proceso worker
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()

        lista_dicts = asyncio.run(
            procesar_documento_escaneado_con_agentes_async(
                ia_data, pdf_bytes, filename
            )
        )
        return [crear_objeto_resultado(d) for d in lista_dicts]
    except Exception as e:
        logger.error(f"Error Worker OCR ({filename}): {e}", exc_info=True)
        return e
    
def extraer_datos_con_regex(texto: str, tipo_persona: str) -> Optional[Dict]:
    """
    Aplica los patrones de regex compilados, distinguiendo entre campos
    únicos (con search) y listas de campos (con findall).
    """
    patrones_a_usar = PATRONES_CONSTANCIAS_COMPILADO.get(tipo_persona)
    if not patrones_a_usar:
        return None

    datos_extraidos = {}

    # --- Procesamiento de Secciones ---
    for seccion_nombre, campos_compilados in patrones_a_usar.items():
        
        # Lógica para secciones que son LISTAS (Actividades y Regímenes)
        if seccion_nombre in ["actividades_economicas", "regimenes"]:
            lista_resultados = []
            # Asumimos que estas secciones tienen un solo patrón para findall
            # La clave es el singular de la sección (ej. 'actividad' o 'regimen')
            clave_patron = list(campos_compilados.keys())[0]
            logger.debug(f"Usando patrón {clave_patron}")

            patron = campos_compilados[clave_patron]
            logger.debug(f"Patrón: {patron.pattern}")
            
            matches = patron.findall(texto)
            logger.debug(f"Matches encontrados para {seccion_nombre}: {matches}")

            for match_tuple in matches:
                if seccion_nombre == "actividades_economicas":
                    # Mapea la tupla de la regex al diccionario del modelo
                    actividad_principal = match_tuple[1].strip()
                    if tipo_persona == "persona_moral":
                        continuacion_actividad = match_tuple[5].strip() if match_tuple[5] else ""
                        descripcion_completa = f"{actividad_principal} {continuacion_actividad}".strip()
                    
                    lista_resultados.append({
                        "orden": int(match_tuple[0]),
                        "act_economica": descripcion_completa if tipo_persona == "persona_moral" else actividad_principal,
                        "porcentaje": float(match_tuple[2]),
                        "fecha_inicio": match_tuple[3],
                        "fecha_final": match_tuple[4] if match_tuple[4] else None
                    })
                    logger.debug(f"Actividad añadida: {lista_resultados[-1]}")

                elif seccion_nombre == "regimenes":
                    nombre_regimen = match_tuple[0].strip()
                    if not any(char.isdigit() for char in nombre_regimen):
                        lista_resultados.append({
                            "nombre_regimen": nombre_regimen,
                            "fecha_inicio": match_tuple[1],
                            "fecha_fin": match_tuple[2] if match_tuple[2] else None
                        })
            datos_extraidos[seccion_nombre] = lista_resultados
        
        # Lógica para secciones que son DICCIONARIOS (Identificación y Domicilio)
        else:
            datos_seccion = {}
            for nombre_campo, patron in campos_compilados.items():
                match = patron.search(texto)
                logger.debug(f"Match para {nombre_campo}: {match}")
                if match:
                    # Usamos el primer grupo que no sea nulo
                    datos_seccion[nombre_campo] = match.group(1).strip()
            datos_extraidos[seccion_nombre] = datos_seccion

    # Verificación final: si no se extrajo el RFC, la operación no fue exitosa.
    if not datos_extraidos.get("identificacion_contribuyente", {}).get("rfc"):
        return None
        
    return datos_extraidos

# --- PROCESADOR PARA CONTANCIA DE SITUACIÓN FISCAL ---
async def procesar_constancia(archivo: UploadFile) -> CSF.ResultadoConsolidado:
    """
    Procesa un archivo de constancia de situación fiscal priorizando regex y usando la IA como fallback.
    Devuelve un objeto RestuladoConsolidado en caso de éxito o error_lectura_csf en caso de fallo.

    args:
        archivo (UploadFile) = Archivo de entrada proveniente del endpoint (en memoria).
    returns:
        RestuladoConsolidado = Objeto de la clase CSF con el formato a seguir para el json en respuesta del archivo.
    """
    resultado_final = CSF.ResultadoConsolidado()

    try:
        # 1. Extraemos el texto del pdf
        pdf_bytes = await archivo.read()
        texto = extraer_texto_de_pdf(pdf_bytes, num_paginas=2)

        if not texto:
            # Aqui se va a empezar la lógica por si es una iamgen
            raise ValueError("No se pudo extraer texto del PDF. Puede estar dañado o ser una imagen.")

        # 2. Definimos el tipo de persona
        tipo_persona = detectar_tipo_contribuyente(texto)
        logger.debug(f"Tipo de persona detectada: {tipo_persona}")

        if tipo_persona == "desconocido":
            return CSF.ResultadoConsolidado(
                error_lectura_csf=f"No se pudo determinar si '{archivo.filename}' es de una persona física o moral. Por favor, suba una CSF válida."
            )

        # Si es válido, continuamos con el flujo normal
        resultado_final = CSF.ResultadoConsolidado(
            tipo_persona=tipo_persona.replace("_", " ".title())
        )

        # Intento 1: Extracción con Regex
        datos_extraidos = extraer_datos_con_regex(texto, tipo_persona)
        logger.debug(f"Datos extraídos con Regex: {datos_extraidos}")
        
        # Intento 2: Fallback con IA si la Regex falló
        if not datos_extraidos:
            try:
                logger.info("--- Fallback a la IA activado ---")
                logger.warning("Se empezará la extracción de datos con IA.")
                datos_extraidos = await _extraer_datos_con_ia(texto)
            except Exception as e:
                logger.error(f"Error en el fallback de IA: {e}")
                return CSF.ErrorRespuesta("No se pudo extraer los datos de su archivo, intentelo más tarde.")

        # Mapeo de los datos extraídos a los modelos Pydantic
        if datos_extraidos:
            if tipo_persona == "persona_fisica":
                resultado_final.identificacion_contribuyente = CSF.DatosIdentificacionPersonaFisica(
                    **datos_extraidos.get("identificacion_contribuyente", {})
                )
            else:
                resultado_final.identificacion_contribuyente = CSF.DatosIdentificacionPersonaMoral(
                    **datos_extraidos.get("identificacion_contribuyente", {})
                )
            
            resultado_final.domicilio_registrado = CSF.DatosDomicilioRegistrado(
                **datos_extraidos.get("domicilio_registrado", {})
            )

            # Iteramos sobre la lista de actividades y creamos un objeto para cada una.
            actividades_data = datos_extraidos.get("actividades_economicas", [])
            if actividades_data:
                resultado_final.actividad_economica = [
                    CSF.ActividadEconomica(**actividad) for actividad in actividades_data
                ]

            # Hacemos lo mismo para la lista de regímenes.
            regimenes_data = datos_extraidos.get("regimenes", [])
            if regimenes_data:
                resultado_final.regimen_fiscal = [
                    CSF.Regimen(**regimen) for regimen in regimenes_data
                ]
    except Exception as e:
        resultado_final.error_lectura_csf = f"Error procesando '{archivo.filename}': {e}"

    return resultado_final