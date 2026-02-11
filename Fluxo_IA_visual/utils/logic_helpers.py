import fitz
import re
import logging
from typing import List, Dict
from .helpers_texto_fluxo import REGEX_FECHA_COMBINADA
from ..services.pdf_processor import detectar_zonas_columnas

logger = logging.getLogger(__name__)

# --- 1. DATE SLICER ---
def segmentar_por_fechas(texto_pagina: str, numero_pagina: int) -> List[Dict]:
    lineas = texto_pagina.split('\n')
    bloques = []
    bloque_actual = None
    idx_interno = 0
    
    for linea in lineas:
        linea_limpia = linea.strip()
        if not linea_limpia: continue

        match = REGEX_FECHA_COMBINADA.match(linea_limpia)
        
        if match:
            # Guardamos el anterior si existe
            if bloque_actual:
                bloques.append(bloque_actual)
            
            fecha_str = match.group(0)
            bloque_actual = {
                "id_unico": f"P{numero_pagina}_IDX{idx_interno}",
                "fecha_detectada": fecha_str,
                "texto_completo": linea_limpia,
                "lineas": [linea_limpia],
                "pagina": numero_pagina
            }
            idx_interno += 1
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
                
                # 1. Detectar columnas
                zonas = detectar_zonas_columnas(page)
                
                # DEFINICIÓN DE LÍMITES "HARDCODED" (Reglas de Oro)
                limite_fecha_x = width * 0.20       # 20% Izquierdo (Fechas)
                limite_saldo_x_inicio = width * 0.85 # 15% Derecho (Saldos - Zona Prohibida)
                
                zonas["fecha_limite_x"] = limite_fecha_x
                zonas["saldo_limite_x"] = limite_saldo_x_inicio # Para debug

                words = page.get_text("words")
                numeros_encontrados = []
                filas_fechas = []
                
                for w in words:
                    texto = w[4].strip().replace("$", "").replace(",", "")
                    x_centro = (w[0] + w[2]) / 2
                    y_centro = (w[1] + w[3]) / 2
                    
                    # A. Fechas (Solo izquierda)
                    if REGEX_FECHA_COMBINADA.match(w[4]):
                        if x_centro <= limite_fecha_x:
                            filas_fechas.append({
                                "fecha_texto": w[4],
                                "y": y_centro,
                                "x": x_centro,
                                "y_min": w[1] - 2,
                                "y_max": w[3] + 2
                            })
                    
                    # B. Números
                    if "." in texto and len(texto) > 3 and texto.replace(".", "").isdigit():
                        try:
                            valor = float(texto)
                            tipo = "indefinido"
                            
                            # 1. ¿Es SALDO? (Prioridad Máxima: Zona Prohibida)
                            if x_centro >= limite_saldo_x_inicio:
                                tipo = "saldo"
                            
                            # 2. Si no es saldo, checamos columnas detectadas
                            elif zonas["cargo"] and zonas["cargo"][0] <= x_centro <= zonas["cargo"][1]:
                                tipo = "cargo"
                            elif zonas["abono"] and zonas["abono"][0] <= x_centro <= zonas["abono"][1]:
                                tipo = "abono"
                            
                            numeros_encontrados.append({
                                "id_geo": f"{x_centro:.2f}_{y_centro:.2f}",
                                "valor": valor,
                                "x": x_centro,
                                "y": y_centro,
                                "tipo": tipo, # Ahora puede ser 'saldo'
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
        
        fecha_bloque_str = bloque["fecha_detectada"].lower().strip()
        
        # --- PASO 1: ENCONTRAR ANCLA Y ---
        y_bloque = None
        for fila in filas_geo:
            if fila.get("usada", False): continue
            fecha_geo = fila["fecha_texto"].lower().strip()
            if fecha_geo in fecha_bloque_str or fecha_bloque_str in fecha_geo:
                y_bloque = fila["y"]
                fila["usada"] = True 
                break 
        
        # --- PASO 2: LOGICA DE FUSION PREVIA ---
        if y_bloque is None:
            montos_en_texto = regex_monto_texto.findall(bloque["texto_completo"])
            # Si no hay ancla geométrica Y no hay montos escritos, es basura/descripción
            if not montos_en_texto and transacciones_finales:
                transacciones_finales[-1]["descripcion"] += " " + bloque["texto_completo"]
                continue
            elif not montos_en_texto:
                continue
            else:
                y_bloque = -1 

        # --- PASO 3: CAZAR EL NÚMERO ---
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

        # Estrategia B: Valor Exacto (Textual) - CORREGIDA
        valores_texto = []
        # Usamos un regex un poco más permisivo para capturar, luego limpiamos
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
            clasificados = [c for c in candidatos_espaciales if c["tipo"] != "indefinido"]
            if clasificados:
                mejor_candidato = clasificados[0] 
                match_status = "OK_SPATIAL_CLASS"
            else:
                mejor_candidato = max(candidatos_espaciales, key=lambda x: x["valor"])
                match_status = "WARN_SPATIAL_INDEF"

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
            "fecha": bloque["fecha_detectada"],
            "descripcion": bloque["texto_completo"],
            "monto": monto_final,
            "tipo": tipo_final,
            "id_interno": bloque["id_unico"],
            "debug_match": match_status
        }
        transacciones_finales.append(tx)

    return transacciones_finales