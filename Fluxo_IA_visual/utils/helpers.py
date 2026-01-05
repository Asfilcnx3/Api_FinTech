from ..models.responses import AnalisisTPV, NomiFlash
from .helpers_texto_fluxo import (
    BANCO_DETECTION_REGEX, ALIAS_A_BANCO_MAP, PATRONES_COMPILADOS, PALABRAS_CLAVE_VERIFICACION, PROMPT_GENERICO, PROMPT_OCR_INSTRUCCIONES_BASE, PROMPT_TEXTO_INSTRUCCIONES_BASE, PROMPTS_POR_BANCO
)
from .helpers_texto_nomi import CAMPOS_FLOAT, CAMPOS_STR, PATTERNS_COMPILADOS_RFC_CURP, RFCS_INSTITUCIONES_IGNORAR

from dateutil.relativedelta import relativedelta
from typing import Tuple, List, Any, Dict, Union, Optional, Literal
import json
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)

def extraer_unico(d: dict, clave: str) -> Union[str, None]:
    """
    Extrae el primer dato de lo encontrado en la función "extraer_datos_por_banco"
    """
    lista = d.get(clave, [])
    return lista[0] if lista else None

def extraer_datos_por_banco(texto: str) -> Dict[str, Any]:
    """
    Analiza el texto para identificar el banco y luego extrae datos específicos
    (como RFC, comisiones, depósitos, etc.) usando la configuración para ese banco.
    """
    resultados = {
        "banco": None,
        "rfc": None,
        "comisiones": None,
        "depositos": None, 
    }

    if not texto:
        return resultados

    # --- 1. Identificar el banco ---
    match_banco = BANCO_DETECTION_REGEX.search(texto)
    if not match_banco:
        return resultados

    banco_estandarizado = ALIAS_A_BANCO_MAP.get(match_banco.group(0))
    resultados["banco"] = banco_estandarizado.upper()

    patrones_del_banco = PATRONES_COMPILADOS.get(banco_estandarizado)
    if not patrones_del_banco:
        return resultados

    # --- 2. Extraer datos crudos con findall ---
    datos_crudos = {}
    for clave, patron in patrones_del_banco.items():
        datos_crudos[clave] = re.findall(patron, texto)

    # --- 3. Procesar resultados con extraer_unico ---
    for nombre_clave in patrones_del_banco.keys():
        valor_capturado = extraer_unico(datos_crudos, nombre_clave)

        if valor_capturado:
            # Si el campo es numérico
            if nombre_clave in ["comisiones", "depositos", "cargos", "saldo_promedio"]:
                try:
                    monto_limpio = str(valor_capturado).replace(",", "").replace("$", "").strip()
                    resultados[nombre_clave] = float(monto_limpio)
                except (ValueError, TypeError):
                    resultados[nombre_clave] = None
            else:  
                resultados[nombre_clave] = str(valor_capturado).upper()

    return resultados

def sumar_lista_montos(montos: List[str]) -> float:
    """
    Convierte una lista de montos en formato de cadena a float y los suma.

    Args:
        montos (List[str]): Lista de montos a sumar.

    Returns:
        float: La suma de los montos.
    """
    total = 0.0
    for monto in montos:
        monto_limpio = monto.replace(',', '').strip()
        try:
            total += float(monto_limpio)
        except ValueError:
            continue
    return total

def extraer_json_del_markdown(respuesta: str) -> Dict[str, Any]:
    """
    EXTRAE EL TEXTO DEL JSON QUE RETORNA LA IA
    Encuentra lo que está dentro de "{}" y retorna un diccionario manejable

    Args:
        respuesta (str): Texto con el json interno

    Returns:
        Dict[str, Any]: Diccionario con las llaves manejables
    """
    logger.debug(respuesta)
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', respuesta, re.DOTALL)
    json_string = json_match.group(1) if json_match else respuesta
    try:
        logger.debug("Json encontrado")
        return json.loads(json_string)
    except json.JSONDecodeError:
        logger.debug(f"El modelo no devolvió un JSON válido. Respuesta: {respuesta[:200]}...")
        return {}
# --- FUNCIÓN PARA EXTRAER RFC Y CURP DE TEXTO ---
def extraer_rfc_curp_por_texto(texto: str, tipo_doc: str) -> Tuple[List[str], List[str]]:
    """
    Busca RFC y/o CURP filtrando RFCs institucionales (bancos).
    """
    if not texto or not tipo_doc:
        logger.error("Texto o tipo de documento no proporcionado.")
        return [], []

    rfcs, curps = [], []
    tipo_doc_key = tipo_doc.lower()

    # --- BUSCAR RFCs ---
    # Asumimos que PATTERNS_COMPILADOS_RFC_CURP existe en el contexto global
    patron_rfc = PATTERNS_COMPILADOS_RFC_CURP["RFC"].get(tipo_doc_key)
    
    if patron_rfc:
        for match in patron_rfc.finditer(texto):
            valor_encontrado = match.group(1)
            
            if valor_encontrado:
                valor_limpio = valor_encontrado.upper()
                
                # --- NUEVA REGLA DE NEGOCIO ---
                # Si el RFC encontrado está en la lista negra, lo ignoramos y seguimos buscando.
                if valor_limpio in RFCS_INSTITUCIONES_IGNORAR:
                    logger.debug(f"RFC Institucional detectado e ignorado: {valor_limpio}")
                    continue
                
                # Si no es un banco, lo guardamos
                rfcs.append(valor_limpio)
                logger.info(f"RFC válido encontrado: {valor_limpio}")
    
    # --- BUSCAR CURPs ---
    patron_curp = PATTERNS_COMPILADOS_RFC_CURP["CURP"].get(tipo_doc_key)
    
    if patron_curp:
        for match in patron_curp.finditer(texto):
            valor_encontrado = match.group(1)
            
            if valor_encontrado:
                valor_limpio = valor_encontrado.upper()
                curps.append(valor_limpio)

    return rfcs, curps
    
def es_escaneado_o_no(texto_extraido: str, umbral: int = 50) -> bool:
    """
    Extrae el texto dado en Bytes y verifica si el texto extraído es válido usando una prueba de dos factores:
    1. Debe tener una longitud mínima.
    2. Debe contener palabras clave relevantes de un estado de cuenta.
    
    Esto previene falsos positivos con PDFs escaneados que generan texto basura.
    """
    if not texto_extraido:
        return False
    logger.debug(f"El texto extraido de las primera páginas es: {len(texto_extraido.strip())}")

    texto_limpio = texto_extraido.strip()
    
    # Prueba 1: ¿Supera la longitud mínima?
    pasa_longitud = len(texto_limpio) > umbral
    
    # Prueba 2: ¿Contiene palabras clave con sentido?
    pasa_contenido = bool(PALABRAS_CLAVE_VERIFICACION.search(texto_limpio))

    return pasa_longitud and pasa_contenido

def parsear_respuesta_toon(texto_toon: str) -> List[Dict[str, Any]]:
    """
    Convierte el formato TOON (texto delimitado por pipes) a una lista de diccionarios.
    Formato esperado por línea: FECHA | DESCRIPCION | MONTO | TIPO
    """
    transacciones = []
    
    # Limpiamos bloques de código si el LLM los puso (```text ... ```)
    texto_limpio = re.sub(r'^```\w*\n|```$', '', texto_toon.strip(), flags=re.MULTILINE).strip()
    
    lineas = texto_limpio.split('\n')
    
    for linea in lineas:
        linea = linea.strip()
        if not linea: continue # Saltar líneas vacías
        
        # Ignorar encabezados si el LLM los generó (ej. "Fecha | Desc...")
        if "fecha" in linea.lower() and "monto" in linea.lower() and "|" in linea:
            continue

        partes = linea.split('|')
        
        # Esperamos 4 o 5 partes. Si hay más (ej. pipe en la descripción), intentamos unirlas
        if len(partes) < 4: # Mínimo fecha, desc, monto
            logger.debug(f"Línea TOON ignorada (formato incorrecto): {linea}")
            continue
            
        try:
            fecha = partes[0].strip()
            
            # El último es la etiqueta, el penúltimo el tipo
            etiqueta_raw = partes[-1].strip().upper() # "TPV" o "GENERAL"
            tipo_raw = partes[-2].strip().lower()
            monto_str = partes[-3].strip()
            
            # Descripción es lo que sobra en medio
            descripcion = " ".join(p.strip() for p in partes[1:-3])
            
            # Normalización de tipo
            tipo = "abono" if "abono" in tipo_raw else "cargo" if "cargo" in tipo_raw else "indefinido"
            
            # Validación de etiqueta (fallback por seguridad)
            es_tpv_ia = "TPV" in etiqueta_raw

            transacciones.append({
                "fecha": fecha,
                "descripcion": descripcion,
                "monto": monto_str,
                "tipo": tipo,
                "categoria": es_tpv_ia
            })
            
        except Exception as e:
            logger.warning(f"Error parseando línea TOON: '{linea}' - {e}")
            continue

    return transacciones

# Funciones para procesar las descripciones de los bancos
# fecha, descripción o parte de esta, monto
def _procesar_banorte(t): return " ".join(t[1:-1]), t[-1]
def _procesar_afirme(t): return " ".join(t[1:-1]), t[-1]
def _procesar_hsbc(t): return " ".join(t[1:-1]), t[-1]
def _procesar_santander(t): return " ".join(t[1:-1]), t[-1]

# fecha, descripción, monto, final de la descripción
def _procesar_bbva(t): return " ".join([t[1], t[-1]]), t[-2]
def _procesar_multiva(t): return " ".join([t[1], t[2], t[-1]]), t[-2]
def _procesar_intercam(t): return " ".join([t[1], t[2], t[-1]]), t[-2]

# fecha, transacción, monto
def _procesar_banregio(t): return " ".join([t[1]]), t[-1]
def _procesar_banamex(t): return " ".join([t[1]]), t[-1]

# fecha, transaccion, monto
def _procesar_scotiabank(t): return " ".join([t[1]]), t[-1]

# Monto, final de transacción, inicio de transacción, monto, mitad de transacción
def _procesar_mifel(t): return " ".join([t[2], t[-1], t[1]]), t[-2]

# monto, final de transacción, inicio de transacción, monto
def _procesar_bajio(t): return " ".join([t[2], t[1]]), t[-1]

# monto, final de transacción, inicio de transacción, monto
def _procesar_azteca(t): return " ".join([t[1], t[-1]]), t[-2]
def _procesar_inbursa(t): return " ".join([t[1], t[-1]]), t[-2]

# Creamos el despachador de descripción dependiendo el banco
DESPACHADOR_DESCRIPCION = {
    "banbajío": _procesar_bajio,
    "banorte": _procesar_banorte,
    "afirme": _procesar_afirme,
    "hsbc": _procesar_hsbc,
    "mifel": _procesar_mifel,
    "scotiabank": _procesar_scotiabank,
    "banregio": _procesar_banregio,
    "santander": _procesar_santander,
    "bbva": _procesar_bbva,
    "multiva": _procesar_multiva,
    "citibanamex": _procesar_banamex,
    "banamex": _procesar_banamex,
    "intercam": _procesar_intercam,
    "azteca": _procesar_azteca,
    "inbursa": _procesar_inbursa
}

def construir_descripcion_optimizado(transaccion: Tuple, banco: str) -> Tuple[str, str]:
    # Busca la función correcta en el diccionario y la ejecuta.
    # Proporciona una función por defecto si el banco no se encuentra.
    funcion_procesadora = DESPACHADOR_DESCRIPCION.get(banco.lower(), lambda t: ("", "0.0"))
    return funcion_procesadora(transaccion)

def reconciliar_resultados_ia(res_gpt: dict, res_gemini:dict) -> dict:
    """
    Compara dos diccionarios de resultados de la IA y devuelve el mejor consolidado
    con una lógica de reconciliación inteligente.
    """
    resultado_final = {}
    # Una forma más limpia de obtener todos los campos únicos de ambos diccionarios
    todos_los_campos = set(res_gpt.keys()) | set(res_gemini.keys())

    # Define qué campos deben ser tratados como números
    CAMPOS_NUMERICOS = {"comisiones", "depositos", "cargos", "saldo_promedio"}

    for campo in todos_los_campos:
        valor_gpt = res_gpt.get(campo)
        valor_gemini = res_gemini.get(campo)

        # --- LÓGICA PARA TOMAR EL MAYOR ---
        
        if campo in CAMPOS_NUMERICOS:
            # Aseguramos que los valores sean numéricos, convirtiendo None a 0.0 para la comparación.
            num_gpt = valor_gpt if valor_gpt is not None else 0.0
            num_gemini = valor_gemini if valor_gemini is not None else 0.0
            resultado_final[campo] = max(num_gpt, num_gemini)

        else:
            # 1. Limpiar y normalizar los valores: convertir strings vacíos a None
            v_gpt = valor_gpt.strip() if isinstance(valor_gpt, str) and valor_gpt.strip() else None
            v_gemini = valor_gemini.strip() if isinstance(valor_gemini, str) and valor_gemini.strip() else None
            
            # 2. Decidir cuál es el mejor valor
            if v_gpt and v_gemini:
                # Si ambos tienen un valor, elegimos el más largo (más completo)
                # Como desempate, preferimos GPT.
                if len(v_gpt) >= len(v_gemini):
                    resultado_final[campo] = v_gpt
                else:
                    resultado_final[campo] = v_gemini
            elif v_gpt:
                # Si solo GPT tiene un valor, lo usamos
                resultado_final[campo] = v_gpt
            elif v_gemini:
                # Si solo Gemini tiene un valor, lo usamos
                resultado_final[campo] = v_gemini
            else:
                # Si ninguno tiene un valor, el resultado es None
                resultado_final[campo] = None
    
    return resultado_final

def sanitizar_datos_ia(datos_crudos: Dict[str, Any]) -> Dict[str, Any]:
    """
    Toma el diccionario crudo de la IA y asegura que los tipos de datos
    sean los correctos para el modelo Pydantic.
    """
    if not datos_crudos:
        return {}

    datos_limpios = datos_crudos.copy()

    # --- Forzar campos a ser STRINGS ---
    # Campos que deben ser strings (incluso si la IA los devuelve como números)
    for campo in CAMPOS_STR:
        if campo in datos_limpios and datos_limpios[campo] is not None:
            datos_limpios[campo] = str(datos_limpios[campo])

    # --- Forzar campos a ser FLOATS ---
    # Campos que deben ser números limpios
    for campo in CAMPOS_FLOAT:
        if campo in datos_limpios:
            datos_limpios[campo] = limpiar_monto(datos_limpios[campo])
            
    return datos_limpios

def total_depositos_verificacion(
    resultados_portada: List[Union[Tuple[Dict, bool, str], Exception]]
) -> Tuple[float, bool]:
    """
    Suma los depósitos de una lista de resultados de análisis con IA.
    """
    total_depositos = 0.0
    for resultado in resultados_portada:
        if isinstance(resultado, Exception): continue
        lista_cuentas, _, _, _, _, _ = resultado
        for cuenta in lista_cuentas:
            depo = cuenta.get("depositos", 0) or 0
            total_depositos += float(depo)

    es_mayor = total_depositos >= 250_000
    return total_depositos, es_mayor

def limpiar_monto(monto: Any) -> float:
    """
    Convierte un monto de cualquier tipo (string, int, float) a un float limpio.
    Maneja de forma segura valores como '$1,234.56', 1234, 1234.56, y None.
    """
    # Si ya es un número, simplemente lo convertimos a float y lo devolvemos.
    if isinstance(monto, (int, float)):
        return float(monto)

    # Si es un string, aplicamos la lógica de limpieza.
    if isinstance(monto, str):
        # Elimina el símbolo de moneda, comas y espacios
        monto_limpio = monto.replace('$', '').replace(',', '').strip()
        try:
            return float(monto_limpio)
        except ValueError:
            # Esto ocurre si el string está vacío o no es numérico después de limpiar
            return 0.0
            
    # Si no es ni número ni string (ej. None), devolvemos 0.0
    return 0.0

def limpiar_y_normalizar_texto(texto: str) -> str:
    """
    Limpia y normaliza el texto extraído de un PDF.
    1. Colapsa múltiples espacios o saltos de línea entre palabras a un solo espacio.
    """
    if not texto:
        return ""

    # Reemplaza secuencias de 2 o más espacios/tabs con un solo espacio.
    texto_normalizado = re.sub(r'[ \t]{2,}', ' ', texto)
    return texto_normalizado.strip()

def crear_chunks_con_superposicion(
    texto_por_pagina: Dict[int, str], 
    paginas_con_movimientos: List[int], 
    tamano_chunk: int = 5, 
    superposicion: int = 1
) -> List[Tuple[str, List[int]]]:
    """
    Crea chunks de texto con superposición, usando solo las páginas que 
    sabemos que tienen movimientos para no procesar portadas.
    """
    chunks = []
    # Filtramos las páginas para procesar solo las que tienen movimientos
    paginas_a_procesar = sorted([p_num for p_num in texto_por_pagina.keys() if p_num in paginas_con_movimientos])
    
    if not paginas_a_procesar:
        return []

    i = 0
    while i < len(paginas_a_procesar):
        # Define el inicio y fin del chunk
        inicio_idx = i
        fin_idx = i + tamano_chunk
        
        # Obtiene los números de página para este chunk
        paginas_en_chunk = paginas_a_procesar[inicio_idx:fin_idx]
        
        if not paginas_en_chunk:
            break
            
        # Crea el contenido de texto para el chunk
        texto_chunk = "".join([texto_por_pagina[p_num] for p_num in paginas_en_chunk])
        
        chunks.append((texto_chunk, paginas_en_chunk))
        
        # Avanza para el siguiente chunk, retrocediendo la superposición
        i += (tamano_chunk - superposicion)
        
    return chunks

def _crear_prompt_agente_unificado(
        banco: str, 
        tipo: Literal["texto", "vision"]
    ) -> str:
    """
    Genera el prompt de sistema para el agente de extracción de TPV,
    combinando las instrucciones específicas del banco con la base de 
    instrucciones correcta (texto o visión).
    """
    banco_key = banco.lower().strip()
    
    # 1. Seleccionar la Introducción y las Instrucciones Base según el tipo
    if tipo == "texto":
        intro = f"Eres un agente de IA experto en analizar TEXTO de estados de cuenta del banco {banco}."
        instrucciones_base = PROMPT_TEXTO_INSTRUCCIONES_BASE
    else: # tipo == "vision"
        intro = f"Eres un agente de IA experto en analizar IMÁGENES de estados de cuenta escaneados del banco {banco}."
        instrucciones_base = PROMPT_OCR_INSTRUCCIONES_BASE
        
    # 2. Buscar las pistas específicas del banco
    # Si no se encuentra, simplemente no se añaden pistas extra.
    pistas_especificas = PROMPTS_POR_BANCO.get(banco_key, PROMPT_GENERICO)

    # 3. Construir el prompt final
    prompt_final = f"""
    {intro}
    
    TU OBJETIVO PRINCIPAL:
    1. Analizar el documento completo.
    2. Extraer TODAS las transacciones visibles (Cargos y Abonos).
    3. Clasificar cada transacción en la columna `ETIQUETA` usando las reglas del banco.

    --- REGLAS DE CLASIFICACIÓN PARA '{banco}' ---
    Si una transacción cumple CUALQUIERA de las siguientes condiciones estrictas, su `ETIQUETA` debe ser "TPV".
    Si NO cumple ninguna, su `ETIQUETA` debe ser "GENERAL".

    {pistas_especificas}
    --------------------------------------------------

    {instrucciones_base}
    """
    return prompt_final.strip()

def crear_objeto_resultado(datos_dict: dict) -> AnalisisTPV.ResultadoExtraccion: # no estamos usandola (identificar si se usará o eliminar)
    """
    Transforma un diccionario plano de resultados en un objeto Pydantic
    ResultadoExtraccion completamente estructurado y anidado.
    """
    try:
        # 1. Creamos el sub-objeto AnalisisIA
        analisis_ia = AnalisisTPV.ResultadoAnalisisIA(
            banco=datos_dict.get("banco"),
            tipo_moneda=datos_dict.get("tipo_moneda"),
            rfc=datos_dict.get("rfc"),
            nombre_cliente=datos_dict.get("nombre_cliente"),
            clabe_interbancaria=datos_dict.get("clabe_interbancaria"),
            periodo_inicio=datos_dict.get("periodo_inicio"),
            periodo_fin=datos_dict.get("periodo_fin"),
            comisiones=datos_dict.get("comisiones"),
            depositos=datos_dict.get("depositos"),
            cargos=datos_dict.get("cargos"),
            saldo_promedio=datos_dict.get("saldo_promedio"),
            depositos_en_efectivo=datos_dict.get("depositos_en_efectivo"),
            traspaso_entre_cuentas=datos_dict.get("traspaso_entre_cuentas"),
            total_entradas_financiamiento=datos_dict.get("total_entradas_financiamiento"),
            entradas_bmrcash=datos_dict.get("entradas_bmrcash"),
            total_moratorios=datos_dict.get("total_moratorios"),
            entradas_TPV_bruto=datos_dict.get("entradas_TPV_bruto"),
            entradas_TPV_neto=datos_dict.get("entradas_TPV_neto"),
        )

        # 2. Creamos el sub-objeto DetalleTransacciones
        detalle_transacciones = AnalisisTPV.ResultadoTPV(
            transacciones=datos_dict.get("transacciones", []),
            error_transacciones=datos_dict.get("error_transacciones")
        )

        # 3. Ensamblamos y devolvemos el objeto principal
        return AnalisisTPV.ResultadoExtraccion(
            AnalisisIA=analisis_ia,
            DetalleTransacciones=detalle_transacciones
        )
    except Exception as e:
        # Si algo falla en la creación del modelo, devolvemos un objeto de error
        return AnalisisTPV.ResultadoExtraccion(
            AnalisisIA=None,
            DetalleTransacciones=AnalisisTPV.ErrorRespuesta(error=f"Error al estructurar el diccionario de respuesta: {e}")
        )
    
def construir_fecha_completa(dia_raw: str, periodo_inicio_str: str, periodo_fin_str: str) -> str:
    """
    Recibe un día (ej: "02", "15") y las fechas del periodo (metadata).
    Devuelve la fecha completa formateada (dd/mm/yyyy).
    """
    # 1. Limpieza básica del día
    if not dia_raw: return ""
    
    # Intentamos obtener solo los dígitos del día
    dia_str = "".join(filter(str.isdigit, str(dia_raw)))
    if not dia_str: return str(dia_raw) # Si no hay números, devolvemos lo que llegó
    
    try:
        dia_int = int(dia_str)
    except:
        return str(dia_raw)

    # 2. Parseo de fechas del periodo (Asumimos formato dd/mm/yyyy o yyyy-mm-dd)
    # Ajusta los formatos según cómo los devuelva tu función de metadata
    def parse_fecha(f_str):
        if not f_str: return None
        # Intentamos formatos comunes
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(str(f_str).strip(), fmt)
            except ValueError:
                continue
        return None

    dt_inicio = parse_fecha(periodo_inicio_str)
    dt_fin = parse_fecha(periodo_fin_str)

    # 3. Lógica de asignación de Mes/Año
    # Si no tenemos metadata, devolvemos solo el día (fallback)
    if not dt_inicio: 
        return f"{dia_int:02d}/??/????"

    # Si solo tenemos inicio (o inicio y fin son el mismo mes/año), es fácil
    mes = dt_inicio.month
    anio = dt_inicio.year

    if dt_fin:
        # CASO COMPLEJO: El periodo cruza meses (Ej: 15 Dic a 14 Ene)
        if dt_inicio.month != dt_fin.month:
            # Heurística: Si el día extraído es mayor o igual al día de inicio, 
            # probablemente pertenece al primer mes. Si es menor, al segundo.
            # Ej: Periodo 15/12 al 14/01. Día "20" -> 20/12. Día "05" -> 05/01.
            if dia_int >= dt_inicio.day:
                mes = dt_inicio.month
                anio = dt_inicio.year
            else:
                mes = dt_fin.month
                anio = dt_fin.year
    
    # 4. Construcción final
    try:
        # Creamos la fecha para validar que sea real (ej: evitar 30 de Febrero)
        fecha_completa = datetime(year=anio, month=mes, day=dia_int)
        return fecha_completa.strftime("%d/%m/%Y")
    except ValueError:
        # Si el día es inválido (ej: 32), devolvemos error controlado
        return f"{dia_int:02d}/{mes:02d}/{anio} (Fecha Inválida)"
        
# --- FUNCIONES AUXILIARES NOMIFLASH ---
def verificar_fecha_comprobante(fecha_str: Optional[str]) -> Optional[bool]:
    """
    Verifica si una fecha en formato 'AAAA-MM-DD' es de los últimos 3 meses.
    """
    if not fecha_str:
        return None
    
    try:
        # Convertimos el string a un objeto de fecha
        fecha_comprobante = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        
        # Obtenemos la fecha de hoy y la de hace 3 meses
        fecha_hoy = datetime.now().date()
        fecha_limite = fecha_hoy - relativedelta(months=3)
        
        # Comparamos
        return fecha_comprobante >= fecha_limite
        
    except (ValueError, TypeError):
        # Si la fecha tiene un formato incorrecto, no podemos validarla
        return None
    
def aplicar_reglas_de_negocio(resultado: NomiFlash.ResultadoConsolidado) -> NomiFlash.ResultadoConsolidado:
    """
    Aplica las reglas de negocio finales a un objeto ResultadoConsolidado.
    """
    # Si no hay objetos que procesar, devuelve el resultado tal cual
    if not resultado:
        return resultado

    # --- Regla 1: Verificación de la fecha del comprobante ---
    if resultado.Comprobante and resultado.Comprobante.fin_periodo:
        resultado.es_menor_a_3_meses = verificar_fecha_comprobante(resultado.Comprobante.fin_periodo)

    # --- Regla 2: Verificación de coincidencia de RFC ---
    # Se ejecuta solo si tenemos los datos de Nómina y Estado, y ambos tienen un RFC.
    if (resultado.Nomina and resultado.Nomina.rfc and resultado.Estado and resultado.Estado.rfc):
        resultado.el_rfc_es_igual = (resultado.Nomina.rfc.upper() == resultado.Estado.rfc.upper())

    # # --- Regla 3: Verificación de coincidencia de QR ---
    # Se ejecuta solo si tenemos los datos de Nómina y Estado, y ambos tienen un CURP.
    if (resultado.Nomina and resultado.Nomina.datos_qr and resultado.SegundaNomina and resultado.SegundaNomina.datos_qr):
        resultado.el_qr_es_igual = (resultado.Nomina.datos_qr.upper() == resultado.SegundaNomina.datos_qr.upper())
            
    return resultado

# ---- FUNCIONES AUXILIARES PARA CSF ----
def detectar_tipo_contribuyente(texto: str) -> str:
    """
    Detecta si el CSF pertenece a una persona física o moral.
    Basandose en la presencia de campos específicos.
    """
    # La presencia de "curp" es el indicador más fiable para Persona Física.
    if "curp" in texto:
        return "persona_fisica"
    
    # La presencia de "razón social" o "régimen capital" es para Persona Moral.
    if re.search(r"raz[oó]n social|r[ée]gimen capital", texto):
        return "persona_moral"

    # Si no se encuentra ninguno de los indicadores clave, es desconocido.
    return "desconocido"