# services/orchestators.py

from ..utils.helpers import (
    limpiar_monto, detectar_tipo_contribuyente, crear_objeto_resultado,
    construir_fecha_completa, separar_fecha_y_ruido, calcular_periodo
    
)
from .ia_extractor import (
    _extraer_datos_con_ia
)
from ..utils.helpers_texto_fluxo import (
    PALABRAS_BMRCASH, PALABRAS_EXCLUIDAS, PALABRAS_EFECTIVO, PALABRAS_TRASPASO_ENTRE_CUENTAS, PALABRAS_TRASPASO_FINANCIAMIENTO, PALABRAS_TRASPASO_MORATORIO
)

from ..utils.helpers_texto_csf import (
    PATRONES_CONSTANCIAS_COMPILADO
)

from .pdf_processor import (
    extraer_texto_de_pdf
)

from ..core.spatial_bank import MotorExtraccionEspacial
from ..models.responses_motor_estados import RespuestasMotorEstados

from ..models.responses_analisisTPV import AnalisisTPV
from ..models.responses_csf import CSF

from ..core.textract_engine import extraer_documento_completo, extraer_saldo_inicial_poc
from ..core.extractor_determinista import ExtractorDeterministaOCR

from fastapi import UploadFile
from ..core.nomiflash_engine import NomiFlashEngine
from ..models.responses_nomiflash import NomiFlash

from typing import Dict, Any, Tuple, Optional, Union, List
from fastapi import UploadFile
import logging
import fitz
import time

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
        # --- ACCESO POR ATRIBUTOS ---
        monto_float = trx.monto  
        # 1. SEPARAMOS LA FECHA SUCIA DE LA BASURA
        fecha_pura_raw, basura_texto = separar_fecha_y_ruido(trx.fecha)
        
        # 2. INYECTAMOS LA BASURA AL INICIO DE LA DESCRIPCIÓN
        desc_original = trx.descripcion
        if basura_texto:
            # "COMISION" + " " + "09740650D"
            descripcion_full = f"{basura_texto} {desc_original}".strip()
        else:
            descripcion_full = desc_original.strip()
            
        descripcion_limpia = descripcion_full.lower() # Para las reglas de negocio
        
        # Manejo seguro del Enum de tipo
        tipo_detectado = trx.tipo.value if hasattr(trx.tipo, 'value') else str(trx.tipo)
        
        # 3. CONSTRUIMOS LA FECHA USANDO SOLO LA PARTE LIMPIA
        # Tu función 'construir_fecha_completa' ahora recibe "01-DIC-25", que sabe manejar perfecto.
        fecha_final = construir_fecha_completa(fecha_pura_raw, p_inicio, p_fin)
        
        # 4. CALCULAMOS EL PERIODO
        periodo_calculado = calcular_periodo(fecha_final, p_inicio)
        
        trx_procesada = {
            "fecha": fecha_final,
            "periodo": periodo_calculado,
            "descripcion": descripcion_full,
            "monto": f"{monto_float:,.2f}", 
            "tipo": tipo_detectado,
            "categoria": "GENERAL",
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

def procesar_ocr_worker_sync(
    ia_data: dict, 
    file_path: str, 
    filename: str
) -> Union[AnalisisTPV.ResultadoExtraccion, Exception]:
    
    # --- CLASE ADAPTADORA INTERNA ---
    class TransaccionAdapterOCR:
        """Adapta la salida del POC a la estructura que requiere el clasificador."""
        def __init__(self, data_dict):
            self.fecha = data_dict.get("fecha", "")
            self.descripcion = data_dict.get("descripcion", "")
            
            # El clasificador de negocio espera 'monto', pero la POC entrega 'importe'
            self.monto = float(data_dict.get("importe", 0.0))
            
            raw_tipo = data_dict.get("tipo", "INDEFINIDO")
            self.tipo = str(raw_tipo).upper() if raw_tipo else "INDEFINIDO"
            
            self.metodo_match = "TEXTRACT_DETERMINISTA" 
            self.coords_box = None
            self.id_interno = "OCR_TX"
            self.score_confianza = 0.95 

    try:
        logger.info(f"[TextractWorker] Iniciando POC Determinista para: {filename}")
        
        # 1. Extracción concurrente con AWS Textract
        filas_estructuradas, textos_crudos = extraer_documento_completo(file_path)
        
        if not filas_estructuradas:
            raise ValueError("Textract no devolvió información útil o falló la conversión del PDF.")
            
        # 2. Buscar el saldo inicial (Arranque)
        saldo_arranque = extraer_saldo_inicial_poc(textos_crudos)
        
        # 3. Procesamiento y reglas deterministas
        extractor = ExtractorDeterministaOCR()
        transacciones_brutas = extractor.procesar_transacciones(filas_estructuradas, saldo_arranque)
        transacciones_limpias = extractor.deduplicar_transacciones(transacciones_brutas)
        
        logger.info(f"[TextractWorker] Transacciones extraídas y deduplicadas: {len(transacciones_limpias)}")
        
        # 4. Adaptación al formato del clasificador de negocio
        transacciones_objetos = [TransaccionAdapterOCR(tx) for tx in transacciones_limpias]
        
        # 5. Clasificación de negocio (tu función existente)
        # Aquí pasamos (1, 999) como dummy, ya que Textract analizó el documento completo
        rango_paginas_dummy = (1, 999) 
        resultado_dict = clasificar_transacciones_extraidas(
            ia_data_cuenta=ia_data, 
            transacciones_objetos=transacciones_objetos, 
            filename=filename, 
            rango_paginas=rango_paginas_dummy
        )
        
        # 6. Inyección de Metadata técnica (Para no romper el modelo Pydantic)
        resultado_dict["metadata_tecnica"] = [{
            "pagina": 1,
            "tiempo_ms": 0,
            "calidad_score": 1.0,
            "metodo_predominante": "TEXTRACT_DETERMINISTA",
            "bloques": len(transacciones_limpias),
            "transacciones": len(transacciones_limpias),
            "alertas": "Procesado con motor OCR Determinista AWS"
        }]
        
        # 7. Creación del objeto final
        obj_res = crear_objeto_resultado(resultado_dict) 
        
        # 8. Restauramos campos de trazabilidad
        obj_res.file_path_origen = file_path
        obj_res.es_digital = False
        
        return obj_res
        
    except Exception as e:
        logger.error(f"Error Worker OCR Textract ({filename}): {e}", exc_info=True)
        return e

def procesar_digital_worker_sync(
    ia_data_inicial: dict,
    filename: str,
    file_path: str,
    rango_paginas: Tuple[int, int]
) -> Union[Any, Exception]: # Retorna AnalisisTPV.ResultadoExtraccion o Exception
    
    # --- CLASE ADAPTADORA INTERNA ---
    class TransaccionAdapter:
        """Adapta el dict del Motor V2 al objeto que espera el clasificador de negocio."""
        def __init__(self, data_dict):
            self.fecha = data_dict.get("fecha", "")
            self.descripcion = data_dict.get("descripcion", "")
            self.monto = data_dict.get("monto", 0.0)
            
            # Normalización de TIPO
            raw_tipo = data_dict.get("tipo", "INDEFINIDO")
            if isinstance(raw_tipo, str):
                self.tipo = raw_tipo.upper()
            else:
                self.tipo = "INDEFINIDO"
            
            # Metadatos técnicos
            self.metodo_match = "SPATIAL_V2" # Hardcodeamos el origen
            self.coords_box = data_dict.get("coords_box", []) 
            self.id_interno = data_dict.get("id_interno", "")
            self.score_confianza = data_dict.get("score_confianza", 1.0)

    try:
        logger.info(f"[DigitalWorker] Iniciando Motor V2 para: {filename}")

        # 1. INSTANCIAR MOTOR V2 (PRODUCCIÓN)
        # CORRECCIÓN IMPORTANTE: En el nuevo motor no existe 'debug_mode'.
        # Pasamos debug_flags=[] para que corra en silencio y rápido (solo logs INFO).
        banco_origen = ia_data_inicial.get("banco", "GENERICO")
        engine = MotorExtraccionEspacial(debug_flags=[], banco=banco_origen)

        # --- INICIO DEL CRONÓMETRO ---
        t_inicio = time.time()

        # 2. EJECUCIÓN DEL PIPELINE (3 PASADAS)
        # Usamos un bloque try/finally para asegurar que el PDF se cierra en memoria
        doc = fitz.open(file_path)
        try:
            # Pasada 1: Geometría (Header/Footer)
            geometries = engine.pass_1_detect_geometry(doc)
            
            # Pasada 2: Columnas (Detección horizontal)
            layouts = engine.pass_2_detect_columns(doc, geometries)
            
            # Pasada 3: Extracción (Slicing y Datos)
            raw_results = engine.pass_3_extract_rows(doc, geometries, layouts)
        finally:
            doc.close()

        # --- FIN DEL CRONÓMETRO Y CÁLCULO PROMEDIO ---
        t_fin = time.time()
        tiempo_total_ms = (t_fin - t_inicio) * 1000
        
        start_pg, end_pg = rango_paginas
        pags_procesadas = (end_pg - start_pg) + 1
        tiempo_promedio_pagina_ms = int(tiempo_total_ms / pags_procesadas) if pags_procesadas > 0 else int(tiempo_total_ms)

        # 3. APLANAR RESULTADOS Y FILTRAR POR PÁGINA
        todas_las_transacciones_objs = []
        metricas_consolidado = []
        total_tx_count = 0

        for i, res_pag in enumerate(raw_results):
            # El motor devuelve índice 1-based en 'page'
            page_num = res_pag.get("page", i + 1)
            
            # Filtro de rango de páginas
            if not (start_pg <= page_num <= end_pg):
                continue

            txs_dicts = res_pag.get("transacciones", [])
            
            # Convertir a Adapters
            for t_dict in txs_dicts:
                tx_obj = TransaccionAdapter(t_dict)
                todas_las_transacciones_objs.append(tx_obj)
            
            total_tx_count += len(txs_dicts)

            # Construir métricas técnicas para el reporte final
            metricas_consolidado.append({
                "pagina": page_num,
                "tiempo_ms": tiempo_promedio_pagina_ms, # <--- Actualizamos con el tiempo real
                "calidad_score": 1.0 if layouts[i].has_explicit_headers else 0.5,
                "metodo_predominante": "SPATIAL_V2",
                "bloques": len(txs_dicts),
                "transacciones": len(txs_dicts),
                "alertas": "Layout Heredado" if not layouts[i].has_explicit_headers else "OK"
            })

        logger.info(f"[DigitalWorker] Motor V2 finalizado. Transacciones: {total_tx_count}")

        # 4. CLASIFICACIÓN DE NEGOCIO
        # (Llama a tu función existente de reglas de negocio)
        resultado_dict = clasificar_transacciones_extraidas(
            ia_data_cuenta=ia_data_inicial, 
            transacciones_objetos=todas_las_transacciones_objs, 
            filename=filename, 
            rango_paginas=rango_paginas
        )
        
        # 5. INYECCIÓN DE METADATA TÉCNICA
        resultado_dict["metadata_tecnica"] = metricas_consolidado 
        
        # 6. CREACIÓN DEL OBJETO RESULTADO FINAL
        # (Llama a tu función existente que convierte el dict en objeto Pydantic/Dataclass)
        obj_res = crear_objeto_resultado(resultado_dict) 
        
        # Restaurar campos de trazabilidad
        obj_res.file_path_origen = file_path 
        
        return obj_res
        
    except Exception as e:
        logger.error(f"Error Crítico en Worker Digital (Motor V2): {e}", exc_info=True)
        # Retornamos la excepción para que el orquestador superior decida qué hacer
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