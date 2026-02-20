import fitz
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

logger = logging.getLogger("EngineV2")
logger.setLevel(logging.INFO) # Solo este logger en INFO

@dataclass
class ColumnLayout:
    """Resultado de la Pasada 2 por página"""
    page_num: int
    has_explicit_headers: bool  # True si encontramos "FECHA", "CARGO", etc.
    columns: Dict[str, Dict]    # {'CARGO': {'x0': 100, 'x1': 150, 'center': 125}, ...}
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
    # --- CONSTANTES DE LOGGING (FLAGS) ---
    LOG_GEOMETRY = 1    # Detalles de Pasada 1 (Detección de Header/Footer)
    LOG_COLUMNS = 2     # Detalles de Pasada 2 (Búsqueda de columnas)
    LOG_EXTRACTION = 3  # Detalles de Pasada 3 (Slicing, montos, stitching)
    LOG_RAYOS_X = 4     # Dumps masivos de palabras (como tu "Rayos X")
    
    def __init__(self, debug_flags: List[int] = None):
        """
        :param debug_flags: Lista de enteros con las secciones a detallar. 
                            Ej: [1, 3] ver detalles de Geometría y Extracción.
                            None o [] = Solo logs INFO generales.
        """
        self.debug_flags = debug_flags if debug_flags else []
        
        # ====================================================================
        # A. CONFIGURACIÓN DE GEOMETRÍA (Pasada 1)
        # ====================================================================
        self.cfg_geo = {
            "p1_search_limit_ratio": 0.90,    # Buscar header hasta el 90% de la pág 1 y 2
            "pn_search_limit_ratio": 0.60,    # Buscar header hasta el 60% en pág 3+
            "header_match_threshold": 40.0,   # Tolerancia vertical para confirmar header continuo
            "fallback_header_y": 0.20,        # Si falla todo en P1, asumir header al 20%
            "min_score_relevo": 3,            # Score necesario para cambiar de header maestro en P2+
        }

        # ====================================================================
        # B. CONFIGURACIÓN DE COLUMNAS (Pasada 2)
        # ====================================================================
        self.cfg_col = {
            "scan_top_offset": 30.0,          # Cuánto mirar hacia arriba desde la línea del header (antes 70)
            "abono_inference_width": 10.0,    # Ancho +/- para crear columna ABONO ficticia
            "min_matches_profile": 4,         # Cuantos matches para aceptar un perfil de columnas inmediatamente
        }

        # ====================================================================
        # C. CONFIGURACIÓN DE EXTRACCIÓN (Pasada 3)
        # ====================================================================
        self.cfg_ext = {
            "row_clustering_px": 6.0,         # Agrupar montos en una misma fila si distan menos de X px
            "slice_ceiling_offset": 5.0,      # Margen superior del slice respecto al ancla
            "slice_floor_offset": 2.0,        # Margen inferior del slice antes de la siguiente fecha
            "orphan_zone_threshold": 10.0,    # Mínimo de pixeles para considerar procesar una zona huérfana
            "hard_stop_lookahead": 20.0,      # Mirar hacia adelante buscando triggers de fin
            "date_search_x_margin": 5.0,      # Margen X extra al buscar fechas en su columna
            "money_validation_y_up": 25.0,    # (Tu corrección) Mirar arriba para validar dinero en "Solo Día"
            "money_validation_y_down": 20.0,  # Mirar abajo para validar dinero
        }

        # ====================================================================
        # D. TRIGGERS Y REGEX (Sin cambios de lógica, solo organización)
        # ====================================================================
        self.RX_FOOTER_TRIGGERS = [
            re.compile(r'este\s+documento\s+es\s+una\s+representaci[oó]n', re.IGNORECASE),
            re.compile(r'total\s+de\s+movimientos', re.IGNORECASE),
            re.compile(r'saldo\s+final', re.IGNORECASE),
            re.compile(r'timbres?\s+fiscal', re.IGNORECASE),
            re.compile(r'folio\s+fiscal', re.IGNORECASE),
            re.compile(r'cargos?\s+objetados?\s+por\s+el\s+cliente', re.IGNORECASE), 
            re.compile(r'unidad\s+especializada\s+de\s+atenci[oó]n', re.IGNORECASE),
            re.compile(r'informaci[oó]n\s+fiscal', re.IGNORECASE),
            re.compile(r'detalles?\s+de\s+movimientos\s+dinero\s+creciente', re.IGNORECASE),
            re.compile(r'inversi[oó]n\s+creciente', re.IGNORECASE),
            re.compile(r'saldo\s+final\s+del\s+periodo', re.IGNORECASE),
            re.compile(r'detalles\s+del\s+cr[eé]dito', re.IGNORECASE),
            re.compile(r'spei\s+enviados', re.IGNORECASE),
        ]
        
        self.RX_HARD_STOP_TRIGGERS = [
            re.compile(r'inversiones\s+premier\s+bajio', re.IGNORECASE),
            re.compile(r'inversiones\s+a\s+plazo\s+fijo', re.IGNORECASE),
            re.compile(r'mercado\s+de\s+dinero', re.IGNORECASE),
            re.compile(r'sociedades\s+de\s+inversi[oó]n', re.IGNORECASE),
            re.compile(r'operaciones\s+vigentes', re.IGNORECASE),
            re.compile(r'detalle\s+de\s+vencimientos', re.IGNORECASE),
            re.compile(r'apartados\s+vigentes', re.IGNORECASE)
        ]
        
        # Keywords para SCORING de Header
        self.HEADER_SCORES = {
            "FECHA": 1, "DATE": 1, "DIA": 1, "DÍA": 1, 
            "DESCRIPCIÓN": 1, "CONCEPTO": 1, "DESCRIPCION": 1, "DETALLE": 1, 
            "REFERENCIA": 1, 
            "CARGO": 2, "RETIRO": 2, "DEBITO": 2, "RETIROS": 2, "SALIDAS": 2,
            "DEPÓSITOS": 2, "DEPOSITOS": 2, "ENTRADAS": 2, "ABONO": 2, "DEPOSITO": 2, "CREDITO": 2, "DEPÓSITO": 2,
            "SALDO": 2, "BALANCE": 2,
            "SUCURSAL": 1, "OFICINA": 1,
            "IMPORTE": 2, "BENEFICIARIO": 2, "RASTREO": 2, "CLAVE": 1, "RECEPTOR": 2, "MOTIVO": 1
        }

        # Blacklist
        self.BLACKLIST_HEADER = [
            "PROMEDIO", "ANTERIOR", "TOTAL", "GRAVABLE", "ISR", "COMISIONES", "GAT", 
            "PERIODO", "TASA", "PENDIENTE", "LIQUIDAR", "SALDO INICIAL", "SPEI",
            "RECUPERACION", "SUMA", "CORTE", "LATINOAMERICA", "NOMINAL", "SEGURIDAD",
            "IMPUESTOS", "OBJETADOS", "TARJETA", "TERCERO", "VENTAS"
        ]

        # Regex Helpers
        # 1. Fechas textuales ESTRICTAS: Solo meses válidos (Español e Inglés)
        # Esto evita que "11 SUC" o "02 HOR" sean detectados como fechas.
        meses = r"(?:ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC|JAN|APR|AUG|DEC)"
        self.REGEX_FECHA_TEXTUAL = re.compile(fr'^\d{{1,2}}\s*[-/]?\s*{meses}', re.IGNORECASE)
        
        # 2. Fechas numéricas: "01/04", "01-04-2023"
        self.REGEX_FECHA_NUMERICA = re.compile(r'^\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?')
        
        # 3. Día Aislado: "01", "31"
        self.REGEX_DIA_AISLADO = re.compile(r'^(\d{1,2})$')

        # 4. Validar Montos
        self.REGEX_MONTO_SIMPLE = re.compile(r'-?\d{1,3}(?:,\d{3})*\.\d{2}')
        
        self.NOISE_DATE_TOKENS = ["SUC", "HORA", "CAJA", "AUT", "REF", "SEC", "MOV"]
        self.KEYWORDS_HEADER_FECHA = ["FECHA", "DIA", "DATE"]
        self.KEYWORDS_IGNORE_DESC = ["SALDO ANTERIOR", "TOTAL", "TRASPASO ENTRE CUENTAS", "SALDO FINAL"]
        
        # Estado Global
        self.global_stop = False

    def _log_debug(self, section_flag: int, message: str):
        """Imprime logs internos SOLO si el flag está activo en la config."""
        if section_flag in self.debug_flags:
            # Usamos logger.info para que salga en el archivo, pero con prefijo DEBUG
            logger.info(f"[DEBUG-{section_flag}] {message}")

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

    # =========================================================================
    # PASADA 1: DETECCIÓN DE GEOMETRÍA (STATEFUL STICKY HEADER)
    # =========================================================================
    def pass_1_detect_geometry(self, doc: fitz.Document) -> List[PageGeometry]:
        logger.info("--- INICIANDO PASADA 1: GEOMETRÍA (STATEFUL STICKY HEADER) ---")
        
        geometries = []
        
        # Estado Persistente
        # Guardamos la Y del último header confiable encontrado.
        active_header_state = {
            "y": None,          # La posición Y
            "score": 0,         # Qué tan seguro estamos (0-10)
            "source_page": -1   # Dónde lo encontramos
        }

        for page_num, page in enumerate(doc):
            width = page.rect.width
            height = page.rect.height
            
            # 1. DEFINIR LÍMITES DE BÚSQUEDA (Usando Config)
            if page_num <= 1:
                limit_y = height * self.cfg_geo["p1_search_limit_ratio"]
            else:
                limit_y = height * self.cfg_geo["pn_search_limit_ratio"]

            # 2. ESCANEO DE CANDIDATOS LOCALES
            words = page.get_text("words")
            lines = {}
            for w in words:
                y_bucket = int(w[1] / 3) * 3 
                if y_bucket not in lines:
                    lines[y_bucket] = {"text": "", "y_max": 0.0}
                lines[y_bucket]["text"] += " " + w[4]
                lines[y_bucket]["y_max"] = max(lines[y_bucket]["y_max"], w[3])

            local_candidates = []
            for data in lines.values():
                if data["y_max"] > limit_y: continue 
                
                score = self._calculate_line_score(data["text"])
                if score >= 1:
                    local_candidates.append({'y': data["y_max"], 'score': score, 'text': data['text']})

            local_candidates.sort(key=lambda x: (-x['score'], x['y']))
            
            # LOG DEBUG: Ver candidatos si el flag LOG_GEOMETRY (1) está activo
            if local_candidates:
                top_cand = local_candidates[0]
                self._log_debug(self.LOG_GEOMETRY, f"Pág {page_num+1}: Mejor Candidato Local -> Score: {top_cand['score']}, Y: {top_cand['y']:.1f}, Txt: '{top_cand['text'][:30]}...'")
            else:
                self._log_debug(self.LOG_GEOMETRY, f"Pág {page_num+1}: No se encontraron candidatos locales.")

            # 3. TOMA DE DECISIÓN (CHAMPION VS CHALLENGER)
            final_header_y = 0.0
            used_strategy = "UNKNOWN"
            best_local = local_candidates[0] if local_candidates else None
            
            # --- Lógica de la Página 1 ---
            if page_num == 0:
                if best_local and best_local['score'] >= 2:
                    final_header_y = best_local['y']
                    active_header_state = {"y": final_header_y, "score": best_local['score'], "source_page": 0}
                    used_strategy = "P1_FOUND"
                else:
                    final_header_y = height * self.cfg_geo["fallback_header_y"] # Config
                    active_header_state = {"y": final_header_y, "score": 1, "source_page": 0} 
                    used_strategy = "P1_FALLBACK"

            # --- Lógica Página 2+ ---
            else:
                # Umbral de RELEVO desde Config
                threshold_score = self.cfg_geo["min_score_relevo"]
                match_tolerance = self.cfg_geo["header_match_threshold"]
                
                # Caso A: Relevo (Nuevo Header fuerte)
                if best_local and best_local['score'] >= threshold_score:
                    final_header_y = best_local['y']
                    active_header_state = {"y": final_header_y, "score": best_local['score'], "source_page": page_num}
                    used_strategy = "NEW_MASTER_DETECTED"
                
                # Caso B: Continuación Confirmada (Mismo Y aprox)
                elif best_local and active_header_state['y'] and abs(best_local['y'] - active_header_state['y']) < match_tolerance and best_local['score'] >= 2:
                    final_header_y = best_local['y']
                    active_header_state['y'] = final_header_y 
                    used_strategy = "CONFIRMED_CONTINUATION"

                # Caso C: Herencia Pura
                elif active_header_state['y'] is not None:
                    final_header_y = active_header_state['y']
                    used_strategy = "INHERITED_STICKY"
                
                # Caso D: Fallback Ciego
                else:
                    final_header_y = height * 0.05 
                    used_strategy = "BLIND_FALLBACK"

            # LOG INFO: General (siempre visible si el logger base está en INFO)
            logger.info(f"Pág {page_num+1}: Header Y={final_header_y:.1f} | Estrategia: {used_strategy}")

            # 4. DETECCIÓN DE FOOTER
            footer_y = height
            blocks = page.get_text("blocks")
            for b in blocks:
                x0, y0, x1, y1, text, _, _ = b
                if any(rx.search(text.upper()) for rx in self.RX_FOOTER_TRIGGERS):
                    if (y0 - 5) < footer_y: footer_y = y0 - 5
            
            if footer_y <= final_header_y + 20: footer_y = height

            geo = PageGeometry(page_num=page_num + 1, width=width, height=height, header_y=final_header_y, footer_y=footer_y)
            geometries.append(geo)

        return geometries
        
    # =========================================================================
    # PASADA 2: DETECCIÓN DE COLUMNAS (Lógica Mejorada con Herencia y Detección Inteligente)
    # =========================================================================
    def pass_2_detect_columns(self, doc: fitz.Document, geometries: List[PageGeometry]) -> List[ColumnLayout]:
        layouts = []
        logger.info("--- INICIANDO PASADA 2: COLUMNAS VERTICALES ---")

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
            
            # --- USO DE CONFIGURACIÓN ---
            # El rango de escaneo ahora viene del init
            y_scan_top = geo.header_y - self.cfg_col["scan_top_offset"]
            y_scan_bottom = geo.header_y 
            
            search_rect = fitz.Rect(0, y_scan_top, geo.width, y_scan_bottom)

            words = page.get_text("words")
            
            header_tokens = [
                w for w in words 
                if y_scan_top <= w[1] <= y_scan_bottom
            ]
            
            # LOG DEBUG: Ver tokens en la zona de header
            self._log_debug(self.LOG_COLUMNS, f"Pág {geo.page_num}: Tokens en zona header ({y_scan_top:.1f}-{y_scan_bottom:.1f}): {[w[4] for w in header_tokens]}")

            detected_cols = {}
            
            for col_name, keywords in COL_DEFINITIONS.items():
                candidates = []
                for w in header_tokens:
                    clean_txt = w[4].upper().strip()
                    if clean_txt in keywords or any(k in clean_txt for k in keywords):
                        candidates.append(w)
                
                if candidates:
                    # Desempate por cercanía vertical a la línea roja
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
            
            has_anchor = "FECHA" in detected_cols
            has_money = any(k in detected_cols for k in ["CARGO", "ABONO", "SALDO"])
            
            if has_anchor and has_money:
                # Inferencia de Abono usando Config
                if "CARGO" in detected_cols and "SALDO" in detected_cols and "ABONO" not in detected_cols:
                    c_cargo = detected_cols["CARGO"]["center"]
                    c_saldo = detected_cols["SALDO"]["center"]
                    y_ref = detected_cols["CARGO"]["y0"]
                    
                    half_width = self.cfg_col["abono_inference_width"] # Config
                    center_inferred = (c_cargo + c_saldo) / 2
                    
                    detected_cols["ABONO"] = {
                        "x0": center_inferred - half_width, 
                        "x1": center_inferred + half_width,
                        "y0": y_ref, "y1": y_ref + 10,
                        "center": center_inferred, 
                        "token": "(IMP)" 
                    }
                    self._log_debug(self.LOG_COLUMNS, f"Pág {geo.page_num}: Columna ABONO inferida en X={center_inferred:.1f}")

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
                    self._log_debug(self.LOG_COLUMNS, f"Pág {geo.page_num}: Layout HEREDADO de Pág {last_valid_layout.page_num}")
                else:
                    layout = ColumnLayout(
                        page_num=geo.page_num,
                        has_explicit_headers=False,
                        columns={},
                        search_area_rect=search_rect
                    )
                    logger.warning(f"Pág {geo.page_num}: FALLO CRÍTICO - Sin Layout ni Herencia")

            layouts.append(layout)
        return layouts
    
    # =========================================================================
    # PASADA 3: SLICING HORIZONTAL (Lógica Híbrida)
    # =========================================================================
    def pass_3_extract_rows(self, doc: fitz.Document, geometries: List[PageGeometry], layouts: List[ColumnLayout]):
        results = []
        logger.info("--- INICIANDO PASADA 3: MULTI-PASS (TABLAS MÚLTIPLES) ---")

        last_global_date = "INICIO_SIN_FECHA" 
        last_page_columns = {} 
        self.global_stop = False 

        for i, layout in enumerate(layouts):
            if self.global_stop:
                logger.info(f"🚫 Pág {layout.page_num}: Saltada por Global Stop activo.")
                results.append({"page": layout.page_num, "anclas": [], "headers_map": [], "transacciones": []})
                continue

            geo = geometries[i]
            page = doc[geo.page_num - 1]
            page_bottom = geo.footer_y 

            # =================================================================
            # ESCANEO PREVENTIVO (Hard Stop Lookahead)
            # =================================================================
            blocks_preventivos = page.get_text("blocks")
            for b in blocks_preventivos:
                texto_bloque = b[4].replace('\n', ' ').strip()
                if any(rx.search(texto_bloque) for rx in self.RX_HARD_STOP_TRIGGERS):
                    y_trigger = b[1] - 5 
                    logger.warning(f"🛑 HARD STOP EN PÁGINA {geo.page_num} (Y={y_trigger:.1f}): '{texto_bloque[:30]}...'")
                    self.global_stop = True
                    if y_trigger < page_bottom:
                        page_bottom = y_trigger
                    break 

            words = page.get_text("words")
            
            # --- RAYOS X (DEBUG POR FLAG) ---
            if self.LOG_RAYOS_X in self.debug_flags:
                self._log_debug(self.LOG_RAYOS_X, f"RAYOS X (Pág {geo.page_num}) - Primeras palabras:")
                for w in words[:10]:
                    self._log_debug(self.LOG_RAYOS_X, f"   🔹 '{w[4]}' | y={w[1]:.1f}")
            
            todas_anclas_pagina = []
            headers_dinamicos = []
            transacciones_pagina = []
            
            # --- DETERMINAR PUNTO DE INICIO ---
            explicit_header_y = geo.header_y if layout.has_explicit_headers else 99999
            
            if explicit_header_y > 100 and explicit_header_y < 900:
                cursor_y = explicit_header_y 
                current_columns = layout.columns
                start_type = "PRIMARY"
                headers_dinamicos.append({"y": cursor_y, "cols": current_columns.copy(), "tipo": "JUMP_START"})
            else:
                if explicit_header_y > 150:
                    cursor_y = 50.0 
                    current_columns = last_page_columns if last_page_columns else layout.columns
                    start_type = "INHERITED_TOP"
                else:
                    cursor_y = explicit_header_y - 2
                    current_columns = layout.columns
                    start_type = "PRIMARY"

                if current_columns:
                    headers_dinamicos.append({"y": cursor_y, "cols": current_columns.copy(), "tipo": start_type})

            # BUCLE DE BLOQUES
            while cursor_y < (page_bottom - 20): 
                
                next_stop_y = page_bottom
                reason_stop = "END_PAGE"
                
                # 1. Buscar Triggers Abajo
                blocks = page.get_text("blocks")
                for b in blocks:
                    if b[1] > cursor_y + 20: 
                        clean_block = b[4].replace('\n', ' ').strip().upper() 
                        
                        if any(rx.search(clean_block) for rx in self.RX_HARD_STOP_TRIGGERS):
                            if (b[1] - 5) < next_stop_y:
                                next_stop_y = b[1] - 5
                                reason_stop = "HARD_STOP"
                        
                        elif any(rx.search(clean_block) for rx in self.RX_FOOTER_TRIGGERS):
                            if (b[1] - 5) < next_stop_y:
                                next_stop_y = b[1] - 5
                                reason_stop = "FOOTER_FOUND"
                
                # 2. Lookahead de Headers
                lookahead_limit = min(next_stop_y, cursor_y + 600)
                words_ahead = [w for w in words if (cursor_y + 30) < w[1] < lookahead_limit]
                
                lines_map = {}
                for w in words_ahead:
                    line_k = int(w[1]/5)*5 
                    if line_k not in lines_map: lines_map[line_k] = ""
                    lines_map[line_k] += " " + w[4]
                
                found_next_header_y = None
                for yk in sorted(lines_map.keys()):
                    txt = lines_map[yk]
                    if self._calculate_line_score(txt) >= 2:
                        # Scan hacia arriba (tolerancia hardcodeada mínima necesaria)
                        y_dry_run_start = max(cursor_y, yk - 15) 
                        test_cols, _ = self._detectar_layout_en_banda(page, y_dry_run_start, page_bottom)
                        if test_cols:
                            found_next_header_y = yk
                            break

                if found_next_header_y and found_next_header_y < next_stop_y:
                    next_stop_y = found_next_header_y - 10 
                    reason_stop = "NEXT_HEADER_FOUND"
                
                if start_type == "INHERITED_TOP" and cursor_y < explicit_header_y:
                    if explicit_header_y < next_stop_y:
                        next_stop_y = explicit_header_y
                        reason_stop = "EXPLICIT_HEADER_COLLISION"

                # PROCESAR BLOQUE
                y_techo_bloque = cursor_y
                y_suelo_bloque = next_stop_y
                
                zonas_x = {}
                # --- FIX: ZONAS X (Fronteras dinámicas para evitar solapamiento) ---
                c_cargo = current_columns.get("CARGO")
                c_abono = current_columns.get("ABONO")

                zonas_x["cargo"] = (9999, 9999)
                zonas_x["abono"] = (9999, 9999)

                if c_cargo and c_abono:
                    # Si existen ambas, calculamos una frontera exacta a la mitad
                    if c_cargo["center"] > c_abono["center"]:
                        # Caso Santander: Abono a la Izquierda, Cargo a la Derecha
                        midpoint = (c_abono["x1"] + c_cargo["x0"]) / 2
                        zonas_x["abono"] = (c_abono["x0"] - 40, midpoint)
                        zonas_x["cargo"] = (midpoint, c_cargo["x1"] + 15)
                    else:
                        # Caso Inverso: Cargo a la Izquierda, Abono a la Derecha
                        midpoint = (c_cargo["x1"] + c_abono["x0"]) / 2
                        zonas_x["cargo"] = (c_cargo["x0"] - 40, midpoint)
                        zonas_x["abono"] = (midpoint, c_abono["x1"] + 15)
                else:
                    # Lógica original de holgura si solo hay una columna de dinero
                    if c_cargo: 
                        zonas_x["cargo"] = (c_cargo["x0"] - 40, c_cargo["x1"] + 15)
                    if c_abono: 
                        zonas_x["abono"] = (c_abono["x0"] - 40, c_abono["x1"] + 15)
                
                if "ABONO" in current_columns:
                    c = current_columns["ABONO"]
                    zonas_x["abono"] = (c["x0"] - 40, c["x1"] + 15)
                else: zonas_x["abono"] = (9999, 9999)
                
                if "SALDO" in current_columns:
                    c = current_columns["SALDO"]
                    zonas_x["saldo"] = (c["x0"] - 10, c["x1"] + 10)
                else: zonas_x["saldo"] = (geo.width + 100, geo.width + 100)
                
                if "DESCRIPCION" in current_columns:
                    zonas_x["desc_center"] = current_columns["DESCRIPCION"]["center"]
                else: zonas_x["desc_center"] = -1

                rango_fecha_x = (0, geo.width * 0.14)
                if "FECHA" in current_columns:
                    col_f = current_columns["FECHA"]
                    rango_fecha_x = (max(0, col_f["x0"]-40), col_f["x1"]+10)
                x_inicio_desc = rango_fecha_x[1] + 5

                # Extraer
                words_block = [w for w in words if y_techo_bloque <= ((w[1]+w[3])/2) <= y_suelo_bloque]
                anclas = self._encontrar_anclas_fechas(words_block, rango_fecha_x, geo.width)
                
                # --- ZONA HUÉRFANA (Usando Config) ---
                if last_global_date != "INICIO_SIN_FECHA":
                    if anclas:
                        y_limite_huerfano = anclas[0]["y_anchor"]
                    else:
                        y_limite_huerfano = y_suelo_bloque

                    orphan_thresh = self.cfg_ext["orphan_zone_threshold"] # Config
                    if (y_limite_huerfano - y_techo_bloque) > orphan_thresh:
                        ancla_virtual = [{
                            "texto_fecha": last_global_date,
                            "y_anchor": y_techo_bloque + 2, 
                            "x_start": rango_fecha_x[0],
                            "tipo": "VIRTUAL_HEREDADA",
                            "box_fecha": [rango_fecha_x[0], y_techo_bloque, rango_fecha_x[0]+20, y_techo_bloque+10]
                        }]
                        
                        txs_huerfanas = self._extraer_transacciones_por_slice(
                            ancla_virtual, words_block, zonas_x, y_limite_huerfano, x_inicio_desc,
                            y_techo_bloque_origen=y_techo_bloque
                        )
                        transacciones_pagina.extend(txs_huerfanas)

                if anclas:
                    todas_anclas_pagina.extend(anclas)
                    txs = self._extraer_transacciones_por_slice(
                        anclas, words_block, zonas_x, y_suelo_bloque, x_inicio_desc,
                        y_techo_bloque_origen=y_techo_bloque
                    )
                    transacciones_pagina.extend(txs)
                    last_global_date = anclas[-1]["texto_fecha"]

                # SIGUIENTE VUELTA
                cursor_y = next_stop_y
                
                if reason_stop == "END_PAGE":
                    break 
                
                elif reason_stop == "HARD_STOP":
                    self.global_stop = True
                    break 

                elif reason_stop in ["FOOTER_FOUND", "NEXT_HEADER_FOUND", "EXPLICIT_HEADER_COLLISION"]:
                    scan_start_y = cursor_y + 5 
                    new_cols, search_rect = self._detectar_layout_en_banda(page, scan_start_y, page_bottom)
                    
                    if new_cols:
                        current_columns = new_cols
                        max_header_y = max(c["y1"] for c in current_columns.values())
                        cursor_y = max_header_y
                        
                        headers_dinamicos.append({
                            "y": scan_start_y,
                            "cols": current_columns.copy(),
                            "tipo": "DETECTED_INLINE",
                            "search_rect": [search_rect.x0, search_rect.y0, search_rect.x1, search_rect.y1]
                        })
                        start_type = "NORMAL"
                    else:
                        cursor_y += 20

            last_page_columns = current_columns.copy() if current_columns else {}

            results.append({
                "page": geo.page_num,
                "anclas": todas_anclas_pagina,
                "headers_map": headers_dinamicos,
                "transacciones": transacciones_pagina
            })
            
        return results
    
    def _encontrar_anclas_fechas(self, words: List, rango_x: Tuple[float, float], ancho_pagina: float) -> List[Dict]:
        x_min_col, x_max_col = rango_x
        # LOG DEBUG
        self._log_debug(self.LOG_EXTRACTION, f"ANCLAS: Buscando fechas en X: {x_min_col:.1f} - {x_max_col:.1f}")

        # 1. FILTRAR (Usando Config)
        margin = self.cfg_ext["date_search_x_margin"]
        x_min_scan = max(0, x_min_col - margin)
        x_max_scan = x_max_col + margin
        
        words_in_col = [w for w in words if x_min_scan <= w[0] <= x_max_scan]
        words_in_col.sort(key=lambda w: (round(w[1], 1), w[0]))

        if not words_in_col: 
            self._log_debug(self.LOG_EXTRACTION, "ANCLAS: No hay palabras en la columna fecha.")
            return []

        # 2. STITCHING (Unir trozos de fecha rotos verticalmente)
        lineas_candidatas = []
        if words_in_col:
            linea_actual = {
                "txt": words_in_col[0][4], "y": words_in_col[0][1], "x": words_in_col[0][0], "tokens": [words_in_col[0]]
            }
            for w in words_in_col[1:]:
                if abs(w[1] - linea_actual["y"]) < 5: # Stitching vertical leve
                    linea_actual["txt"] += " " + w[4]
                    linea_actual["tokens"].append(w)
                else:
                    lineas_candidatas.append(linea_actual)
                    linea_actual = {"txt": w[4], "y": w[1], "x": w[0], "tokens": [w]}
            lineas_candidatas.append(linea_actual)

        anclas = []

        # 3. BARRIDO Y VALIDACIÓN
        for linea in lineas_candidatas:
            clean_txt = linea["txt"].strip().upper().replace(".", "").replace(",", "")
            tokens = clean_txt.split()
            first_token = tokens[0] if tokens else ""
            
            # self._log_debug(self.LOG_EXTRACTION, f"CANDIDATO '{clean_txt}' en Y={linea['y']:.1f}")

            if any(noise in first_token for noise in self.NOISE_DATE_TOKENS):
                continue 

            es_ancla_valida = False
            tipo_detectado = ""
            txt_final = clean_txt 

            # CHECK 1: TEXTUAL
            if self.REGEX_FECHA_TEXTUAL.search(clean_txt):
                es_ancla_valida = True
                tipo_detectado = "TEXTUAL"
            
            # CHECK 2: NUMÉRICA
            elif self.REGEX_FECHA_NUMERICA.search(clean_txt):
                es_ancla_valida = True
                tipo_detectado = "NUMERICA"
            
            # CHECK 3: DÍA AISLADO
            elif self.REGEX_DIA_AISLADO.match(first_token):
                dia_val = int(first_token)
                if 1 <= dia_val <= 31:
                    resto_txt = " ".join(tokens[1:]) if len(tokens) > 1 else ""
                    texto_vecino = self._obtener_texto_vecino(words, linea["y"], x_max_scan)
                    
                    ruido_interno = any(n in resto_txt for n in self.NOISE_DATE_TOKENS)
                    ruido_externo = any(n in texto_vecino for n in self.NOISE_DATE_TOKENS)

                    if not ruido_interno and not ruido_externo:
                        tiene_dinero = self._validar_dinero_en_fila(words, linea["y"], ancho_pagina)
                        
                        if tiene_dinero:
                            es_ancla_valida = True
                            tipo_detectado = "SOLO_DIA"
                            txt_final = first_token 
                            self._log_debug(self.LOG_EXTRACTION, f" -> ACEPTADO: Día Aislado '{first_token}' con Dinero confirmado.")
                        else:
                            # self._log_debug(self.LOG_EXTRACTION, f" -> RECHAZADO: Día '{first_token}' sin dinero cerca.")
                            pass
            
            if es_ancla_valida:
                tks = linea["tokens"]
                if tipo_detectado == "SOLO_DIA": tks = tks[:1] 
                x0_box = min(t[0] for t in tks)
                y0_box = min(t[1] for t in tks)
                x1_box = max(t[2] for t in tks)
                y1_box = max(t[3] for t in tks)

                anclas.append({
                    "texto_fecha": txt_final,
                    "y_anchor": linea["y"],
                    "x_start": linea["x"],
                    "tipo": tipo_detectado,
                    "box_fecha": [x0_box, y0_box, x1_box, y1_box]
                })

        return anclas

    def _obtener_texto_vecino(self, all_words: List, y_target: float, x_start: float) -> str:
        """Devuelve el texto que está inmediatamente a la derecha (mismo Y, X mayor)."""
        vecinos = [
            w[4] for w in all_words
            if abs(w[1] - y_target) < 5 
            and w[0] > x_start
            and w[0] < x_start + 100 
        ]
        return " ".join(vecinos).upper()

    def _validar_dinero_en_fila(self, all_words: List, y_target: float, ancho_pagina: float) -> bool:
        """
        Busca si existe un monto monetario en la zona visual del candidato.
        Usa Configuración para definir qué tan arriba/abajo mirar.
        """
        y_up = self.cfg_ext["money_validation_y_up"]
        y_down = self.cfg_ext["money_validation_y_down"]
        
        y_min = y_target - y_up  
        y_max = y_target + y_down 
        
        palabras_zona = [
            w for w in all_words 
            if y_min < w[1] < y_max
            and w[0] > (ancho_pagina * 0.15) 
        ]
        
        texto_zona = " ".join([w[4] for w in palabras_zona])
        clean = texto_zona.replace("$", "").replace(",", "")
        
        return bool(self.REGEX_MONTO_SIMPLE.search(clean))

    def _linea_tiene_dinero(self, tokens_linea, ancho_pagina) -> bool:
        """Ayudante rápido para validar si una línea candidata a 'Solo Día' tiene montos."""
        txt = "".join([t[4] for t in tokens_linea])
        clean = txt.replace("$", "").replace(",", "")
        return bool(self.REGEX_MONTO_SIMPLE.search(clean))

    def _extraer_transacciones_por_slice(self, anclas: List[Dict], words: List, zonas_x: Dict, y_limite_total: float, x_inicio_desc_dinamico: float, y_techo_bloque_origen: float = None) -> List[Dict]:
        if not anclas: return []
            
        transacciones = []
        r_cargo = zonas_x["cargo"]
        r_abono = zonas_x["abono"]
        x_muro_saldo = zonas_x["saldo"][0] 
        x_inicio_texto = x_inicio_desc_dinamico
        x_center_desc = zonas_x.get("desc_center", -1)

        REGEX_FILA_TOTAL = re.compile(
            r'^\s*(TOTAL|SUMA|GRAN\s+TOTAL|SALDO\s+M[IÍ]NIMO|COMISIONES\s+COBRADAS|Y\s+DEP[ÓO]SITOS|NOMINAL3\s+GAT|EN\s+EL\s+AÑO\s+DEL\s+PERIODO)',
            re.IGNORECASE
        )

        # Configuración
        ceil_offset = self.cfg_ext["slice_ceiling_offset"]
        floor_offset = self.cfg_ext["slice_floor_offset"]
        cluster_px = self.cfg_ext["row_clustering_px"]

        for i, ancla in enumerate(anclas):
            y_actual = ancla["y_anchor"]
            
            # --- LÓGICA DE TECHO ---
            if i == 0 and y_techo_bloque_origen is not None:
                # Ajuste especial para el primer elemento si viene de bloque huérfano
                y_techo_slice = y_techo_bloque_origen - 15.0
            else:
                y_techo_slice = y_actual - ceil_offset # Usando Config

            if i < len(anclas) - 1:
                y_siguiente = anclas[i+1]["y_anchor"]
                y_suelo_slice = y_siguiente - floor_offset 
            else:
                y_suelo_slice = y_limite_total

            # self._log_debug(self.LOG_EXTRACTION, f"SLICE [{i}] Fecha: '{ancla['texto_fecha']}' Y={y_actual:.1f} | Techo: {y_techo_slice:.1f} | Suelo: {y_suelo_slice:.1f}")

            # Filtrar palabras dentro del slice
            palabras_slice = [w for w in words if y_techo_slice <= w[1] < y_suelo_slice]
            
            montos_detectados = []
            tokens_texto = []
            
            for w in palabras_slice:
                x = w[0]
                if x >= x_muro_saldo: continue
                
                clean_txt = w[4].replace("$", "").replace(",", "")
                es_numero = self.REGEX_MONTO_SIMPLE.search(clean_txt)
                
                # Clasificación de Monto REAL
                if es_numero and x > x_inicio_texto:
                    col = None
                    x_center = (w[0] + w[2]) / 2
                    if r_cargo[0] <= x_center <= r_cargo[1]: col = "CARGO"
                    elif r_abono[0] <= x_center <= r_abono[1]: col = "ABONO"
                    
                    if not col: 
                        if r_cargo[0] <= w[0] <= r_cargo[1]: col = "CARGO"
                        elif r_abono[0] <= w[0] <= r_abono[1]: col = "ABONO"

                    if col:
                        try:
                            val = float(clean_txt)
                            montos_detectados.append({"val": val, "y": w[1], "x": w[0], "col": col, "box": w[:4]})
                            continue 
                        except: pass
                
                if x > x_inicio_texto:
                    tokens_texto.append(w)

            # Agrupación de filas (Clustering)
            if montos_detectados:
                montos_detectados.sort(key=lambda m: m["y"])
                
                filas_montos = []
                grupo_actual = [montos_detectados[0]]
                for m in montos_detectados[1:]:
                    # Usando Configuración para Clustering
                    if abs(m["y"] - grupo_actual[0]["y"]) < cluster_px:
                        grupo_actual.append(m)
                    else:
                        filas_montos.append(grupo_actual)
                        grupo_actual = [m]
                filas_montos.append(grupo_actual)

                for idx_fila, grupo in enumerate(filas_montos):
                    mejor_monto = sorted(grupo, key=lambda k: k["x"])[0]
                    y_monto = mejor_monto["y"]
                    
                    # Cálculo dinámico de techos locales para descripción
                    if idx_fila == 0:
                        y_techo_local = y_techo_slice 
                    else:
                        y_prev_monto = filas_montos[idx_fila-1][0]["y"]
                        y_techo_local = (y_prev_monto + y_monto) / 2
                    
                    if idx_fila < len(filas_montos) - 1:
                        y_next_monto = filas_montos[idx_fila+1][0]["y"]
                        y_suelo_local = (y_monto + y_next_monto) / 2
                    else:
                        y_suelo_local = y_suelo_slice

                    x_limite_lectura = x_inicio_texto - 15.0 
                    
                    is_desc_right_sided = False
                    if x_center_desc > 0 and x_center_desc > mejor_monto["x"]:
                        is_desc_right_sided = True

                    tokens_desc = []
                    for w in tokens_texto:
                        if not (y_techo_local <= w[1] < y_suelo_local): continue
                        if not (w[0] > x_limite_lectura): continue
                        
                        hit_monto = False
                        if is_desc_right_sided:
                            if abs(w[0] - mejor_monto["x"]) < 20: hit_monto = True
                        else:
                            if w[0] >= mejor_monto["x"] - 5: hit_monto = True
                            
                        if not hit_monto:
                            tokens_desc.append(w)
                    
                    tokens_desc.sort(key=lambda w: (round(w[1], 0), w[0]))
                    desc_str = " ".join([w[4] for w in tokens_desc]).strip()

                    if REGEX_FILA_TOTAL.match(desc_str): continue

                    tx = {
                        "fecha": ancla["texto_fecha"],
                        "descripcion": desc_str,
                        "monto": mejor_monto["val"],
                        "tipo": mejor_monto["col"],
                        "id_interno": f"Y{int(y_monto)}_IDX{idx_fila}",
                        "score_confianza": 0.95,
                        "coords_box": mejor_monto["box"]
                    }
                    transacciones.append(tx)

        return transacciones

    def _detectar_layout_en_banda(self, page, y_start: float, y_end: float) -> Tuple[Dict, fitz.Rect]:
        """
        Mini-Pass 2: Detecta columnas usando múltiples perfiles con ALTURAS DINÁMICAS.
        """
        all_words = page.get_text("words")
        
        # DEFINICIONES DE PERFIL (Podrían ir a Config si quisieras, pero aquí están bien encapsuladas)
        PROFILES_CONFIG = [
            {
                "scan_height": 15.5, 
                "definitions": {
                    "FECHA": ["FECHA", "DIA", "DATE"],
                    "DESCRIPCION": ["DESCRIPCION", "DESCRIPCIÓN", "CONCEPTO", "DETALLE", "NARRATIVA"],
                    "REFERENCIA": ["REFERENCIA", "FOLIO", "DOCTO", "AUTORIZACION"],
                    "CARGO": ["CARGO", "RETIRO", "DEBITO", "SALIDAS", "IMPORTE"], 
                    "ABONO": ["ABONO", "ABONOS", "DEPOSITO", "DEPÓSITO", "DEPOSITOS", "DEPÓSITOS", "CREDITO", "ENTRADAS"],
                    "SALDO": ["SALDO"]
                }
            },
            {
                "scan_height": 30,
                "definitions": {
                    "FECHA": ["FECHA"],
                    "CARGO": ["IMPORTE", "MONTO"], 
                    "DESCRIPCION": ["CONCEPTO", "MOTIVO", "BENEFICIARIO"], 
                    "REFERENCIA": ["RASTREO", "CLAVE", "REFERENCIA", "AUTORIZACION"],
                    "EXTRA_TRIGGER": ["RECEPTOR", "NOMBRE", "TARJETA", "CUENTA"] 
                }
            }
        ]

        best_detected_cols = {}
        best_search_rect = fitz.Rect(0,0,0,0)
        max_matches = 0
        min_matches_to_break = self.cfg_col["min_matches_profile"] # Usando Config

        for config in PROFILES_CONFIG:
            scan_h = config["scan_height"]
            defs = config["definitions"]
            
            y_scan_bottom = y_start + scan_h
            current_search_rect = fitz.Rect(0, y_start, page.rect.width, y_scan_bottom)
            
            header_tokens = [w for w in all_words if y_start <= w[1] <= y_scan_bottom]
            
            current_cols = {}
            matches = 0
            
            for canon_name, keywords in defs.items():
                is_trigger = (canon_name == "EXTRA_TRIGGER")
                candidates = []
                for w in header_tokens:
                    clean_txt = w[4].upper().strip()
                    if clean_txt in keywords or any(k in clean_txt for k in keywords):
                        candidates.append(w)
                
                if candidates:
                    matches += 1
                    if not is_trigger:
                        best = sorted(candidates, key=lambda w: abs(w[1] - y_start))[0]
                        x_center = (best[0] + best[2]) / 2
                        current_cols[canon_name] = {
                            "x0": best[0], "x1": best[2], 
                            "y0": best[1], "y1": best[3], 
                            "center": x_center,
                            "token": best[4]
                        }
            
            has_essential = "FECHA" in current_cols and (any(k in current_cols for k in ["CARGO", "ABONO", "DESCRIPCION"]))
            
            if has_essential:
                if matches > max_matches:
                    max_matches = matches
                    best_detected_cols = current_cols
                    best_search_rect = current_search_rect
                    
                    if matches >= min_matches_to_break:
                        break

        return best_detected_cols, best_search_rect
    
    # =========================================================================
    # VISUALIZACIÓN: VERSIÓN FINAL (Guías de columna extendidas y cajas grandes)
    # =========================================================================
    def debug_draw_all(self, doc_path: str, output_path: str, geometries: List[PageGeometry], layouts: List[ColumnLayout], extractions: List[Dict] = None):
        """
        Genera un PDF visual mejorado:
        - Líneas azules verticales cubren todo el bloque de transacciones hasta el siguiente header.
        - Cajas verdes de detección de columnas son más grandes (con padding).
        """
        doc = fitz.open(doc_path)
        limit = len(layouts)
        
        for i in range(limit):
            page = doc[i]
            geo = geometries[i]
            layout = layouts[i]
            
            data_page = extractions[i] if extractions and i < len(extractions) else None
            
            # --- 0. DIBUJAR ÁREA DE BÚSQUEDA PRIMARIA (Referencia fondo tenue) ---
            if layout.search_area_rect:
                shape = page.new_shape()
                shape.draw_rect(layout.search_area_rect)
                shape.finish(color=(0, 0, 1), width=0.5, fill=(0, 0, 1), fill_opacity=0.03)
                shape.commit()

            headers_a_pintar = []
            anclas_a_pintar = []
            transacciones_a_pintar = []
            
            if data_page:
                headers_a_pintar = data_page.get("headers_map", [])
                anclas_a_pintar = data_page.get("anclas", [])
                transacciones_a_pintar = data_page.get("transacciones", [])
            
            if not headers_a_pintar:
                headers_a_pintar = [{"y": geo.header_y, "cols": layout.columns, "tipo": "STATIC_FALLBACK"}]

            # --- 1. DIBUJAR HEADERS Y GUÍAS VERTICALES ---
            # Usamos enumerate para poder mirar hacia adelante (el siguiente header)
            for idx, h_info in enumerate(headers_a_pintar):
                y_ref = h_info["y"]
                cols = h_info["cols"]
                tipo = h_info.get("tipo", "UNKNOWN")
                
                # --- CÁLCULO DEL LÍMITE INFERIOR DE LAS LÍNEAS AZULES ---
                # Si hay un siguiente header en la lista, la línea azul llega hasta ahí.
                # Si no, llega hasta el footer detectado de la página.
                if idx + 1 < len(headers_a_pintar):
                    y_end_line = headers_a_pintar[idx + 1]["y"] - 2 # Un pequeño margen antes del siguiente
                else:
                    y_end_line = geo.footer_y # Hasta el final del contenido

                # Pintar área de búsqueda secundaria (si existe)
                if "search_rect" in h_info:
                    r_coords = h_info["search_rect"]
                    r_sec = fitz.Rect(r_coords)
                    shape = page.new_shape()
                    shape.draw_rect(r_sec)
                    shape.finish(color=(0, 0, 0.8), width=0.5, fill=(0, 0, 1), fill_opacity=0.05)
                    shape.commit()

                line_color = (1, 0, 0) if tipo in ["PRIMARY", "STATIC_FALLBACK"] else (1, 0.5, 0) 
                
                # Línea horizontal del Header
                page.draw_line((0, y_ref), (geo.width, y_ref), color=line_color, width=1.5)
                page.insert_text((5, y_ref - 5), f"TABLA ({tipo})", color=line_color, fontsize=6)

                # Columnas y Guías Verticales
                for col_name, data in cols.items():
                    x_center = data["center"]
                    
                    # --- CORRECCIÓN 1: Línea guía azul extendida hasta el final del bloque ---
                    # Usamos y_end_line calculado arriba y aumentamos un poco el grosor (0.5)
                    page.draw_line((x_center, y_ref), (x_center, y_end_line), color=(0, 0, 1), width=0.5)
                    page.insert_text((x_center - 10, y_ref - 2), col_name, color=(0, 0, 0.5), fontsize=5)
                    
                    # --- CORRECCIÓN 2: Cajita verde más grande con padding ---
                    if "x0" in data:
                        padding = 3 # Pixels extra por lado
                        r = fitz.Rect(data["x0"] - padding, data["y0"] - padding, 
                                        data["x1"] + padding, data["y1"] + padding)
                        
                        # Borde verde sólido y relleno suave
                        page.draw_rect(r, color=(0, 0.7, 0), width=1.5, fill=(0, 1, 0), fill_opacity=0.15)

            # --- 2. DIBUJAR ANCLAS (FECHAS) ---
            for ancla in anclas_a_pintar:
                y = ancla["y_anchor"]
                page.draw_line((0, y), (geo.width, y), color=(1, 0, 1), width=0.3)
                
                if "box_fecha" in ancla:
                    r = fitz.Rect(ancla["box_fecha"])
                    page.draw_rect(r, color=(0, 1, 1), width=1, fill=(0, 1, 1), fill_opacity=0.3)
                    page.insert_text((r.x1 + 2, r.y1), f"{ancla.get('tipo', '?')}", color=(0,0,0), fontsize=4)
                else:
                    page.draw_circle((ancla["x_start"], y), 2, color=(1, 0, 1), fill=(1, 0, 1))

            # --- 3. DIBUJAR TRANSACCIONES ---
            for tx in transacciones_a_pintar:
                if "coords_box" in tx:
                    rx0, ry0, rx1, ry1 = tx["coords_box"]
                    rect_monto = fitz.Rect(rx0, ry0, rx1, ry1)
                    page.draw_rect(rect_monto, color=(1, 0, 1), width=1, fill=(1, 0, 1), fill_opacity=0.3)
                    page.insert_text((rx1 + 2, ry1), f"{tx['tipo']}", color=(1, 0, 1), fontsize=5)

        doc.save(output_path)
        logger.info(f"PDF Debug generado: {output_path}")