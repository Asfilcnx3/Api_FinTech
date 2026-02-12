import fitz
import re
import logging
import time
import unicodedata
import difflib
from typing import List, Dict, Tuple

from ..models.responses_motor_estados import RespuestasMotorEstados

logger = logging.getLogger(__name__)

### -------- ZONA DE REGEX ------------
# Regex para detectar líneas que empiezan con un número (posible día) seguido de texto
REGEX_DIA_INICIO = re.compile(r'^(\d{1,2})(\s+|$)(.*)')

# Regex para fechas tipo "01/JUL", "15/ENE" (Case insensitive) - Captura: Grupo 1 (Día), Grupo 2 (Mes)
REGEX_FECHA_BBVA = re.compile(r'\b(\d{1,2})\/([a-zA-Z]{3})\b', re.IGNORECASE)

# Regex para los meses en formato "MMM" (case insensitive)
MESES_REGEX = r"(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)"

# Regex de fecha simple para detectar "señales de vida" en el mapa geométrico (dd/mm o dd-mes)
REGEX_FECHA_SIMPLE = re.compile(r'\b\d{1,2}[/-](?:[0-9]{2}|[a-zA-Z]{3})', re.IGNORECASE)

# Regex de monto simple para detectar "señales de vida" en el mapa geométrico (número con punto decimal)
REGEX_MONTO_SIMPLE = re.compile(r'\d{1,3}(?:,\d{3})*\.\d{2}')

# Regex combinada para detectar formatos de fecha al inicio de línea (para segmentación)
PATRONES_FECHA_INICIO = [
    r"^\d{2}-[A-Z]{3}-\d{2}",    # 01-DIC-25 (Tu caso actual)
    r"^\d{2}/\d{2}/\d{4}",        # 01/12/2025
    r"^\d{2}/\d{2}/\d{2}",        # 01/12/25
    r"^\d{2}\s[A-Z]{3}",          # 01 DIC
    r"^\d{2}-[A-Z]{3}",           # 01-DIC
]
REGEX_FECHA_COMBINADA = re.compile("|".join(PATRONES_FECHA_INICIO), re.IGNORECASE)

# PATRONES DE FECHA CONOCIDOS (conforme se vayan descubriendo se deberán poner aqui)
PATRONES_FECHA = {
    "DD/MM/AAAA": re.compile(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b'),
    "DD/MM/AA":   re.compile(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2})\b'),
    "DD-MMM":     re.compile(r'\b(\d{1,2})[-/]([a-zA-Z]{3})\b', re.IGNORECASE), # 01-ENE, 01/ENE
    "DD/MMM":     re.compile(r'\b(\d{1,2})[-/]([a-zA-Z]{3})\b', re.IGNORECASE), # BBVA
    "DD MMM":     re.compile(rf'\b(\d{{1,2}})\s+{MESES_REGEX}\b', re.IGNORECASE),
    "MMM-DD":     re.compile(r'\b([a-zA-Z]{3})[-/](\d{1,2})\b', re.IGNORECASE), # ENE-01
    "DD_AISLADO": re.compile(r'^(\d{1,2})(\s+|$)') # Días sueltos al inicio de línea
}
# ---------- FIN DE ZONA REGEX -----------

class BankStatementEngine:
    def __init__(self, debug_mode=False):
        """Motor de procesamiento de estados de cuenta bancarios, con enfoque en robustez y trazabilidad."""
        self.metrics = {
            "total_paginas": 0,
            "tiempo_total": 0.0,
            "total_transacciones": 0,
            "transacciones_perfectas": 0,    # Match exacto (Texto + Geo)
            "transacciones_inferidas": 0,    # Match parcial (Geo o Texto)
            "transacciones_dudosas": 0,      # Match forzado/Guess
            "score_promedio": 0.0,           # 0 a 100
            "hit_rate": 0.0                  # % de éxito
        }
        self.errores = []
    
    # --------- FUNCIONES ORQUESTADORAS PRINCIPALES ---------
    def procesar_pagina_completa(
        self, 
        texto_pagina: str, 
        numero_pagina: int, 
        mapa_geo_completo: Dict,
        filename_debug: str
    ) -> "RespuestasMotorEstados.ResultadoPagina":
        """
        Orquesta todo el proceso para UNA página: Segmentación -> Reconciliación -> Métricas.
        """
        start_time = time.time()
        alertas = []
        
        # 1. Auto-detección de formatos (Podrías cachearlo a nivel clase si quisieras)
        # CORRECCIÓN DEL ERROR AQUÍ: Usamos self._detectar...
        formatos = self._detectar_formato_fecha_predominante(texto_pagina)
        
        # 2. Segmentación (Texto -> Bloques)
        bloques = self.segmentar_por_fechas(texto_pagina, numero_pagina, formatos)
        
        # 3. Reconciliación (Bloques + Geo -> Objetos Transacción)
        # Nota: Pasamos el mapa completo, la función filtra por número de página internamente
        transacciones_objs = self.reconciliar_geometria_con_bloques(bloques, mapa_geo_completo)
        
        # 4. Cálculo de Métricas
        end_time = time.time()
        tiempo_ms = (end_time - start_time) * 1000
        
        # Promedio de calidad
        total_score = sum(t.score_confianza for t in transacciones_objs)
        calidad_promedio = (total_score / len(transacciones_objs)) if transacciones_objs else 0.0
        
        # Detección de Alertas Simples
        if len(bloques) > 0 and len(transacciones_objs) == 0:
            alertas.append("BLOQUEO_TOTAL: Se detectó texto pero ninguna transacción válida.")
        if calidad_promedio < 0.6 and transacciones_objs:
            alertas.append("CALIDAD_BAJA: Muchas transacciones forzadas o inferidas.")

        # 5. Construcción de Respuesta Estructurada
        metricas = RespuestasMotorEstados.MetricasPagina(
            numero_pagina=numero_pagina,
            tiempo_procesamiento_ms=round(tiempo_ms, 2),
            cantidad_bloques_detectados=len(bloques),
            cantidad_transacciones_finales=len(transacciones_objs),
            calidad_promedio_pagina=round(calidad_promedio, 4),
            alertas=alertas
        )
        
        return RespuestasMotorEstados.ResultadoPagina(
            pagina=numero_pagina,
            metricas=metricas,
            transacciones=transacciones_objs
        )
    
    def procesar_documento_entero(self, pdf_path: str, paginas: List[int] = None) -> List["RespuestasMotorEstados.ResultadoPagina"]:
        """
        PIPELINE COMPLETO: Extracción -> Segmentación -> Geometría -> Reconciliación.
        Devuelve una lista de resultados por página.
        """
        resultados_totales = []
        
        # 1. Extracción (Usa el nuevo método integrado)
        logger.info(f"Iniciando extracción de texto para: {pdf_path}")
        textos = self.extraer_texto_con_crop(pdf_path, paginas)
        
        if not textos:
            return []
        
        paginas_a_procesar = list(textos.keys())
        
        # 2. Generación de Mapa Geométrico (Solo una vez para las páginas requeridas)
        # Nota: generar_mapa_montos_geometrico ya espera una lista de ints
        mapa_geo = self.generar_mapa_montos_geometrico(pdf_path, paginas_a_procesar)
        
        # 3. Procesamiento por página
        for num_pag, texto_limpio in textos.items():
            
            # Llamamos a tu orquestador de página existente
            # Nota: 'filename_debug' es algo que pedías en tu función original, 
            # puedes pasarlo o manejarlo de otra forma. Aquí paso el nombre del PDF.
            resultado_pag = self.procesar_pagina_completa(
                texto_pagina=texto_limpio,
                numero_pagina=num_pag,
                mapa_geo_completo=mapa_geo,
                filename_debug=pdf_path 
            )
            
            resultados_totales.append(resultado_pag)
            
            # Acumulamos métricas globales
            self.metrics["total_transacciones"] += resultado_pag.metricas.cantidad_transacciones_finales
            self.metrics["total_paginas"] += 1

        return resultados_totales
    # ------------------------------------------------------- 
    
    # --- 0. TEXT EXTRACTION (Fitz) ---
    def extraer_texto_con_crop(self, pdf_path: str, paginas: List[int] = None) -> Dict[int, str]:
        """
        Abre el PDF, aplica el recorte dinámico (usando la lógica interna de la clase)
        y normaliza el texto (NFC + limpieza de espacios).
        """
        texto_por_pagina = {}
        t_start = time.time()
        
        try:
            doc = fitz.open(pdf_path)
            total_doc_pages = len(doc)
            
            # Si no se especifican páginas, procesar todas
            if not paginas:
                paginas = range(1, total_doc_pages + 1)

            for num_pag in paginas:
                idx = num_pag - 1
                if idx >= total_doc_pages: 
                    continue
                
                page = doc[idx]
                
                # 1. CÁLCULO DINÁMICO (REUSANDO LÓGICA INTERNA)
                rect_crop = self._calcular_crop_dinamico(page)
                
                # 2. EXTRACCIÓN
                # sort=True es vital para que lea columnas (Izquierda -> Derecha, Arriba -> Abajo)
                texto_raw = page.get_text("text", clip=rect_crop, sort=True)
                
                # 3. NORMALIZACIÓN (Pipeline de limpieza)
                if texto_raw:
                    # A. Normalizar Unicode (ej. tildes separadas vs juntas)
                    texto_limpio = unicodedata.normalize('NFC', texto_raw)
                    
                    # B. Eliminar Non-breaking spaces (El veneno de Santander/Banregio)
                    texto_limpio = texto_limpio.replace('\xa0', ' ')
                    
                    # C. Limpieza de caracteres de control basura (opcional pero recomendado)
                    texto_limpio = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', texto_limpio)
                else:
                    texto_limpio = ""

                texto_por_pagina[num_pag] = texto_limpio

            doc.close()
            
            # Opcional: Registrar métrica interna
            self.metrics["tiempo_total"] += (time.time() - t_start)
            
        except Exception as e:
            logger.error(f"Error crítico extrayendo texto de {pdf_path}: {e}")
            return {}

        return texto_por_pagina

    # --- 1. DATE SLICER ---
    def segmentar_por_fechas(self, texto_pagina: str, numero_pagina: int, formatos_activos: List[str] = None) -> List[Dict]:
        """
        Segmenta el texto en bloques lógicos, aplicando un FILTRO ANTI-GHOSTING 
        para eliminar líneas duplicadas por capas de impresión del PDF.
        """
        
        # 1. Configuración de formatos
        if formatos_activos is None:
            formatos_activos = self._detectar_formato_fecha_predominante(texto_pagina)
            if not formatos_activos: 
                formatos_activos = ["DD/MM/AAAA", "DD-MMM", "DD/MMM", "DD MMM", "DD_AISLADO"]
        
        lineas_crudas = texto_pagina.split('\n')
        
        # --- FASE 1: LIMPIEZA DE ECOS (PRE-PROCESAMIENTO) ---
        lineas_unicas = []
        linea_prev = ""
        
        for linea in lineas_crudas:
            linea_limpia = linea.strip()
            if not linea_limpia: continue
            
            # Calculamos similitud con la línea inmediatamente anterior
            # Si es > 90% similar, asumimos que es un "fantasma" de impresión (negritas falsas)
            ratio = difflib.SequenceMatcher(None, linea_limpia, linea_prev).ratio()
            
            if ratio > 0.90:
                # Es un fantasma, la ignoramos.
                continue
                
            lineas_unicas.append(linea_limpia)
            linea_prev = linea_limpia

        # --- FASE 2: MÁQUINA DE ESTADOS (LOGIC ORIGINAL MEJORADA) ---
        bloques = []
        bloque_actual = None
        idx_interno = 0

        for linea in lineas_unicas:
            match_encontrado = None
            tipo_match = None

            # Probamos regex
            for fmt_key in formatos_activos:
                regex = PATRONES_FECHA[fmt_key]
                match = regex.match(linea) 
                
                if match:
                    if fmt_key == "DD_AISLADO":
                        posible_dia = int(match.group(1))
                        es_valido = (1 <= posible_dia <= 31)
                        if len(linea) < 6: es_valido = False # Filtro de ruido corto
                        
                        # Validación de dinero para fechas débiles ("02")
                        if es_valido:
                            tiene_monto = bool(REGEX_MONTO_SIMPLE.search(linea))
                            if not tiene_monto: es_valido = False
                            
                        if es_valido:
                            match_encontrado = match
                            tipo_match = fmt_key
                            break 
                    else:
                        match_encontrado = match
                        tipo_match = fmt_key
                        break
            
            if match_encontrado:
                # 1. CERRAR BLOQUE ANTERIOR
                if bloque_actual:
                    # IMPORTANTE: .copy() para romper la referencia de memoria
                    bloques.append(bloque_actual.copy())

                # 2. PREPARAR DATOS NUEVOS
                raw_fecha = match_encontrado.group(0)
                fecha_final = raw_fecha 

                if tipo_match == "DD_AISLADO":
                    dia_num = int(match_encontrado.group(1))
                    fecha_final = f"{dia_num:02d}"
                elif tipo_match == "DD MMM": 
                    dia = int(match_encontrado.group(1))
                    mes_str = match_encontrado.group(2).lower()
                    mapa_mes = {"ene":1,"feb":2,"mar":3,"abr":4,"may":5,"jun":6,"jul":7,"ago":8,"sep":9,"oct":10,"nov":11,"dic":12}
                    mes_num = mapa_mes.get(mes_str[:3], 0)
                    fecha_final = f"{dia:02d}/{mes_num:02d}"

                # 3. CREAR NUEVO BLOQUE (ID ÚNICO)
                bloque_actual = {
                    "id_unico": f"P{numero_pagina}_IDX{idx_interno}",
                    "fecha_detectada": fecha_final,
                    "texto_completo": linea,
                    "lineas": [linea],
                    "pagina": numero_pagina,
                    "formato_detectado": tipo_match
                }
                idx_interno += 1 # Incrementamos contador
            
            else:
                # CONTINUACIÓN
                if bloque_actual:
                    bloque_actual["texto_completo"] += " " + linea
                    bloque_actual["lineas"].append(linea)

        # Cierre final al salir del loop
        if bloque_actual:
            bloques.append(bloque_actual.copy())

        return bloques

    # --- 2. MAPA ESTELAR ---
    def generar_mapa_montos_geometrico(self, pdf_path: str, paginas: List[int]) -> Dict[int, Dict]:
        mapa_completo = {}
        try:
            with fitz.open(pdf_path) as doc:
                for num_pagina in paginas:
                    idx = num_pagina - 1
                    if idx >= len(doc): continue
                    
                    page = doc[idx]
                    width = page.rect.width
                    
                    # 1. Detectar columnas (Headers)
                    zonas = self._detectar_zonas_columnas(page)
                    
                    # DEFINICIÓN DE LÍMITES "BASE"
                    limite_fecha_x = width * 0.22      
                    limite_saldo_x_base = width * 0.78 # Default (15% Derecho aprox)
                    
                    # --- CORRECCIÓN DINÁMICA DE SALDO ---
                    # Si las zonas detectadas (Cargo/Abono) invaden la zona de saldo,
                    # empujamos el límite de saldo a la derecha para no "comer" montos válidos.
                    max_x_columnas = 0
                    if zonas.get("cargo"):
                        max_x_columnas = max(max_x_columnas, zonas["cargo"][1])
                    if zonas.get("abono"):
                        max_x_columnas = max(max_x_columnas, zonas["abono"][1])
                    
                    # Si la columna termina en 514 y el saldo empezaba en 477, 
                    # movemos el saldo a 514 + un buffer pequeño (ej. 10px).
                    if max_x_columnas > limite_saldo_x_base:
                        limite_saldo_real = max_x_columnas + 5
                    else:
                        limite_saldo_real = limite_saldo_x_base

                    zonas["fecha_limite_x"] = limite_fecha_x
                    zonas["saldo_limite_x"] = limite_saldo_real # Guardamos el real para debug

                    words = page.get_text("words")
                    numeros_encontrados = []
                    filas_fechas = []
                    
                    for w in words:
                        texto_raw = w[4].strip()
                        texto_clean = texto_raw.replace("$", "").replace(",", "")
                        x_centro = (w[0] + w[2]) / 2
                        y_centro = (w[1] + w[3]) / 2
                        
                        # --- A. Fechas (Solo izquierda) ---
                        es_fecha_regex = bool(REGEX_FECHA_COMBINADA.match(texto_raw))
                        es_fecha_bbva = bool(REGEX_FECHA_BBVA.match(texto_raw)) # BBVA
                        
                        # Detectar si es un día aislado (número 1-31)
                        es_dia_aislado = False
                        if texto_clean.isdigit() and len(texto_clean) <= 2:
                            val = int(texto_clean)
                            if 1 <= val <= 31:
                                es_dia_aislado = True

                        # SI ES FECHA O DÍA AISLADO EN ZONA IZQUIERDA
                        if (es_fecha_regex or es_fecha_bbva or es_dia_aislado) and x_centro <= limite_fecha_x:
                            filas_fechas.append({
                                "fecha_texto": texto_raw,
                                "y": y_centro,
                                "x": x_centro,
                                "y_min": w[1] - 2,
                                "y_max": w[3] + 2,
                                "es_dia_aislado": es_dia_aislado # Metadata útil
                            })
                        
                        # --- B. Números (Montos) ---
                        # (Esta lógica se mantiene igual, busca floats)
                        if "." in texto_clean and len(texto_clean) > 3 and texto_clean.replace(".", "").isdigit():
                            try:
                                valor = float(texto_clean)
                                tipo = "indefinido"
                                
                                # 1. ¿Es SALDO?
                                if x_centro >= limite_saldo_real:
                                    tipo = "saldo"
                                # 2. Columnas detectadas
                                elif zonas["cargo"] and zonas["cargo"][0] <= x_centro <= zonas["cargo"][1]:
                                    tipo = "cargo"
                                elif zonas["abono"] and zonas["abono"][0] <= x_centro <= zonas["abono"][1]:
                                    tipo = "abono"
                                
                                numeros_encontrados.append({
                                    "id_geo": f"{x_centro:.2f}_{y_centro:.2f}",
                                    "valor": valor,
                                    "x": x_centro,
                                    "y": y_centro,
                                    # INYECCIÓN: Guardamos el bounding box original (x0, y0, x1, y1)
                                    "coords_box": (w[0], w[1], w[2], w[3]), 
                                    "tipo": tipo,
                                    "usado": False
                                })
                            except ValueError:
                                continue

                    mapa_completo[num_pagina] = {
                        "numeros": numeros_encontrados,
                        "filas_fechas": filas_fechas,
                        "zonas_debug": zonas
                    }

        except Exception as e:
            logger.error(f"Error generando mapa geométrico: {e}")
            return {}

        return mapa_completo

    # --- 3. RECONCILIACIÓN (Lógica de consumo único) ---
    def reconciliar_geometria_con_bloques(self, bloques_texto: List[Dict], mapa_geometrico: Dict) -> List["RespuestasMotorEstados.TransaccionDetectada"]:
        transacciones_finales = []
        numeros_usados_ids = set()
        regex_monto_texto = re.compile(r'(\d{1,3}(?:,\d{3})*\.\d{2})')

        for bloque in bloques_texto:
            pag = bloque["pagina"]
            if pag not in mapa_geometrico: continue
                
            data_pag = mapa_geometrico[pag]
            zonas = data_pag.get("zonas_debug", {})
            
            filas_geo = sorted(data_pag["filas_fechas"], key=lambda k: k['y'])
            numeros_geo = sorted(data_pag["numeros"], key=lambda k: k['y'])
            
            # --- LIMPIEZA DE FECHA ---
            fecha_bloque_raw = bloque["fecha_detectada"].lower().strip()
            
            # 1. Si es BBVA (tiene letras)
            match_bbva = REGEX_FECHA_BBVA.match(fecha_bloque_raw)
            
            # 2.Si es Afirme Extraemos solo el número si viene sucio (por seguridad)
            match_dia = REGEX_DIA_INICIO.match(fecha_bloque_raw)
            
            if match_bbva:
                # Normalizamos para comparar: "01/jul"
                token_fecha_bloque = match_bbva.group(0).lower()

            elif match_dia:
                # Si el bloque dice "03 com", extraemos "03"
                # Si dice "3", extraemos "3" y le ponemos pad
                raw_num = int(match_dia.group(1))
                token_fecha_bloque = f"{raw_num:02d}"
            else:
                token_fecha_bloque = fecha_bloque_raw
            
            # --- PASO 1: ENCONTRAR ANCLA Y (GEOMETRÍA) ---
            y_bloque = None
            for fila in filas_geo:
                if fila.get("usada", False): continue
                
                fecha_geo = fila["fecha_texto"].lower().strip()
                
                # COMPARACIÓN RELAJADA:
                # 1. Coincidencia exacta ("03" == "03")
                # 2. Contención ("03/12" contiene "03")
                
                match_found = False
                if token_fecha_bloque == fecha_geo: # "03" == "03"
                    match_found = True
                elif token_fecha_bloque in fecha_geo or fecha_geo in token_fecha_bloque:
                    # Solo si longitudes son suficientes para evitar falsos positivos
                    if len(token_fecha_bloque) > 2 or len(fecha_geo) > 2:
                        match_found = True
                    # Si son cortos ("2" vs "12"), cuidado. Exigimos igualdad si son cortos.
                    elif token_fecha_bloque == fecha_geo: 
                        match_found = True

                if match_found:
                    y_bloque = fila["y"]
                    fila["usada"] = True 
                    break
            
            # --- PASO 2: LOGICA DE FUSION (Si no hay ancla, buscar montos en texto) ---
            if y_bloque is None:
                montos_en_texto = regex_monto_texto.findall(bloque["texto_completo"])
                
                # Se debe usar dot notation (.) en lugar de brackets [""]
                if not montos_en_texto and transacciones_finales:
                    # Accedemos al último objeto Pydantic de la lista
                    transacciones_finales[-1].descripcion += " " + bloque["texto_completo"]
                    continue
                elif not montos_en_texto:
                    continue
                else:
                    y_bloque = -1 # Estrategia Texto Puro

            # --- PASO 3: CAZAR EL NÚMERO (Estrategia Espacial vs Texto) ---
            monto_final = 0.0
            tipo_final = "indefinido"
            match_status = "MISS_MONTO"
            mejor_candidato = None

            # Estrategia A: Espacial (Filtrando Saldos)
            candidatos_espaciales = []
            if y_bloque != -1:
                # --- TOLERANCIA DINÁMICA ---
                # Calculamos cuántas líneas tiene el bloque de texto
                cantidad_lineas = len(bloque.get("lineas", []))
                
                # Altura promedio de línea en PDF (usualmente 10-14pt). 
                # Le damos 15 por seguridad.
                pixels_por_linea = 15 
                
                # El rango de búsqueda debe ser:
                # Desde: Un poco arriba de la fecha (y_bloque - 15)
                # Hasta: La fecha + (número de líneas * altura) + un buffer extra
                y_min_search = y_bloque - 15
                y_max_search = y_bloque + (cantidad_lineas * pixels_por_linea) + 15
                
                candidatos_espaciales = [
                    n for n in numeros_geo 
                    if y_min_search <= n["y"] <= y_max_search
                    and n["id_geo"] not in numeros_usados_ids
                    and n["tipo"] != "saldo" # Ignoramos saldo
                ]

            # Estrategia B: Valor Exacto (Textual)
            valores_texto = []
            strs_montos = regex_monto_texto.findall(bloque["texto_completo"])
            for s in strs_montos:
                try:
                    # Limpieza de comas y espacios antes de convertir
                    v = float(s.replace(",", "").replace(" ", ""))
                    # Ignoramos montos cero encontrados en el texto (ej. "IVA: 0.00")
                    if v > 0.01:
                        valores_texto.append(v)
                except: pass
                
            # Ordenamos de MAYOR a MENOR. 
            # Queremos intentar casar primero el monto principal (2,500) antes que comisiones o saldos menores.
            valores_texto.sort(reverse=True)
            
            candidato_valor_exacto = None
            for val_txt in valores_texto:
                for n in numeros_geo:
                    # Verificamos coincidencia
                    if (n["id_geo"] not in numeros_usados_ids 
                        and abs(n["valor"] - val_txt) < 0.01
                        and n["tipo"] != "saldo"): 
                        
                        candidato_valor_exacto = n
                        break 
                if candidato_valor_exacto: break

            # DECISIÓN
            if candidato_valor_exacto:
                mejor_candidato = candidato_valor_exacto
                match_status = "OK_TEXT_MATCH"

            elif candidatos_espaciales:
                # 1. Filtramos candidatos que explícitamente sean saldo (por si se coló alguno)
                candidatos_validos = [c for c in candidatos_espaciales if c["tipo"] != "saldo"]
                
                if not candidatos_validos:
                    # Si todos eran saldo, no hay nada que hacer
                    mejor_candidato = None
                else:
                    # 2. Intentamos buscar por clasificación explícita (Cargo/Abono detectado por headers)
                    clasificados = [c for c in candidatos_validos if c["tipo"] != "indefinido"]
                    
                    if clasificados:
                        # Si hay clasificados, tomamos el primero (prioridad a columnas detectadas)
                        # Ordenamos por X para asegurar izquierda-derecha
                        clasificados.sort(key=lambda x: x["x"])
                        mejor_candidato = clasificados[0]
                        match_status = "OK_SPATIAL_CLASS"
                    
                    else:
                        # 3. CASO CRÍTICO (BBVA): Todos son "indefinidos".
                        # AQUÍ ESTABA EL ERROR: Antes usabas max(valor).
                        # AHORA: Usamos el que esté más a la IZQUIERDA (menor X).
                        # Porque el orden es: [Cargo/Abono] -> [Saldo]
                        
                        candidatos_validos.sort(key=lambda k: k["x"]) # Ordenar por posición X
                        mejor_candidato = candidatos_validos[0]       # Tomar el primero (izquierda)
                        
                        match_status = "OK_LEFTMOST_GUESS" # "WARN_SPATIAL_INDEF"

            # ASIGNACIÓN
            if mejor_candidato:
                monto_final = mejor_candidato["valor"]
                tipo_final = mejor_candidato["tipo"]
                numeros_usados_ids.add(mejor_candidato["id_geo"])

                if tipo_final == "indefinido":
                    x_cand = mejor_candidato["x"]
                    zona_c = zonas.get("cargo")
                    zona_a = zonas.get("abono")
                    TOLERANCIA_X = 50 
                    
                    if zona_c and (zona_c[0] - TOLERANCIA_X) <= x_cand <= (zona_c[1] + TOLERANCIA_X):
                        tipo_final = "cargo"
                    elif zona_a and (zona_a[0] - TOLERANCIA_X) <= x_cand <= (zona_a[1] + TOLERANCIA_X):
                        tipo_final = "abono"
                    else:
                        if x_cand < 400: tipo_final = "cargo"
                        else: tipo_final = "abono"

            # --- PASO 4: GARBAGE COLLECTOR INTELIGENTE (GHOSTBUSTER) ---
            if monto_final == 0.0 and match_status == "MISS_MONTO":
                if transacciones_finales:
                    # Acceso a objeto Pydantic
                    tx_prev = transacciones_finales[-1]
                    desc_prev = tx_prev.descripcion  # Dot notation
                    desc_actual = bloque["texto_completo"] # Esto sí es dict (viene de segmentar)
                    
                    # --- CHECK DE FANTASMA ---
                    # 1. Si la descripción actual está contenida en la anterior (duplicado exacto o parcial)
                    if desc_actual in desc_prev:
                        continue # Es un fantasma, lo ignoramos por completo
                    
                    # 2. Si son muy similares (ej. > 80% parecido) usando SequenceMatcher
                    # Esto detecta "23/OCT Compra" vs "23/OCT Compra." (con punto extra)
                    ratio = difflib.SequenceMatcher(None, desc_prev, desc_actual).ratio()
                    if ratio > 0.8:
                        continue # Es un fantasma casi idéntico, lo ignoramos

                    # Si NO es un fantasma, entonces sí es información nueva (ej. continuación real)
                    tx_prev.descripcion += " " + desc_actual
                    continue
                else:
                    # Si es la primera transacción y no tiene monto, la ignoramos porque no tenemos nada a qué compararla (podría ser un encabezado o algo sin valor)
                    continue

            # --- AQUÍ EMPIEZA LA INYECCIÓN DE SCORE (Sustituyendo la creación del dict 'tx' de la V3) ---
            # 1. Determinar Score y Enum
            score_calculado = 0.5 # Default
            metodo_enum = RespuestasMotorEstados.MetodoExtraccion.FORZADO
            
            if match_status == "OK_TEXT_MATCH":
                score_calculado = 1.0
                metodo_enum = RespuestasMotorEstados.MetodoExtraccion.EXACTO_TEXTO
            elif match_status == "OK_SPATIAL_CLASS":
                score_calculado = 0.9
                metodo_enum = RespuestasMotorEstados.MetodoExtraccion.EXACTO_GEO_COLUMNA
            elif match_status == "OK_LEFTMOST_GUESS":
                score_calculado = 0.7
                metodo_enum = RespuestasMotorEstados.MetodoExtraccion.INFERENCIA_GEO
            
            # 2. Mapeo de Tipo string a Enum
            tipo_enum = RespuestasMotorEstados.TipoTransaccion.INDEFINIDO
            if tipo_final in ["cargo", "abono", "saldo"]:
                tipo_enum = RespuestasMotorEstados.TipoTransaccion(tipo_final)

            # 3. Creación del Objeto Pydantic (Validación estricta)
            try:
                tx_obj = RespuestasMotorEstados.TransaccionDetectada(
                    fecha=token_fecha_bloque,
                    descripcion=bloque["texto_completo"],
                    monto=monto_final,
                    tipo=tipo_enum,
                    id_interno=bloque["id_unico"],
                    score_confianza=score_calculado,
                    metodo_match=metodo_enum,
                    coords_box = mejor_candidato.get("coords_box") if mejor_candidato else None,
                    errores=[]          # Por ahora no tenemos errores
                )
                transacciones_finales.append(tx_obj)
            
            except Exception as e:
                logger.error(f"Error creando objeto transacción {bloque['id_unico']}: {e}")
                # Se agrega a lista de errores de la clase
                RespuestasMotorEstados.TransaccionDetectada(
                    fecha=token_fecha_bloque,
                    descripcion=bloque["texto_completo"],
                    monto=0.0,
                    tipo=RespuestasMotorEstados.TipoTransaccion.INDEFINIDO,
                    id_interno=bloque["id_unico"],
                    score_confianza=0.0,
                    metodo_match=RespuestasMotorEstados.MetodoExtraccion.MANUAL,
                    coords_box=None,
                    errores=[RespuestasMotorEstados.ErrorRespuesta(
                        codigo_error="TRANSACCION_INVALIDA",
                        mensaje=f"Error al crear objeto de transacción: {e}"
                    )]
                )
            # --- FIN DE LA INYECCIÓN ---

        return transacciones_finales
    
    # --- FUNCIONES AUXILIARES DE DETECCIÓN DINÁMICA ---

    def _detectar_zonas_columnas(self, page: fitz.Page) -> Dict[str, Tuple[float, float]]:
        """
        Escanea la página (priorizando el tercio superior RECALCULADO) buscando encabezados 
        de columnas para definir las zonas X de 'cargo' y 'abono'.
        """
        # Importación dentro para evitar ciclos si es necesario, o mover arriba
        from ..utils.helpers_texto_fluxo import KEYWORDS_COLUMNAS 
        
        ancho_pag = page.rect.width
        zonas = {
            "cargo": None, 
            "abono": None, 
            "fecha_columna": (0, ancho_pag * 0.22)
        }
        
        # IMPORTANTE: Ahora buscamos headers en una zona más amplia
        # Porque el crop dinámico nos asegura que tenemos contenido, 
        # pero a veces los headers están un poco más abajo de lo usual.
        rect_header = fitz.Rect(0, 0, ancho_pag, page.rect.height * 0.40)
        words = page.get_text("words", clip=rect_header)
        
        candidatos = []

        for w in words:
            texto = w[4].lower().replace(":", "").replace(".", "").strip()
            x0, x1 = w[0], w[2]
            
            if texto in KEYWORDS_COLUMNAS["cargo"]:
                candidatos.append({"tipo": "cargo", "x0": x0, "x1": x1, "y": w[1]})
                
            elif texto in KEYWORDS_COLUMNAS["abono"]:
                candidatos.append({"tipo": "abono", "x0": x0, "x1": x1, "y": w[1]})

        margen_expansion = 25 

        for c in candidatos:
            zona_tupla = (c["x0"] - margen_expansion, c["x1"] + margen_expansion)
            if zonas[c["tipo"]] is None:
                zonas[c["tipo"]] = zona_tupla

        centro_pag = ancho_pag / 2
        if zonas["cargo"] and not zonas["abono"]:
            if zonas["cargo"][1] < centro_pag: 
                zonas["abono"] = (centro_pag, ancho_pag)
                
        elif zonas["abono"] and not zonas["cargo"]:
            if zonas["abono"][0] > centro_pag: 
                zonas["cargo"] = (0, centro_pag)

        return zonas

    def _calcular_crop_dinamico(self, page: fitz.Page) -> fitz.Rect:
        """
        Escanea la página buscando 'señales de vida' (fechas y montos).
        Devuelve un rectángulo ajustado al contenido real, ignorando headers lejanos y footers.
        """
        rect_original = page.rect
        words = page.get_text("words")
        
        if not words:
            return rect_original

        min_y_detectado = rect_original.height  # Empezamos desde abajo
        max_y_detectado = 0.0                   # Empezamos desde arriba
        
        encontro_datos = False

        for w in words:
            texto = w[4].strip()
            
            # HEURÍSTICA 1: ¿Parece una fecha? (dd/mm o dd-mes)
            es_fecha = bool(REGEX_FECHA_SIMPLE.search(texto))
            
            # HEURÍSTICA 2: ¿Parece un monto? (tiene punto decimal y dígitos)
            # Evitamos números de página simples (ej: "1", "45") pidiendo el punto decimal.
            es_monto = bool(REGEX_MONTO_SIMPLE.search(texto))
            
            if es_fecha or es_monto:
                y0, y1 = w[1], w[3]
                
                # Actualizamos los límites del "mapa de calor"
                if y0 < min_y_detectado: min_y_detectado = y0
                if y1 > max_y_detectado: max_y_detectado = y1
                encontro_datos = True

        # --- DEFINICIÓN DE MÁRGENES ---
        if not encontro_datos:
            # Fallback: Si no detectamos nada (página vacía o imagen), devolvemos crop estándar
            # Margen 5% arriba y abajo
            return fitz.Rect(0, rect_original.height * 0.05, rect_original.width, rect_original.height * 0.95)

        # BÚFER DE SEGURIDAD
        # Arriba: Necesitamos espacio para los Headers de columna (Saldo, Cargo, etc.)
        # Si la primera fecha está en Y=200, subimos 150px para atrapar los headers.
        BUFFER_SUPERIOR = 120 
        
        # Abajo: Solo necesitamos un poquito extra por si el monto tiene colita (ej. letras 'g', 'j', 'p')
        BUFFER_INFERIOR = 10 

        y_final_top = max(0, min_y_detectado - BUFFER_SUPERIOR)
        y_final_bottom = min(rect_original.height, max_y_detectado + BUFFER_INFERIOR)

        # --- VALIDACIÓN DE SEGURIDAD ---
        # Si el crop resultante es ridículamente pequeño (ej. < 100px), algo salió mal.
        if (y_final_bottom - y_final_top) < 100:
            return rect_original

        return fitz.Rect(0, y_final_top, rect_original.width, y_final_bottom)

    def _detectar_formato_fecha_predominante(self, texto_muestra: str) -> List[str]:
        """
        Analiza el texto y devuelve una lista de claves de formatos detectados
        ordenados por frecuencia.
        """
        conteo = {k: 0 for k in PATRONES_FECHA.keys()}
        
        # Muestreo rápido
        lineas = texto_muestra.split('\n')[:200] # Analizar primeras 200 líneas es suficiente
        
        for linea in lineas:
            linea = linea.strip()
            if not linea: continue
            
            for clave, regex in PATRONES_FECHA.items():
                if regex.search(linea):
                    conteo[clave] += 1
                    
        # Filtramos los que tengan 0 hits y ordenamos por popularidad
        detectados = sorted(
            [k for k, v in conteo.items() if v > 0],
            key=lambda k: conteo[k],
            reverse=True
        )
        
        # "DD_AISLADO" es peligroso, solo lo devolvemos si es el ÚNICO o el MUY dominante
        if "DD_AISLADO" in detectados:
            # Si hay formatos fuertes (DD/MM/AAAA), preferimos esos aunque haya menos
            formatos_fuertes = [f for f in detectados if f != "DD_AISLADO"]
            if formatos_fuertes:
                return formatos_fuertes + ["DD_AISLADO"]
                
        return detectados