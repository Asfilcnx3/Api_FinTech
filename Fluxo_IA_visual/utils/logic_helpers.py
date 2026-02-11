import fitz
import re
import logging
from typing import List, Dict
from .helpers_texto_fluxo import REGEX_FECHA_COMBINADA
from ..services.pdf_processor import detectar_zonas_columnas

logger = logging.getLogger(__name__)

# Regex para detectar líneas que empiezan con un número (posible día) seguido de texto
REGEX_DIA_INICIO = re.compile(r'^(\d{1,2})(\s+|$)(.*)')

# Regex para fechas tipo "01/JUL", "15/ENE" (Case insensitive)
# Captura: Grupo 1 (Día), Grupo 2 (Mes)
REGEX_FECHA_BBVA = re.compile(r'\b(\d{1,2})\/([a-zA-Z]{3})\b', re.IGNORECASE)

# Mapa de meses para conversión rápida (BBVA usa español)
MESES_ESP = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12
}

# --- 1. DATE SLICER ---
def segmentar_por_fechas(texto_pagina: str, numero_pagina: int) -> List[Dict]:
    lineas = texto_pagina.split('\n')
    bloques = []
    bloque_actual = None
    idx_interno = 0
    
    # Bandera de estado: ¿Hemos detectado que esta página es formato BBVA?
    modo_bbva_detectado = False

    for linea in lineas:
        linea_limpia = linea.strip()
        if not linea_limpia: continue

        # --- MATCHES ---
        match_full = REGEX_FECHA_COMBINADA.match(linea_limpia)
        match_dia = REGEX_DIA_INICIO.match(linea_limpia)
        match_bbva = REGEX_FECHA_BBVA.match(linea_limpia)

        # --- ARBITRAJE: ¿Es fecha real o un falso positivo? ---
        es_fecha_fuerte = False
        if match_full:
            if re.search(r'[/|-]|(\sde\s)', match_full.group(0)):
                es_fecha_fuerte = True

        # --- LÓGICA DE CORTE ---

        # CASO A: FECHA BBVA (DD/MMM) <--- PRIORIDAD MÁXIMA
        if match_bbva:
            # ACTIVAMOS MODO BBVA: A partir de aquí, somos estrictos.
            modo_bbva_detectado = True 
            
            if bloque_actual: bloques.append(bloque_actual)
            
            fecha_raw = match_bbva.group(0) # "01/JUL"
            
            bloque_actual = {
                "id_unico": f"P{numero_pagina}_IDX{idx_interno}",
                "fecha_detectada": fecha_raw,
                "texto_completo": linea_limpia,
                "lineas": [linea_limpia],
                "pagina": numero_pagina
            }
            idx_interno += 1

        # CASO B: Fecha Completa y Fuerte (Ej: 12/12/2025)
        elif match_full and es_fecha_fuerte:
            if bloque_actual: bloques.append(bloque_actual)
            
            fecha_str = match_full.group(0)
            bloque_actual = {
                "id_unico": f"P{numero_pagina}_IDX{idx_interno}",
                "fecha_detectada": fecha_str,
                "texto_completo": linea_limpia,
                "lineas": [linea_limpia],
                "pagina": numero_pagina
            }
            idx_interno += 1

        # CASO C: Día Aislado (Ej: "03 comvta...", "15 compra...")
        elif match_dia:
            # --- CORRECCIÓN CRÍTICA ---
            # Si ya detectamos formato BBVA en esta página, NO aceptamos "días aislados" (números solos).
            # En BBVA, una nueva transacción SIEMPRE empieza con DD/MMM.
            # Si empieza con un número (ej: "1 DOM..."), es descripción de la anterior.
            if modo_bbva_detectado:
                # Es descripción (Falso positivo de fecha)
                if bloque_actual:
                    bloque_actual["texto_completo"] += " " + linea_limpia
                    bloque_actual["lineas"].append(linea_limpia)
                continue # Saltamos al siguiente ciclo

            # Lógica estándar para otros bancos (Afirme, etc.)
            posible_dia = int(match_dia.group(1))

            # Filtro anti-ruido genérico
            es_dia_valido = (1 <= posible_dia <= 31)
            
            # Filtro extra: Si es un solo dígito sin cero (ej: "1" en vez de "01"), desconfiamos
            # a menos que estemos seguros de que no es BBVA.
            txt_dia = match_dia.group(1)
            if len(txt_dia) == 1 and len(linea_limpia) > 50:
                # Ej: "1 DOM FAIRPLAY..." es muy largo para ser un header de fecha simple tipo "1 PAGO"
                es_dia_valido = False

            if es_dia_valido:
                if bloque_actual: bloques.append(bloque_actual)

                fecha_limpia = f"{posible_dia:02d}"
                
                bloque_actual = {
                    "id_unico": f"P{numero_pagina}_IDX{idx_interno}",
                    "fecha_detectada": fecha_limpia, 
                    "texto_completo": linea_limpia, 
                    "lineas": [linea_limpia],
                    "pagina": numero_pagina
                }
                idx_interno += 1
            else:
                # Falso positivo -> Se pega al anterior
                if bloque_actual:
                    bloque_actual["texto_completo"] += " " + linea_limpia
                    bloque_actual["lineas"].append(linea_limpia)
        
        # CASO D: Texto normal (Descripción)
        else:
            if bloque_actual:
                bloque_actual["texto_completo"] += " " + linea_limpia
                bloque_actual["lineas"].append(linea_limpia)

    if bloque_actual:
        bloques.append(bloque_actual)
        
    return bloques

# --- 2. MAPA ESTELAR ---
def generar_mapa_montos_geometrico(pdf_path: str, paginas: List[int]) -> Dict[int, Dict]:
    mapa_completo = {}
    try:
        with fitz.open(pdf_path) as doc:
            for num_pagina in paginas:
                idx = num_pagina - 1
                if idx >= len(doc): continue
                
                page = doc[idx]
                width = page.rect.width
                
                # 1. Detectar columnas (Headers)
                zonas = detectar_zonas_columnas(page)
                
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
def reconciliar_geometria_con_bloques(bloques_texto: List[Dict], mapa_geometrico: Dict) -> List[Dict]:
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
            if not montos_en_texto and transacciones_finales:
                # Fusión de descripción
                transacciones_finales[-1]["descripcion"] += " " + bloque["texto_completo"]
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

        # --- PASO 4: GARBAGE COLLECTOR (NUEVO) ---
        # Si después de todo el esfuerzo, el monto es 0 y no encontramos nada...
        # Es altamente probable que sea una continuación de descripción con fecha engañosa.
        if monto_final == 0.0 and match_status == "MISS_MONTO":
            if transacciones_finales:
                # FUSIONAMOS HACIA ATRÁS
                transacciones_finales[-1]["descripcion"] += " " + bloque["texto_completo"]
                # Y NO AGREGAMOS esta transacción a la lista
                continue
            else:
                # Si es el primer bloque y está vacío, lo ignoramos
                continue

        tx = {
            "fecha": token_fecha_bloque,
            "descripcion": bloque["texto_completo"],
            "monto": monto_final,
            "tipo": tipo_final,
            "id_interno": bloque["id_unico"],
            "debug_match": match_status
        }
        transacciones_finales.append(tx)

    return transacciones_finales