import fitz
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EngineV2")

@dataclass
class ColumnLayout:
    """Resultado de la Pasada 2 por página"""
    page_num: int
    has_explicit_headers: bool  # True si encontramos "FECHA", "CARGO", etc.
    columns: Dict[str, Dict]    # {'CARGO': {'x0': 100, 'x1': 150, 'center': 125}, ...}
    # ### NUEVO: Guardamos el área donde buscamos para poder dibujarla después
    search_area_rect: fitz.Rect = field(default_factory=lambda: fitz.Rect(0,0,0,0))

@dataclass
class PageGeometry:
    page_num: int
    width: float
    height: float
    header_y: float
    footer_y: float
    content_rect: fitz.Rect = field(init=False)

    def __post_init__(self):
        # +2px de margen para no comerse pixels superiores de los números
        self.content_rect = fitz.Rect(0, self.header_y + 2, self.width, self.footer_y)

class BankStatementEngineV2:
    def __init__(self):
        # Triggers de cierre (Footer)
        self.RX_FOOTER_TRIGGERS = [
            re.compile(r'este\s+documento\s+es\s+una\s+representaci[oó]n', re.IGNORECASE),
            re.compile(r'total\s+de\s+movimientos', re.IGNORECASE),
            re.compile(r'saldo\s+final', re.IGNORECASE),
            re.compile(r'timbres?\s+fiscal', re.IGNORECASE),
            re.compile(r'folio\s+fiscal', re.IGNORECASE),
            re.compile(r'cargos?\s+objetados?\s+por\s+el\s+cliente', re.IGNORECASE), 
            re.compile(r'unidad\s+especializada\s+de\s+atenci[oó]n', re.IGNORECASE)
        ]
        
        # Keywords para SCORING de Header
        self.HEADER_SCORES = {
            "FECHA": 1, "DATE": 1, "DIA": 1, "DÍA": 1, 
            "DESCRIPCIÓN": 1, "CONCEPTO": 1, "DESCRIPCION": 1, "DETALLE": 1, 
            "REFERENCIA": 1, 
            "CARGO": 2, "RETIRO": 2, "DEBITO": 2, "RETIROS": 2, "SALIDAS": 2,
            "DEPÓSITOS": 2, "DEPOSITOS": 2, "ENTRADAS": 2, "ABONO": 2, "DEPOSITO": 2, "CREDITO": 2,
            "SALDO": 2, "BALANCE": 2,
            "SUCURSAL": 1, "OFICINA": 1
        }

        # Si la línea tiene estas palabras, IGNORARLA (Score = -100)
        self.BLACKLIST_HEADER = ["PROMEDIO", "ANTERIOR", "TOTAL", "GRAVABLE", "ISR", "COMISIONES", "GAT", "PERIODO"]

        # --- MEJORAS EN REGEX ---
        # 1. Fechas textuales: Soporta "02/FEB", "2 FEB", "02-Febrero" (3 o más letras)
        #    re.IGNORECASE es clave aquí.
        self.REGEX_FECHA_TEXTUAL = re.compile(r'\d{1,2}\s*[/-]?\s*[a-z]{3,}', re.IGNORECASE) 
        
        # 2. Fechas numéricas: Soporta "12/05", "12/05/23"
        self.REGEX_FECHA_NUMERICA = re.compile(r'\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?')
        
        # 3. Día Aislado: Solo un número del 1 al 31 (requiere validación extra después)
        self.REGEX_DIA_AISLADO = re.compile(r'^(\d{1,2})$')
        # 3.1 Detecta "02 C/Online..." -> Captura el "02" si está al principio seguido de espacio
        self.REGEX_DIA_INICIO = re.compile(r'^(\d{1,2})\s')
        
        # 4. Montos: Soporta "$1,000.00", "1000.00", "50.00", "-50.00"
        self.REGEX_MONTO_SIMPLE = re.compile(r'-?\d{1,3}(?:,\d{3})*\.\d{2}')
        
        self.KEYWORDS_HEADER_FECHA = ["FECHA", "DIA", "DATE"]
        self.KEYWORDS_IGNORE_DESC = ["SALDO ANTERIOR", "TOTAL", "TRASPASO ENTRE CUENTAS", "SALDO FINAL"]
        self.debug_mode = True

    def _calculate_line_score(self, text: str) -> int:
        """Calcula 'qué tanto se parece' una línea a un header de tabla."""
        clean_text = text.upper()
        
        # --- FILTRO DE MUERTE SÚBITA ---
        # Si contiene palabras de resumen financiero, devolvemos 0 inmediatamente.
        for bad_word in self.BLACKLIST_HEADER:
            if bad_word in clean_text:
                return 0
        
        score = 0
        for kw, points in self.HEADER_SCORES.items():
            # Usamos lógica de palabra completa o substring según longitud
            if len(kw) < 4:
                # Para palabras cortas como DIA, buscamos con espacios para no matchear "MEDIODIA"
                if f" {kw} " in f" {clean_text} ": 
                    score += points
            else:
                if kw in clean_text:
                    score += points
        
        return score

    def pass_1_detect_geometry(self, doc: fitz.Document) -> List[PageGeometry]:
        # ... (Tu código de Pass 1 se mantiene IDÉNTICO, lo omito por brevedad) ...
        # Copia y pega tu función pass_1_detect_geometry original aquí
        geometries = []
        logger.info("--- INICIANDO PASADA 1: GEOMETRÍA (DENSITY SCORING) ---")

        for page_num, page in enumerate(doc):
            width = page.rect.width
            height = page.rect.height
            words = page.get_text("words") 
            
            lines = {} 
            for w in words:
                x0, y0, x1, y1, text = w[:5]
                y_bucket = int(y0 / 3) * 3 
                if y_bucket not in lines:
                    lines[y_bucket] = {"text": "", "y_max": 0.0, "words": []}
                lines[y_bucket]["text"] += " " + text
                lines[y_bucket]["y_max"] = max(lines[y_bucket]["y_max"], y1)

            best_header_y = 0.0
            max_score = 0
            
            for y_key, data in lines.items():
                score = self._calculate_line_score(data["text"])
                if score >= 3: 
                    if score > max_score:
                        max_score = score
                        best_header_y = data["y_max"]
                    elif score == max_score and data["y_max"] > best_header_y:
                         best_header_y = data["y_max"]

            if max_score < 3:
                best_header_y = height * 0.18 if page_num == 0 else height * 0.10
                logger.warning(f"Pág {page_num+1}: Sin header claro. Fallback Y={best_header_y:.1f}")

            footer_y = height
            blocks = page.get_text("blocks") 
            for b in blocks:
                x0, y0, x1, y1, text, _, _ = b
                clean_txt = text.upper()
                for rx in self.RX_FOOTER_TRIGGERS:
                    if rx.search(clean_txt):
                        candidate_y = y0 - 5
                        if candidate_y < footer_y:
                            footer_y = candidate_y

            if footer_y <= best_header_y + 20: 
                footer_y = height

            geo = PageGeometry(page_num=page_num + 1, width=width, height=height, header_y=best_header_y, footer_y=footer_y)
            geometries.append(geo)

        return geometries
        
    # =========================================================================
    # PASADA 2: ACTUALIZADA (Con visualización de búsqueda)
    # =========================================================================
    def pass_2_detect_columns(self, doc: fitz.Document, geometries: List[PageGeometry]) -> List[ColumnLayout]:
        layouts = []
        logger.info("--- INICIANDO PASADA 2: COLUMNAS VERTICALES ---")

        # --- CAMBIO 1: Diccionario ampliado según tu imagen ---
        COL_DEFINITIONS = {
            "FECHA": ["FECHA", "DIA", "DÍA", "DATE"], 
            "DESCRIPCION": ["DESCRIPCION", "DESCRIPCIÓN", "CONCEPTO", "DETALLE", "NARRATIVA", "OPERACIONES"],
            "REFERENCIA": ["REFERENCIA", "FOLIO", "DOCTO"],
            "CARGO": ["CARGO", "CARGOS", "RETIRO", "RETIROS", "DEBITO", "SALIDAS"], 
            "ABONO": ["ABONO", "ABONOS", "DEPOSITO", "DEPÓSITO", "DEPOSITOS", "DEPÓSITOS", "CREDITO", "ENTRADAS"],
            "SALDO": ["SALDO", "BALANCE"]
        }

        last_valid_layout = None

        for geo in geometries:
            page = doc[geo.page_num - 1]
            
            # --- CAMBIO 1: RANGO AZUL MÁS AJUSTADO ---
            # Antes: -70 (miraba muy arriba). Ahora: -30 (más pegado a la línea detectada)
            y_scan_top = geo.header_y - 30
            y_scan_bottom = geo.header_y + 6 # Un poquito más abajo para atrapar headers de 2 lineas
            
            search_rect = fitz.Rect(0, y_scan_top, geo.width, y_scan_bottom)

            words = page.get_text("words")
            
            # Filtramos palabras DENTRO de la caja azul
            header_tokens = [
                w for w in words 
                if y_scan_top <= w[1] <= y_scan_bottom
            ]

            detected_cols = {}
            
            # 1. Buscar explícitamente cada columna
            for col_name, keywords in COL_DEFINITIONS.items():
                candidates = []
                for w in header_tokens:
                    clean_txt = w[4].upper().strip()
                    # Buscamos coincidencia exacta o parcial (ej: "CARGO" en "CARGOS")
                    if clean_txt in keywords or any(k in clean_txt for k in keywords):
                        candidates.append(w)
                
                if candidates:
                    # Desempate: Tomamos el que esté verticalmente más cerca de la línea roja (geo.header_y)
                    # Esto evita que agarre una palabra del título "DETALLE DE OPERACIONES" si se confunde
                    best = sorted(candidates, key=lambda w: abs(w[1] - geo.header_y))[0]
                    x_center = (best[0] + best[2]) / 2
                    
                    detected_cols[col_name] = {
                        "x0": best[0], 
                        "x1": best[2], 
                        "y0": best[1], 
                        "y1": best[3], 
                        "center": x_center, 
                        "token": best[4]
                    }
            
            # Validación
            has_anchor = "FECHA" in detected_cols
            has_money = any(k in detected_cols for k in ["CARGO", "ABONO", "SALDO"])
            
            if has_anchor and has_money:
                # Inferencia de Abono si falta (Opcional, pero útil)
                if "CARGO" in detected_cols and "SALDO" in detected_cols and "ABONO" not in detected_cols:
                    c_cargo = detected_cols["CARGO"]["center"]
                    c_saldo = detected_cols["SALDO"]["center"]
                    # Inventamos coordenadas para el dibujo
                    y_ref = detected_cols["CARGO"]["y0"]
                    detected_cols["ABONO"] = {
                        "x0": (c_cargo + c_saldo) / 2 - 10, "x1": (c_cargo + c_saldo) / 2 + 10,
                        "y0": y_ref, "y1": y_ref + 10,
                        "center": (c_cargo + c_saldo) / 2, 
                        "token": "(IMP)" 
                    }

                layout = ColumnLayout(
                    page_num=geo.page_num,
                    has_explicit_headers=True,
                    columns=detected_cols,
                    search_area_rect=search_rect 
                )
                last_valid_layout = layout 
                logger.info(f"Pág {geo.page_num}: Layout ENCONTRADO -> {list(detected_cols.keys())}")
                
            else:
                # Herencia
                if last_valid_layout:
                    layout = ColumnLayout(
                        page_num=geo.page_num,
                        has_explicit_headers=False, 
                        columns=last_valid_layout.columns.copy(),
                        search_area_rect=search_rect
                    )
                    logger.info(f"Pág {geo.page_num}: Layout HEREDADO de Pág {last_valid_layout.page_num}")
                else:
                    layout = ColumnLayout(
                        page_num=geo.page_num,
                        has_explicit_headers=False,
                        columns={},
                        search_area_rect=search_rect
                    )
            layouts.append(layout)
        return layouts
    
    # =========================================================================
    # PASADA 3: SLICING HORIZONTAL (Lógica Híbrida)
    # =========================================================================
    def pass_3_extract_rows(self, doc: fitz.Document, geometries: List[PageGeometry], layouts: List[ColumnLayout]):
        results = []
        logger.info("--- INICIANDO PASADA 3: EXTRAER TRANSACCIONES ---")

        for i, layout in enumerate(layouts):
            geo = geometries[i]
            page = doc[geo.page_num - 1]
            
            # --- CAMBIO 2: INICIO DE LECTURA (FIX DE LOS $70.00) ---
            # Antes: geo.header_y + 15 (Muy abajo, se saltaba la primera fila)
            # Ahora: geo.header_y + 2 (Inmediatamente después de la línea roja)
            y_start = geo.header_y + 2
            y_end = geo.footer_y
            
            words = page.get_text("words")
            # Filtramos solo el cuerpo de la tabla
            words_body = [w for w in words if y_start <= w[1] <= y_end]

            # 2. Convertir ColumnLayout a "zonas_x" (formato que espera tu lógica)
            # Necesitamos rangos [min, max] para Cargo, Abono y Saldo
            zonas_x = {}
            if "CARGO" in layout.columns:
                c = layout.columns["CARGO"]
                zonas_x["cargo"] = (c["x0"] - 10, c["x1"] + 10) # Damos un poco de margen lateral
            else:
                zonas_x["cargo"] = (9999, 9999) # Fuera de rango
            
            if "ABONO" in layout.columns:
                c = layout.columns["ABONO"]
                zonas_x["abono"] = (c["x0"] - 10, c["x1"] + 10)
            else:
                zonas_x["abono"] = (9999, 9999)

            if "SALDO" in layout.columns:
                c = layout.columns["SALDO"]
                zonas_x["saldo"] = (c["x0"] - 10, c["x1"] + 10)
            else:
                # Si no hay saldo, ponemos un muro a la derecha
                zonas_x["saldo"] = (geo.width - 50, geo.width)

            # 3. Detectar Anclas (Fechas a la izquierda)
            anclas = self._encontrar_anclas_fechas(words_body, geo.width)
            
            # 4. Slicing y Extracción
            transacciones = self._extraer_transacciones_por_slice(anclas, words_body, zonas_x, y_end)
            
            logger.info(f"Pág {geo.page_num}: {len(transacciones)} transacciones extraídas.")
            results.append({
                "page": geo.page_num,
                "anclas": anclas,
                "transacciones": transacciones
            })
            
        return results
    
    def _encontrar_anclas_fechas(self, words: List, ancho_pagina: float) -> List[Dict]:
        x_pared = ancho_pagina * 0.25
        words_sorted = sorted(words, key=lambda w: (round(w[1],1), w[0]))

        # --- STITCHING DE LÍNEAS (Igual que antes) ---
        lineas_agrupadas = []
        if words_sorted:
            linea_actual = {"txt": words_sorted[0][4], "y": words_sorted[0][1], "x": words_sorted[0][0], "tokens": [words_sorted[0]]}
            for w in words_sorted[1:]:
                if abs(w[1] - linea_actual["y"]) < 4:
                    linea_actual["txt"] += " " + w[4]
                    linea_actual["tokens"].append(w)
                else:
                    if linea_actual["x"] < x_pared: lineas_agrupadas.append(linea_actual)
                    linea_actual = {"txt": w[4], "y": w[1], "x": w[0], "tokens": [w]}
            if linea_actual["x"] < x_pared: lineas_agrupadas.append(linea_actual)

        anclas = []
        for linea in lineas_agrupadas:
            raw_completo = linea["txt"].strip() 
            
            # 1. FECHAS TEXTUALES ("11/MAR") - Prioridad Alta
            match_textual = self.REGEX_FECHA_TEXTUAL.search(raw_completo)
            if match_textual:
                anclas.append({"texto_fecha": match_textual.group(0), "y_anchor": linea["y"], "x_start": linea["x"], "tipo": "TEXTUAL"})
                continue
            
            # 2. FECHAS NUMÉRICAS ("12/05/23")
            match_num = self.REGEX_FECHA_NUMERICA.search(raw_completo)
            if match_num:
                anclas.append({"texto_fecha": match_num.group(0), "y_anchor": linea["y"], "x_start": linea["x"], "tipo": "NUMERICA"})
                continue

            # --- CAMBIO IMPORTANTE AQUÍ ---
            # 3. Lógica Híbrida para "SOLO DÍA" ("02")
            
            dia_detectado = None
            
            # Caso A: La línea es SOLO el número (ej: "02")
            match_aislado = self.REGEX_DIA_AISLADO.match(raw_completo)
            if match_aislado:
                dia_detectado = int(match_aislado.group(1))
            
            # Caso B: La línea EMPIEZA con número pero tiene texto (ej: "02 C/Online...")
            # Esto arregla las filas pegadas como "C/Online Mora"
            else:
                match_inicio = self.REGEX_DIA_INICIO.match(raw_completo)
                if match_inicio:
                    # VALIDACIÓN EXTRA: Verificar que el primer token físico sea realmente ese número.
                    # Esto evita errores si el stitching pegó basura anterior.
                    primer_token_txt = linea["tokens"][0][4].strip()
                    if primer_token_txt == match_inicio.group(1):
                        dia_detectado = int(match_inicio.group(1))

            if dia_detectado and 1 <= dia_detectado <= 31:
                # VALIDACIÓN DE DINERO (Igual que antes)
                # Buscamos dinero a la derecha en la misma altura Y
                y_target = linea["y"]
                hay_dinero_en_linea = False
                
                # Buscamos en words original para ver toda la fila más allá de la pared X
                for w in words:
                    if abs(w[1] - y_target) < 6 and w[0] > x_pared:
                        clean = w[4].replace("$","").replace(",","")
                        if self.REGEX_MONTO_SIMPLE.search(clean):
                            hay_dinero_en_linea = True
                            break
                
                if hay_dinero_en_linea:
                    anclas.append({
                        "texto_fecha": str(dia_detectado), 
                        "y_anchor": linea["y"], 
                        "x_start": linea["x"], 
                        "tipo": "SOLO_DIA"
                    })

        return anclas

    def _extraer_transacciones_por_slice(self, anclas: List[Dict], words: List, zonas_x: Dict, y_limite_total: float) -> List[Dict]:
        transacciones = []
        
        # Limites de columnas
        r_cargo = zonas_x["cargo"]
        r_abono = zonas_x["abono"]
        x_muro_saldo = zonas_x["saldo"][0] # El inicio de la columna saldo es el muro final

        for i, ancla in enumerate(anclas):
            # Definir techo y suelo del slice
            y_techo = ancla["y_anchor"] - 5
            # El suelo es la siguiente ancla o el final de la página
            y_suelo = anclas[i + 1]["y_anchor"] - 5 if i < len(anclas) - 1 else y_limite_total
            
            # Palabras dentro de la franja horizontal
            palabras_slice = [w for w in words if y_techo <= w[1] < y_suelo]
            
            desc_tokens = []
            cand_montos = []
            
            # Zona donde empieza la descripción (un poco a la derecha de la fecha)
            x_inicio_desc = ancla["x_start"] + 30 

            for w in palabras_slice:
                x, y, x2, y2, texto = w[:5]
                
                # Ignorar lo que esté muy a la derecha (Saldo) o muy a la izquierda (antes de fecha)
                if x >= x_muro_saldo: continue
                if x < x_inicio_desc: continue # Es parte de la fecha

                clean_txt = texto.replace("$", "").replace(",", "")
                # Detección de número (formato 1,000.00 o 500.00)
                es_numero = self.REGEX_MONTO_SIMPLE.search(clean_txt)
                
                col = None
                if es_numero:
                    x_center = (x + x2) / 2
                    # 1. Por centro geométrico (más robusto que borde izquierdo)
                    if r_cargo[0] <= x_center <= r_cargo[1]:
                        col = "CARGO"
                    elif r_abono[0] <= x_center <= r_abono[1]:
                        col = "ABONO"
                    
                    if col:
                        try:
                            val = float(clean_txt)
                            cand_montos.append({"val": val, "x": x, "col": col, "box": w[:4]})
                        except: pass
                
                if not col:
                    # Si no es monto, es descripción
                    desc_tokens.append(w)

            # Armar descripción
            desc_tokens.sort(key=lambda w: (round(w[1], 0), w[0]))
            desc_str = " ".join([w[4] for w in desc_tokens])

            # Selección del mejor monto (El que esté más a la izquierda suele ser el correcto si hay basura)
            if cand_montos:
                # Priorizamos Cargos/Abonos
                mejor = sorted(cand_montos, key=lambda k: k["x"])[0]
                
                tx = {
                    "fecha": ancla["texto_fecha"],
                    "descripcion": desc_str,
                    "monto": mejor["val"],
                    "tipo": mejor["col"],
                    "y_pos": ancla["y_anchor"],
                    "coords": mejor["box"]
                }
                transacciones.append(tx)

        return transacciones
    
    # =========================================================================
    # VISUALIZACIÓN: ACTUALIZADA (Caja Azul de Búsqueda)
    # =========================================================================
    def debug_draw_all(self, doc_path: str, output_path: str, geometries: List[PageGeometry], layouts: List[ColumnLayout], extractions: List[Dict] = None):
        doc = fitz.open(doc_path)
        for i, page in enumerate(doc):
            if i >= len(layouts): break
            
            geo = geometries[i]
            layout = layouts[i]
            
            # 1. Caja AZUL (Área de búsqueda Pass 2)
            shape = page.new_shape()
            shape.draw_rect(layout.search_area_rect)
            shape.finish(color=(0, 0, 1), width=0.5, fill=(0, 0, 1), fill_opacity=0.1)
            shape.commit()
            
            # 2. Caja ROJA (Header Y detectado en Pass 1)
            # Dibujamos una linea roja donde el Pass 1 creyó que estaba el header
            page.draw_line((0, geo.header_y), (geo.width, geo.header_y), color=(1, 0, 0), width=1)
            
            # Determinar estado
            if layout.has_explicit_headers:
                col_color = (0, 0.6, 0) # VERDE FUERTE (Detectado)
                status_txt = "LAYOUT: DETECTADO (Verde)"
            elif layout.columns:
                col_color = (1, 0.5, 0) # NARANJA (Heredado)
                status_txt = "LAYOUT: HEREDADO (Naranja)"
            else:
                col_color = (0.5, 0.5, 0.5) # GRIS
                status_txt = "LAYOUT: FALLIDO"

            page.insert_text((5, 50), status_txt, color=col_color, fontsize=10)
            
            # --- CAMBIO: DIBUJAR COLUMNAS ---
            for col_name, data in layout.columns.items():
                x_center = data["center"]
                
                # A) Si tenemos coordenadas del token (Pass 2 detectado), dibujamos cajita alrededor de la palabra
                if "y0" in data and "y1" in data:
                    word_rect = fitz.Rect(data["x0"], data["y0"], data["x1"], data["y1"])
                    page.draw_rect(word_rect, color=col_color, width=1.5)
                    # B) Línea desde abajo de la palabra hasta el footer
                    start_y = data["y1"]
                else:
                    # Si es heredado a veces no tenemos Y exacta, usamos header_y
                    start_y = geo.header_y

                # C) Línea vertical que recorre toda la página (la columna visual)
                page.draw_line((x_center, start_y), (x_center, geo.footer_y), color=col_color, width=1)
                
                # Etiqueta chiquita arriba
                page.insert_text((x_center - 10, start_y - 2), col_name, color=col_color, fontsize=6)

            # --- NUEVO: DIBUJAR SLICING (Magenta) ---
            if extractions and i < len(extractions):
                data_page = extractions[i]
                anclas = data_page["anclas"]
                transacciones = data_page["transacciones"]

                # 1. Líneas horizontales de corte (Slices)
                for ancla in anclas:
                    y = ancla["y_anchor"]
                    # Línea magenta fina atravesando la página
                    page.draw_line((0, y), (geo.width, y), color=(1, 0, 1), width=0.5)
                    # Círculo en el ancla detectada
                    page.draw_circle((ancla["x_start"], y), 2, color=(1, 0, 1), fill=(1, 0, 1))

                # 2. Cajas sobre los montos extraídos
                for tx in transacciones:
                    if "coords" in tx:
                        rx0, ry0, rx1, ry1 = tx["coords"]
                        rect_monto = fitz.Rect(rx0, ry0, rx1, ry1)
                        # Caja magenta rellena sobre el dinero detectado
                        page.draw_rect(rect_monto, color=(1, 0, 1), width=1, fill=(1, 0, 1), fill_opacity=0.3)
                        
                        # Texto chiquito con el tipo detectado
                        page.insert_text((rx1 + 2, ry1), f"{tx['tipo']}", color=(1, 0, 1), fontsize=5)

        doc.save(output_path)
        logger.info(f"PDF Debug generado: {output_path}")