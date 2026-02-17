import fitz
import re
import time
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class FormatoFecha(Enum):
    DESCONOCIDO = "desconocido"
    COMPLETA = "completa"   # Ej: 12 ABR, 12/04/2025, 12-04
    SOLO_DIA = "solo_dia"   # Ej: 01, 15, 30 (Común en Santander/Afirme)


@dataclass
class StatementContext:
    columnas_detectadas: Optional[Dict] = None
    formato_fecha: FormatoFecha = FormatoFecha.DESCONOCIDO


class BankStatementEngine:
    def __init__(self, debug_mode=False):
        """
        Motor V4.2 (Híbrido): Infinite Scroll + Detección de Columnas Semántica
        """
        self.debug_mode = debug_mode
        self.metrics = {
            "total_paginas": 0,
            "total_transacciones": 0,
            "tiempo_total": 0.0
        }

        # --- ZONA DE REGEX ---

        # 1. Regex de Monto
        self.REGEX_MONTO_SIMPLE = re.compile(r'\d{1,3}(?:,\d{3})*\.\d{2}')
        self.REGEX_MONTO_ESTRICTO = re.compile(r'^\d{1,3}(?:,\d{3})*\.\d{2}$')

        # 2. Meses
        self.STR_MESES = r"(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)"

        # 3. FECHA FUERTE: DD/MM/AAAA, DD-MM-AA
        self.REGEX_FECHA_NUMERICA = re.compile(
            r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b'
        )
        # 4. FECHA TEXTUAL (BBVA/SANTANDER): "03 FEB", "03/FEB", "03-FEB"
        self.REGEX_FECHA_TEXTUAL = re.compile(
            rf'\b(\d{{1,2}})[\/\s-]{self.STR_MESES}\b',
            re.IGNORECASE
        )
        # 5. DÍA AISLADO
        self.REGEX_DIA_AISLADO = re.compile(r'^(\d{1,2})(\s+|$)')

        # --- KEYWORDS ---
        self.KEYWORDS_HEADER_FECHA = ["fecha", "dia", "día", "date", "fech", "operación", "operacion"]

        self.TRIGGERS_CIERRE = [
            "total de movimientos", "total de cargos", "total de abonos",
            "resumen de comisiones", "cadena original", "timbre fiscal",
            "este documento es una representación", "saldo final del periodo",
            # Secciones que aparecen DESPUÉS de los movimientos y no son transacciones
            "estado de cuenta de apartados", "apartados vigentes",
        ]

        self.KEYWORDS_CARGO = [
            "retiro", "retiros", "cargo", "cargos", "debito", "debitos",
            "débito", "signo", "debe", "salida", "salidas"
        ]
        self.KEYWORDS_ABONO = [
            "deposito", "depositos", "depósito", "abono", "abonos", "depósitos",
            "credito", "creditos", "haber", "entrada", "entradas"
        ]
        self.KEYWORDS_IGNORE_DESC = [
            "saldo anterior", "saldo inicial", "saldo al corte",
            "saldo promedio", "total de", "resumen de", "no. de cuenta", "saldo",
            # Headers de secciones que no son movimientos
            "importe apartado", "nombre apartado", "folio",
        ]

    # =========================================================================
    #                    PIPELINE: PERGAMINO INFINITO
    # =========================================================================
    def procesar_documento_entero(self, pdf_path: str, paginas: List[int] = None):
        """
        Fusiona todas las páginas en una sola estructura lógica vertical (Y acumulado).
        """
        t_start_global = time.time()
        resultados_totales = []

        all_words_continuos = []
        y_offset_acumulado = 0.0
        ctx = StatementContext()

        try:
            with fitz.open(pdf_path) as doc:
                if paginas is None:
                    paginas = list(range(1, len(doc) + 1))
                    logger.info(f"Auto-detectadas {len(paginas)} páginas para procesar")
                elif not paginas:
                    logger.error("Lista de páginas vacía")
                    return []

                primer_pagina_idx = paginas[0] - 1
                if primer_pagina_idx >= len(doc):
                    logger.error(f"Página {paginas[0]} fuera de rango (doc tiene {len(doc)} páginas)")
                    return []

                page_1 = doc[primer_pagina_idx]
                ancho_pagina = page_1.rect.width

                ctx.columnas_detectadas = self._detectar_zonas_columnas(doc, paginas)

                # --- PASO 2: FUSIÓN VERTICAL (STITCHING) ---
                for num_pag in paginas:
                    idx = num_pag - 1
                    if idx >= len(doc):
                        logger.warning(f"Página {num_pag} excede límite del documento")
                        continue

                    page = doc[idx]
                    alto_pagina = page.rect.height

                    y_hard_stop = self._calcular_hard_stop(page)
                    y_start = alto_pagina * 0.15 if idx > primer_pagina_idx else 0

                    rect_lectura = fitz.Rect(0, y_start, ancho_pagina, y_hard_stop)
                    words = page.get_text("words", clip=rect_lectura)

                    words_ajustados = []
                    for w in words:
                        w_list = list(w)
                        w_list[1] += y_offset_acumulado
                        w_list[3] += y_offset_acumulado
                        words_ajustados.append(w_list)

                    all_words_continuos.extend(words_ajustados)
                    y_offset_acumulado += alto_pagina
                    self.metrics["total_paginas"] += 1

                if not all_words_continuos:
                    logger.warning("No se extrajeron palabras del documento")
                    return []

                anclas = self._encontrar_anclas_fechas(all_words_continuos, ancho_pagina, ctx)

                if not anclas:
                    logger.warning("No se encontraron anclas de fechas")
                    return []

                transacciones = self._extraer_transacciones_por_slice(
                    anclas, all_words_continuos, ctx.columnas_detectadas, y_offset_acumulado
                )

                self.metrics["total_transacciones"] = len(transacciones)

                tiempo_ms = (time.time() - t_start_global) * 1000

                resultado = {
                    "pagina": 999,
                    "metricas": {
                        "numero_pagina": 999,
                        "tiempo_procesamiento_ms": round(tiempo_ms, 2),
                        "cantidad_bloques_detectados": len(transacciones),
                        "cantidad_transacciones_finales": len(transacciones),
                        "calidad_promedio_pagina": 1.0,
                        "alertas": []
                    },
                    "transacciones": transacciones
                }

                resultados_totales.append(resultado)

        except Exception as e:
            logger.error(f"Error crítico en pipeline: {e}", exc_info=True)
            raise

        self.metrics["tiempo_total"] = (time.time() - t_start_global)
        return resultados_totales

    # =========================================================================
    #                       LÓGICA CORE MEJORADA
    # =========================================================================
    def _calcular_hard_stop(self, page: fitz.Page) -> float:
        texto_lower = page.get_text("text").lower()
        y_limite = page.rect.height
        umbral_minimo_y = page.rect.height * 0.45

        for trigger in self.TRIGGERS_CIERRE:
            if trigger.lower() in texto_lower:
                instancias = page.search_for(trigger)
                for inst in instancias:
                    y_candidato = inst.y0 - 5
                    if y_candidato > umbral_minimo_y:
                        y_limite = min(y_limite, y_candidato)
                        break

        return y_limite


    # =========================================================================
    #           DETECCIÓN DE COLUMNAS V7 - ANCHOR-FIRST SEMÁNTICA
    # =========================================================================
    def _detectar_zonas_columnas(self, doc: fitz.Document, paginas: List[int]) -> Dict:
        """
        V7 - DETECCIÓN ANCHOR-FIRST:

        Problema resuelto: la v6 capturaba tokens de la carátula (resumen inicial)
        que también tienen "cargos/abonos/saldo" pero en X distintas a la tabla real.

        Estrategia:
        1. ANCLA: Buscar la línea donde CARGOS y ABONOS aparecen JUNTOS
           (co-aparición en la misma Y ±8px). Esa Y es el header real de la tabla.
        2. BLOQUE: Extraer TODOS los tokens en Y_ancla ±30px (captura headers
           multi-línea como "SALDO" encima de "OPERACION / LIQUIDACION").
        3. CLASIFICAR: Dentro del bloque, mapear cada token a cargo/abono/saldo/saldo_sub.
        4. MURO: Si hay sub-saldo, el muro va antes de la primera sub-columna.
        5. FALLBACK: Si no hay co-aparición, intentar ancla solo por ABONO, luego
           solo CARGO, finalmente proporcional.
        """
        logger.info("\n" + "=" * 60)
        logger.info("🤖 INICIANDO DETECCIÓN V7 - ANCHOR-FIRST")
        logger.info("=" * 60)

        ancho_final = 612.0

        KEYWORDS_SALDO_SUB = [
            "operacion", "operación", "liquidacion", "liquidación",
            "contable", "disponible"
        ]
        # Veneno: palabras que invalidan una línea como header de tabla
        POISON_LINE = [
            "promedio", "anterior", "inicial", "total de", "resumen",
            "gravable", "minimo", "mínimo", "objetad", "comision"
        ]

        # Acumularemos el mejor resultado de todas las páginas analizadas
        # (guardamos la geometría de la página que tenga la mejor ancla)
        mejor_ancla = None   # {"y": float, "cargo_x": float, "abono_x": float, "tokens_bloque": list}

        for num_pag in paginas[:4]:
            idx = num_pag - 1
            if idx >= len(doc):
                continue
            page = doc[idx]
            ancho_final = page.rect.width
            all_words_pg = page.get_text("words")
            lineas_pg = self._agrupar_por_lineas(all_words_pg, tolerancia_y=4)

            # ================================================================
            # FASE 1: BUSCAR LÍNEA ANCLA (co-aparición CARGO + ABONO)
            # ================================================================
            # Escaneamos TODA la página (no limitamos al 50%) porque en algunos
            # bancos la tabla empieza más abajo.
            # Índice: por cada línea, registramos si tiene cargo y/o abono.
            ancla_y = None
            ancla_cargo_x = None
            ancla_abono_x = None

            for ln in lineas_pg:
                txt_ln = ln["texto"].lower()

                # Saltar líneas con veneno
                if any(p in txt_ln for p in POISON_LINE):
                    continue

                x_cargo_en_linea = None
                x_abono_en_linea = None

                for w in ln["tokens"]:
                    txt_w = w[4].lower().strip().replace(":", "").replace(".", "")
                    x_c = (w[0] + w[2]) / 2

                    # ¿Es keyword de cargo?
                    if any(k in txt_w for k in self.KEYWORDS_CARGO):
                        # Solo aceptar si está en la mitad derecha de la página
                        # (evita "Cargos Objetados" a la izquierda en la carátula)
                        if x_c > ancho_final * 0.35:
                            x_cargo_en_linea = x_c

                    # ¿Es keyword de abono?
                    if any(k in txt_w for k in self.KEYWORDS_ABONO):
                        if x_c > ancho_final * 0.35:
                            x_abono_en_linea = x_c

                # ¿Ambos encontrados en esta línea?
                if x_cargo_en_linea is not None and x_abono_en_linea is not None:
                    ancla_y = ln["y_min"]
                    ancla_cargo_x = x_cargo_en_linea
                    ancla_abono_x = x_abono_en_linea
                    logger.info(f"✅ ANCLA encontrada en Y={ancla_y:.0f}: "
                                f"CARGO x={ancla_cargo_x:.0f}, ABONO x={ancla_abono_x:.0f}")
                    break  # Primera co-aparición válida = header real

            # Si no encontramos co-aparición, intentar solo ABONO como ancla débil
            if ancla_y is None:
                for ln in lineas_pg:
                    txt_ln = ln["texto"].lower()
                    if any(p in txt_ln for p in POISON_LINE):
                        continue
                    for w in ln["tokens"]:
                        txt_w = w[4].lower().strip().replace(":", "").replace(".", "")
                        x_c = (w[0] + w[2]) / 2
                        if any(k in txt_w for k in self.KEYWORDS_ABONO) and x_c > ancho_final * 0.35:
                            ancla_y = ln["y_min"]
                            ancla_abono_x = x_c
                            logger.info(f"⚠️  Ancla débil (solo ABONO) en Y={ancla_y:.0f}, x={ancla_abono_x:.0f}")
                            break
                    if ancla_y is not None:
                        break

            if ancla_y is None:
                logger.warning(f"  Página {num_pag}: Sin ancla encontrada")
                continue

            # ================================================================
            # FASE 2: EXTRAER BLOQUE DE HEADERS (Y_ancla ± 30px)
            # ================================================================
            # Tolerancia generosa para capturar headers multi-línea:
            # Línea 1: FECHA OPER | FECHA LIQ | DESCRIPCION | REFERENCIA | CARGOS | ABONOS
            # Línea 2 (encima):                                                    SALDO
            # Línea 3 (encima):                                            OPERACION | LIQUIDACION
            Y_RADIO_BLOQUE = 30
            tokens_bloque = [
                w for w in all_words_pg
                if (ancla_y - Y_RADIO_BLOQUE) <= w[1] <= (ancla_y + Y_RADIO_BLOQUE)
            ]

            if mejor_ancla is None or ancla_cargo_x is not None:
                mejor_ancla = {
                    "y": ancla_y,
                    "cargo_x": ancla_cargo_x,
                    "abono_x": ancla_abono_x,
                    "tokens_bloque": tokens_bloque,
                    "pagina": num_pag,
                    "ancho": ancho_final,
                }
                # Si encontramos ancla fuerte (cargo+abono) en la primera página, no seguimos
                if ancla_cargo_x is not None:
                    break

        # ================================================================
        # FASE 3: CLASIFICAR TOKENS DEL BLOQUE → CARGO / ABONO / SALDO / SALDO_SUB
        # ================================================================
        if mejor_ancla is None:
            logger.warning("⚠️  Sin ancla en ninguna página → usando proporcional puro")
            ancho_final = ancho_final  # ya está definido
            x_cargo_final  = ancho_final * 0.64
            x_abono_final  = ancho_final * 0.78
            x_saldo_final  = ancho_final * 0.92
            x_muro_real    = None
        else:
            ancho_final = mejor_ancla["ancho"]
            tokens_bloque = mejor_ancla["tokens_bloque"]

            # Usamos la X del ancla como base confirmada
            x_cargo_base = mejor_ancla["cargo_x"]
            x_abono_base = mejor_ancla["abono_x"]

            # Ahora buscamos SALDO en el bloque completo
            saldo_candidatos   = []  # x_centro de tokens que son saldo puro
            saldo_sub_candidatos = [] # x_centro de tokens que son sub-saldo

            # También re-confirmamos cargo/abono con todos los tokens del bloque
            # (por si el ancla fue débil y solo teníamos abono)
            cargo_candidatos = []
            abono_candidatos = []

            lineas_bloque = self._agrupar_por_lineas(tokens_bloque, tolerancia_y=4)

            for ln in lineas_bloque:
                txt_ln = ln["texto"].lower()
                if any(p in txt_ln for p in POISON_LINE):
                    continue

                for w in ln["tokens"]:
                    txt_w = w[4].lower().strip().replace(":", "").replace(".", "")
                    x_c = (w[0] + w[2]) / 2

                    # SALDO (puro): exactamente "saldo" sin sub-keywords
                    # Solo en la mitad derecha de la página (>50%) para evitar
                    # "Saldo Anterior" o similares en la zona de descripción
                    if txt_w == "saldo" and x_c > ancho_final * 0.50:
                        saldo_candidatos.append(x_c)

                    # SUB-SALDO: palabras como "operacion", "liquidacion" que aparecen
                    # debajo de "SALDO" en headers de 2 líneas.
                    # Umbral más estricto: >55% del ancho para evitar falsos positivos
                    # en la mitad izquierda (ej: "Operacion" en zona de descripción AFIRME)
                    elif any(k in txt_w for k in KEYWORDS_SALDO_SUB) and x_c > ancho_final * 0.55:
                        saldo_sub_candidatos.append(x_c)

                    # CARGO (re-confirmación)
                    elif any(k in txt_w for k in self.KEYWORDS_CARGO) and x_c > ancho_final * 0.35:
                        cargo_candidatos.append(x_c)

                    # ABONO (re-confirmación)
                    elif any(k in txt_w for k in self.KEYWORDS_ABONO) and x_c > ancho_final * 0.35:
                        abono_candidatos.append(x_c)

            # Consolidar cargo/abono: priorizar ancla, luego bloque
            x_cargo_final = x_cargo_base if x_cargo_base else self._mediana(cargo_candidatos)
            x_abono_final = x_abono_base if x_abono_base else self._mediana(abono_candidatos)

            # Saldo: usamos la mediana de los candidatos puros del bloque
            x_saldo_final = self._mediana(saldo_candidatos)

            # Muro: si hay sub-saldo, usamos su X más izquierda
            x_muro_real = min(saldo_sub_candidatos) if saldo_sub_candidatos else None

            logger.info(f"\n📋 EVIDENCIA DE BLOQUE (página {mejor_ancla['pagina']}, Y≈{mejor_ancla['y']:.0f}):")
            logger.info(f"   CARGO  : base={x_cargo_base} | bloque={cargo_candidatos} → {x_cargo_final}")
            logger.info(f"   ABONO  : base={x_abono_base} | bloque={abono_candidatos} → {x_abono_final}")
            logger.info(f"   SALDO  : candidatos={[int(x) for x in saldo_candidatos]} → {x_saldo_final}")
            logger.info(f"   SUB-S  : candidatos={[int(x) for x in saldo_sub_candidatos]} → muro={x_muro_real}")

            # ---- DEDUCCIÓN DE COLUMNAS FALTANTES ----
            if x_cargo_final is None and x_abono_final is not None:
                # Cargo suele estar ~65px a la izquierda del abono
                x_cargo_final = x_abono_final - 65
                logger.info(f"   CARGO deducido: {x_cargo_final:.0f} (abono - 65px)")

            if x_abono_final is None and x_cargo_final is not None:
                x_abono_final = x_cargo_final + 65
                logger.info(f"   ABONO deducido: {x_abono_final:.0f} (cargo + 65px)")

            if x_cargo_final is None and x_abono_final is None:
                logger.warning("   Sin cargo ni abono → proporcional")
                x_cargo_final = ancho_final * 0.64
                x_abono_final = ancho_final * 0.78

            if x_saldo_final is None:
                if x_muro_real is not None:
                    x_saldo_final = x_muro_real + 40  # ficticio, no se captura
                    logger.info(f"   SALDO ficticio (sub-saldo guía): {x_saldo_final:.0f}")
                else:
                    x_saldo_final = ancho_final * 0.92
                    logger.info(f"   SALDO proporcional: {x_saldo_final:.0f}")

        # ================================================================
        # FASE 4: VALIDACIÓN DE ORDEN
        # REGLA: saldo debe estar a la derecha de cargo Y abono.
        # NO forzamos cargo < abono porque el orden depende del banco:
        #   - BBVA/Santander: [CARGOS | ABONOS | SALDO]  → cargo < abono
        #   - AFIRME:         [DEPÓSITOS | RETIROS | SALDO] → abono < cargo
        # Si saldo queda a la izquierda de cargo o abono (error de detección),
        # lo corregimos intercambiando saldo con el más a la derecha.
        # ================================================================
        x_max_cargo_abono = max(x_cargo_final, x_abono_final)

        if x_saldo_final < x_max_cargo_abono:
            # Saldo está a la izquierda → intercambiar saldo con el de más a la derecha
            if x_cargo_final > x_abono_final:
                # Cargo es el más a la derecha → swap cargo ↔ saldo
                x_cargo_final, x_saldo_final = x_saldo_final, x_cargo_final
                logger.warning("   ⚠️  Saldo corregido: swap cargo↔saldo (saldo estaba a la izquierda)")
            else:
                # Abono es el más a la derecha → swap abono ↔ saldo
                x_abono_final, x_saldo_final = x_saldo_final, x_abono_final
                logger.warning("   ⚠️  Saldo corregido: swap abono↔saldo (saldo estaba a la izquierda)")

        # ================================================================
        # FASE 5: CONSTRUCCIÓN DE RANGOS ADAPTATIVOS
        # Funciona para cualquier orden: cargo < abono (BBVA) o abono < cargo (AFIRME)
        # ================================================================
        dist_cargo_abono = abs(x_abono_final - x_cargo_final)

        # El más a la derecha de {cargo, abono} — es el que está junto al saldo
        x_izquierdo  = min(x_cargo_final, x_abono_final)
        x_derecho    = max(x_cargo_final, x_abono_final)

        dist_derecho_saldo = abs(x_saldo_final - x_derecho)

        radio_cargo = min(50, max(20, dist_cargo_abono * 0.38))
        radio_abono = min(50, max(20, min(dist_cargo_abono, dist_derecho_saldo) * 0.38))

        # Muro: siempre a la derecha del más-derecho de {cargo, abono}
        if x_muro_real is not None and x_muro_real > x_derecho + 10:
            muro_derecho = x_muro_real - 15
            logger.info(f"   🛡️  MURO REAL (sub-saldo x={x_muro_real:.0f}): {muro_derecho:.0f}")
        else:
            if x_muro_real is not None:
                logger.warning(
                    f"   ⚠️  Sub-saldo x={x_muro_real:.0f} descartado como muro "
                    f"(izquierda de columna derecha x={x_derecho:.0f})"
                )
            muro_derecho = (x_derecho + x_saldo_final) / 2
            logger.info(f"   🛡️  MURO MIDPOINT: {muro_derecho:.0f}")

        # Rangos: cada columna se expande ±radio desde su centro.
        # La columna DERECHA (más cercana al saldo) se topa con el muro.
        # La columna IZQUIERDA no toca el muro.
        r_izq_raw = (x_izquierdo - radio_cargo, x_izquierdo + radio_cargo)
        r_der_raw = (x_derecho - radio_abono, min(x_derecho + radio_abono, muro_derecho))

        # Anti-solapamiento: si se solapan, cortar en el punto medio entre centros
        if r_izq_raw[1] > r_der_raw[0]:
            corte = (x_izquierdo + x_derecho) / 2
            r_izq = (r_izq_raw[0], corte)
            r_der = (corte, r_der_raw[1])
        else:
            r_izq = r_izq_raw
            r_der = r_der_raw

        # Asignar rangos al tipo semántico correcto
        # (cargo/abono mantienen su identidad independientemente de su posición)
        if x_cargo_final <= x_abono_final:
            # Layout estándar: cargo izquierda, abono derecha
            r_cargo = r_izq
            r_abono = r_der
        else:
            # Layout invertido (AFIRME): abono izquierda, cargo derecha
            r_abono = r_izq
            r_cargo = r_der

        logger.info(f"\n🏁 GEOMETRÍA FINAL V7:")
        logger.info(f"   Centros : Cargo={x_cargo_final:.0f} | Abono={x_abono_final:.0f} | Saldo={x_saldo_final:.0f}")
        logger.info(f"   Rangos  : Cargo={tuple(int(x) for x in r_cargo)} | Abono={tuple(int(x) for x in r_abono)}")
        logger.info(f"   Muro    : {muro_derecho:.0f} → saldo desde ahí hasta {ancho_final:.0f}")

        return {
            "cargo":  r_cargo,
            "abono":  r_abono,
            "saldo":  (muro_derecho, ancho_final),
            "muro_derecho": muro_derecho,
            "_centros": {
                "cargo": x_cargo_final,
                "abono": x_abono_final,
                "saldo": x_saldo_final
            },
            "_tiene_sub_saldo": x_muro_real is not None,
        }

    def _agrupar_por_lineas(self, words: List, tolerancia_y: float = 3) -> List[Dict]:
        """Agrupa palabras en líneas basándose en su coordenada Y."""
        if not words:
            return []

        words_sorted = sorted(words, key=lambda w: (w[1], w[0]))
        lineas = []
        linea_actual = {
            "tokens": [words_sorted[0]],
            "y_min": words_sorted[0][1],
            "y_max": words_sorted[0][3],
            "texto": words_sorted[0][4]
        }

        for w in words_sorted[1:]:
            # Misma línea si el Y está dentro de la tolerancia
            if abs(w[1] - linea_actual["y_min"]) <= tolerancia_y:
                linea_actual["tokens"].append(w)
                linea_actual["texto"] += " " + w[4]
                linea_actual["y_max"] = max(linea_actual["y_max"], w[3])
            else:
                lineas.append(linea_actual)
                linea_actual = {
                    "tokens": [w],
                    "y_min": w[1],
                    "y_max": w[3],
                    "texto": w[4]
                }
        lineas.append(linea_actual)
        return lineas

    def _mediana(self, valores: List[float]) -> Optional[float]:
        """Calcula la mediana de una lista, devuelve None si está vacía."""
        if not valores:
            return None
        s = sorted(valores)
        n = len(s)
        mid = n // 2
        return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2

    def _encontrar_anclas_fechas(self, words: List, ancho_pagina: float, ctx: StatementContext) -> List[Dict]:
        """
        LÓGICA HÍBRIDA V3-V4:
        Itera sobre las líneas agrupadas y busca patrones en orden de prioridad.
        """
        x_pared = 40.0
        words_sorted = sorted(words, key=lambda w: w[1])

        for w in words_sorted[:200]:
            if w[0] < (ancho_pagina * 0.30):
                txt = w[4].strip().upper().replace(":", "")
                if any(kw.upper() in txt for kw in self.KEYWORDS_HEADER_FECHA):
                    x_pared = max(w[0] + 80.0, w[2] + 20)
                    break

        candidatos = [w for w in words_sorted if w[0] < x_pared]
        candidatos.sort(key=lambda w: (round(w[1], 1), w[0]))

        if not candidatos:
            return []

        # === AGRUPACIÓN VISUAL (STITCHING DE LÍNEA) ===
        lineas_agrupadas = []
        if candidatos:
            linea_actual = {
                "txt": candidatos[0][4],
                "y": candidatos[0][1],
                "x": candidatos[0][0],
                "tokens": [candidatos[0]]
            }

            for w in candidatos[1:]:
                if abs(w[1] - linea_actual["y"]) < 4:
                    linea_actual["txt"] += " " + w[4]
                    linea_actual["tokens"].append(w)
                else:
                    lineas_agrupadas.append(linea_actual)
                    linea_actual = {"txt": w[4], "y": w[1], "x": w[0], "tokens": [w]}
            lineas_agrupadas.append(linea_actual)

        anclas = []

        for linea in lineas_agrupadas:
            raw_completo = linea["txt"].strip()

            # --- PRIORIDAD 1: FECHAS TEXTUALES ("03 FEB", "03/FEB") ---
            match_textual = self.REGEX_FECHA_TEXTUAL.search(raw_completo)
            if match_textual:
                anclas.append({
                    "texto_fecha": match_textual.group(0),
                    "y_anchor": linea["y"],
                    "x_start": linea["x"],
                    "tipo_detectado": "COMPLETA_TEXTUAL"
                })
                continue

            # --- PRIORIDAD 2: FECHAS NUMÉRICAS FUERTES ("12/05/2023") ---
            match_num = self.REGEX_FECHA_NUMERICA.search(raw_completo)
            if match_num:
                anclas.append({
                    "texto_fecha": match_num.group(0),
                    "y_anchor": linea["y"],
                    "x_start": linea["x"],
                    "tipo_detectado": "COMPLETA_NUMERICA"
                })
                continue

            # --- PRIORIDAD 3: DÍA AISLADO CON VALIDACIÓN DE MONTO ---
            match_dia = self.REGEX_DIA_AISLADO.match(raw_completo)
            if match_dia:
                posible_dia = match_dia.group(1)

                try:
                    dia_int = int(posible_dia)
                    if not (1 <= dia_int <= 31):
                        continue
                except:
                    continue

                y_target = linea["y"]
                palabras_linea_completa = [
                    w for w in words
                    if abs(w[1] - y_target) < 6 and w[0] > x_pared
                ]

                texto_linea_derecha = " ".join([w[4] for w in palabras_linea_completa])

                if self.REGEX_MONTO_SIMPLE.search(texto_linea_derecha):
                    anclas.append({
                        "texto_fecha": posible_dia,
                        "y_anchor": linea["y"],
                        "x_start": linea["x"],
                        "tipo_detectado": "SOLO_DIA"
                    })

        logger.info(f"Total anclas encontradas (Híbrido): {len(anclas)}")
        return anclas

    def _extraer_transacciones_por_slice(
        self, anclas: List[Dict], words: List, zonas_x: Dict, y_limite_total: float
    ) -> List[Dict]:
        """
        Extrae transacciones usando slicing vertical entre anclas.

        ESTRATEGIA DE CLASIFICACIÓN:
        1. Intenta clasificar usando x0 (borde izquierdo) — compatibilidad total
           con todos los bancos donde los números pequeños están bien alineados.
        2. Si x0 no cae en ninguna columna, intenta con x_centro (borde izquierdo
           + borde derecho / 2) — fix para montos grandes alineados a la derecha
           cuyo x0 cae en la columna vecina (ej: '17,242.00' en BBVA).
        3. Si tampoco, aplica snap por centro de columna si hay metadatos disponibles.
        """
        transacciones = []

        inicio_cargo = zonas_x["cargo"][0]
        inicio_abono = zonas_x["abono"][0]
        x_primera_columna_numerica = min(inicio_cargo, inicio_abono)
        x_limite_desc = x_primera_columna_numerica - 10

        # Los metadatos de centros solo existen en zonas_x del motor V7
        centros = zonas_x.get("_centros", None)

        for i, ancla in enumerate(anclas):
            y_techo = ancla["y_anchor"] - 2
            y_suelo_ref = anclas[i + 1]["y_anchor"] - 2 if i < len(anclas) - 1 else y_limite_total
            y_suelo = min(y_suelo_ref, y_limite_total)

            palabras_slice = [w for w in words if y_techo <= w[1] < y_suelo]

            desc_tokens = []
            cand_montos = []

            x_inicio_desc = ancla["x_start"] + 35
            x_muro_saldo = zonas_x["saldo"][0]
            r_cargo = zonas_x["cargo"]
            r_abono = zonas_x["abono"]

            for w in palabras_slice:
                x, y, x2, y2, texto = w[0], w[1], w[2], w[3], w[4]

                # Posicionamiento siempre por borde izquierdo (igual que versión original)
                if x >= x_muro_saldo:
                    continue
                if x < x_inicio_desc:
                    continue

                clean_txt = texto.replace("$", "").replace(",", "")
                es_numero = bool(
                    re.search(r'^\d{1,3}(?:,\d{3})*\.\d{2}$', clean_txt) or
                    (re.search(r'\d', clean_txt) and "." in clean_txt and len(clean_txt) < 15)
                )

                # ── PASO 1: Clasificar por x0 (borde izquierdo) ──────────────
                col = None
                if r_cargo[0] <= x <= r_cargo[1]:
                    col = "CARGO"
                elif r_abono[0] <= x <= r_abono[1]:
                    col = "ABONO"

                # ── PASO 2: Fallback por x_centro ────────────────────────────
                # Solo para números que no clasificaron con x0.
                # Fix para montos grandes alineados a la derecha en su celda:
                #   x0 cae en zona cargo, pero x_centro está en zona abono.
                # Ejemplo: '17,242.00' x0=420 (fuera), x_centro=438.9 → ABONO ✓
                if col is None and es_numero:
                    x_cls = (x + x2) / 2
                    if r_cargo[0] <= x_cls <= r_cargo[1]:
                        col = "CARGO"
                        if self.debug_mode:
                            logger.debug(f"   📌 x_cls CARGO: '{texto}' x0={x:.1f} x_cls={x_cls:.1f}")
                    elif r_abono[0] <= x_cls <= r_abono[1]:
                        col = "ABONO"
                        if self.debug_mode:
                            logger.debug(f"   📌 x_cls ABONO: '{texto}' x0={x:.1f} x_cls={x_cls:.1f}")

                    # ── PASO 3: Snap por centro de columna (solo si tenemos metadatos) ──
                    # Actúa cuando x_cls tampoco cae en rango — token en el gap.
                    # Requiere _centros en zonas_x (disponible con _detectar_zonas_columnas V7).
                    if col is None and centros and x_inicio_desc <= x_cls < x_muro_saldo:
                        c_cargo = centros["cargo"]
                        c_abono = centros["abono"]
                        x_entre = min(c_cargo, c_abono) <= x_cls <= max(c_cargo, c_abono)
                        if x_entre:
                            col = "CARGO" if abs(x_cls - c_cargo) <= abs(x_cls - c_abono) else "ABONO"
                            if self.debug_mode:
                                logger.debug(
                                    f"   📌 SNAP {col}: '{texto}' x_cls={x_cls:.1f} "
                                    f"(Δc={abs(x_cls-c_cargo):.1f} Δa={abs(x_cls-c_abono):.1f})"
                                )

                # ── Asignación final ─────────────────────────────────────────
                if es_numero and col:
                    try:
                        val = float(clean_txt)
                        cand_montos.append({"val": val, "x": x, "col": col, "box": w[:4]})
                    except ValueError:
                        pass

                elif x < x_limite_desc:
                    desc_tokens.append(w)

                else:
                    if not es_numero and x < (x_limite_desc + 80):
                        desc_tokens.append(w)

            # Armar descripción
            desc_tokens.sort(key=lambda w: (round(w[1], 0), w[0]))
            desc_str = " ".join([w[4] for w in desc_tokens])

            # Filtro Semántico
            desc_clean = " ".join(desc_str.split()).upper()
            if any(k.upper() in desc_clean for k in self.KEYWORDS_IGNORE_DESC):
                if self.debug_mode:
                    kw_match = [k for k in self.KEYWORDS_IGNORE_DESC if k.upper() in desc_clean]
                    logger.debug(
                        f"🚫 FILTRO SEMÁNTICO eliminó: Y={int(ancla['y_anchor'])} "
                        f"fecha={ancla['texto_fecha']} keyword={kw_match} desc='{desc_clean[:60]}'"
                    )
                continue

            movs = [m for m in cand_montos if m["col"] in ["CARGO", "ABONO"]]

            if movs:
                # Tomamos el primer monto (más a la izquierda = columna más cercana a descripción)
                mejor = sorted(movs, key=lambda k: k["x"])[0]
                monto_final = mejor["val"]
                tipo_final = mejor["col"]
                coords_box = mejor["box"]
            else:
                if self.debug_mode:
                    logger.debug(
                        f"\n⚠️  SLICE SIN MONTO → ancla={ancla['texto_fecha']} Y={int(ancla['y_anchor'])} "
                        f"[techo={int(y_techo)}, suelo={int(y_suelo)}]"
                    )
                    logger.debug(
                        f"   Rangos: CARGO={tuple(int(v) for v in r_cargo)} | "
                        f"ABONO={tuple(int(v) for v in r_abono)} | MURO={int(x_muro_saldo)}"
                    )
                    nums_en_slice = [
                        w for w in palabras_slice
                        if re.search(r'\d+\.\d{2}', w[4].replace(",", ""))
                        and w[0] < x_muro_saldo
                    ]
                    if nums_en_slice:
                        logger.debug("   Números en slice (fuera de rango):")
                        for wn in nums_en_slice:
                            xn, xn2 = wn[0], wn[2]
                            x_cls_d = (xn + xn2) / 2
                            col_d = ("CARGO✓" if r_cargo[0] <= xn <= r_cargo[1] else
                                     "ABONO✓" if r_abono[0] <= xn <= r_abono[1] else
                                     f"FUERA x0={xn:.0f} x_cls={x_cls_d:.0f}")
                            logger.debug(f"     → '{wn[4]}' {col_d}")
                    else:
                        logger.debug(f"   Sin números en slice. Tokens: {[(w[4], int(w[0])) for w in palabras_slice[:10]]}")
                continue

            tx = {
                "fecha": ancla["texto_fecha"],
                "descripcion": desc_str,
                "monto": monto_final,
                "tipo": tipo_final,
                "id_interno": f"Y{int(ancla['y_anchor'])}",
                "score_confianza": 0.95,
                "metodo_match": "EXACTO_GEO_COLUMNA",
                "coords_box": coords_box,
                "errores": []
            }
            transacciones.append(tx)

        return transacciones