import fitz  # PyMuPDF
import logging
import re
from typing import Dict, List, Tuple, Any

logger = logging.getLogger(__name__)

class MotorCaratulas:
    """
    Motor centralizado para la extracción, clasificación y reconciliación 
    de carátulas de estados de cuenta bancarios.
    """
    def __init__(self, triggers_config: dict, palabras_clave_regex: re.Pattern,
                alias_banco_map: dict, banco_detection_regex: re.Pattern, 
                patrones_compilados: dict, debug_flags: list = None):
        """
        Inicializa el motor con las configuraciones necesarias para no depender
        de variables globales esparcidas en otros archivos.
        """
        # Configuración de PDF
        self.triggers_config = triggers_config
        self.palabras_clave_regex = palabras_clave_regex
        
        # Configuración estática de Bancos (Regex)
        self.alias_banco_map = alias_banco_map
        self.banco_detection_regex = banco_detection_regex
        self.patrones_compilados = patrones_compilados

        # Lista de enteros para granularidad en logs
        self.debug_flags = debug_flags if debug_flags is not None else []
    
    def _log_debug(self, flag: int, mensaje: str):
        """
        Imprime un log detallado SOLAMENTE si el flag numérico fue 
        pasado en la lista de debug_flags al instanciar el motor.
        """
        if flag in self.debug_flags:
            # Usamos logger.info para asegurarnos de que se imprima en la consola
            # pero le ponemos un prefijo visual para distinguirlo de los logs normales
            etiquetas = {
                1: "[REGEX]  ", 
                2: "[GPT]    ", 
                3: "[QWEN]   ", 
                4: "[RECONC] ", 
                5: "[FILTRO] "
            }
            prefijo = etiquetas.get(flag, "[DEBUG]  ")
            logger.info(f"  {prefijo} {mensaje}")
    
    async def procesar_caratula_completa(
        self,
        pdf_bytes: bytes,
        prompt_base: str,
        analizar_gpt_fn,   # Inyectamos la función analizar_gpt_fluxo
        analizar_qwen_fn,  # Inyectamos la función analizar_con_ocr_fluxo
        extraer_json_fn,   # Inyectamos extraer_json_del_markdown
        sanitizar_fn       # Inyectamos sanitizar_datos_ia
    ) -> Tuple[List[Dict[str, Any]], bool, str, Dict[int, str], List[Tuple[int, int]]]:
        """
        El orquestador principal del motor. Ejecuta todo el flujo de extracción física,
        estática y de IA, culminando en la triangulación determinista.
        """
        # 1. Extracción física y detección de rangos
        texto_por_pagina, rangos_cuentas = self.extraer_texto_y_rangos(pdf_bytes)
        texto_verificacion_global = "\n".join(texto_por_pagina.values())
        es_documento_digital = self.validar_documento_digital(texto_verificacion_global)

        logger.info(f"[MotorCaratulas] Se detectaron {len(rangos_cuentas)} cuentas. Digital: {es_documento_digital}")

        resultados_acumulados = []

        # 2. Bucle Principal: Procesar cada cuenta detectada
        for inicio_rango, fin_rango in rangos_cuentas:
            logger.info(f"[MotorCaratulas] Procesando cuenta en rango: {inicio_rango} a {fin_rango}")

            # A. Aislar texto del rango actual para no contaminar el Regex
            texto_rango = [texto_por_pagina.get(p, "") for p in range(inicio_rango, fin_rango + 1)]
            texto_verificacion_rango = "\n".join(texto_rango)

            # B. Extracción estática (Regex) - Nuestra "Verdad Base"
            datos_regex = self.identificar_banco_y_datos_estaticos(texto_verificacion_rango.lower())
            banco_detectado = datos_regex.get("banco")

            # C. Selección inteligente de páginas para la IA
            paginas_para_ia = [inicio_rango]
            if (inicio_rango + 1) <= fin_rango:
                paginas_para_ia.append(inicio_rango + 1)

            # Lógica especial heredada (ej. Banregio)
            if banco_detectado == "BANREGIO":
                longitud_rango = (fin_rango - inicio_rango) + 1
                if longitud_rango > 5:
                    paginas_finales = list(range(fin_rango - 4, fin_rango + 1))
                    paginas_para_ia = sorted(list(set(paginas_para_ia + paginas_finales)))
                else:
                    paginas_para_ia = list(range(inicio_rango, fin_rango + 1))

            # D. Ejecución concurrente de Modelos Multimodales
            # Pasamos los bytes; la conversión a imagen la hace la función de la IA por ahora
            tarea_gpt = analizar_gpt_fn(prompt_base, pdf_bytes, paginas_a_procesar=paginas_para_ia)
            tarea_qwen = analizar_qwen_fn(prompt_base, pdf_bytes, paginas_a_procesar=paginas_para_ia)

            import asyncio
            resultados_ia_brutos = await asyncio.gather(tarea_gpt, tarea_qwen, return_exceptions=True)
            res_gpt_str, res_qwen_str = resultados_ia_brutos

            # E. Extracción y Sanitización de los resultados
            datos_gpt = {}
            if res_gpt_str and not isinstance(res_gpt_str, Exception):
                datos_gpt = sanitizar_fn(extraer_json_fn(res_gpt_str))
                self._log_debug(2, f"Datos crudos GPT: {datos_gpt}")
            else:
                logger.error(f"[MotorCaratulas] Falla en GPT: {res_gpt_str}")

            datos_qwen = {}
            if res_qwen_str and not isinstance(res_qwen_str, Exception):
                datos_qwen = sanitizar_fn(extraer_json_fn(res_qwen_str))
                self._log_debug(3, f"Datos crudos Qwen: {datos_qwen}")
            else:
                logger.error(f"[MotorCaratulas] Falla en QwenVL3: {res_qwen_str}")

            # F. Reconciliación Inteligente (Triangulación)
            datos_reconciliados = self.reconciliar_extracciones(datos_regex, datos_qwen, datos_gpt)

            # --- FILTRO DE CALIDAD ---
            if self._es_cuenta_valida(datos_reconciliados, texto_verificacion_rango):
                # G. Inyección de Metadatos
                datos_reconciliados["_metadatos_paginas"] = {
                    "inicio": inicio_rango,
                    "fin": fin_rango,
                    "paginas_analizadas_ia": paginas_para_ia
                }
                resultados_acumulados.append(datos_reconciliados)

        # Mantenemos la misma firma de retorno que esperaba tu orchestator original
        return resultados_acumulados, es_documento_digital, texto_verificacion_global, None, texto_por_pagina, rangos_cuentas

    def extraer_texto_y_rangos(self, pdf_bytes: bytes) -> Tuple[Dict[int, str], List[Tuple[int, int]]]:
        """
        Escanea el PDF para extraer el texto crudo por página y detectar 
        dónde empiezan y terminan las cuentas (Rangos).
        Migrado desde: pdf_processor.py -> detectar_rangos_y_texto
        """
        texto_por_pagina = {}
        rangos_detectados = []
        inicio_actual = None
        
        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                total_paginas = len(doc)
                
                for page_index, page in enumerate(doc):
                    page_num = page_index + 1
                    page_text = page.get_text("text").lower()
                    texto_por_pagina[page_num] = page_text
                    
                    # A. Inicio de rango
                    if inicio_actual is None:
                        if any(trig in page_text for trig in self.triggers_config["inicio"]):
                            inicio_actual = page_num

                    if inicio_actual is not None:
                        encontrado_fin = False
                        
                        # B. Fin explícito
                        if any(trig in page_text for trig in self.triggers_config["fin"]):
                            rangos_detectados.append((inicio_actual, page_num))
                            inicio_actual = None
                            encontrado_fin = True
                        
                        # C. Nuevo inicio (Cascada)
                        elif page_num > inicio_actual and any(trig in page_text for trig in self.triggers_config["inicio"]):
                            rangos_detectados.append((inicio_actual, page_num - 1))
                            inicio_actual = page_num
                        
                        # D. Fin de documento
                        if not encontrado_fin and inicio_actual is not None and page_num == total_paginas:
                            rangos_detectados.append((inicio_actual, total_paginas))
                            inicio_actual = None

        except Exception as e:
            logger.error(f"[MotorCaratulas] Error detectando rangos: {e}")

        # Fallback si no hay rangos
        if not rangos_detectados:
            rangos_detectados = [(1, len(texto_por_pagina) if texto_por_pagina else 1)]

        return texto_por_pagina, rangos_detectados

    def validar_documento_digital(self, texto_extraido: str, umbral: int = 50) -> bool:
        """
        Verifica si el texto extraído es válido para prevenir falsos positivos con escaneos.
        Migrado desde: pdf_processor.py -> es_escaneado_o_no
        """
        if not texto_extraido:
            return False
            
        texto_limpio = texto_extraido.strip()
        logger.debug(f"[MotorCaratulas] Longitud del texto extraído: {len(texto_limpio)}")
        
        # Prueba 1: Longitud mínima
        pasa_longitud = len(texto_limpio) > umbral
        
        # Prueba 2: Contiene palabras clave con sentido
        pasa_contenido = bool(self.palabras_clave_regex.search(texto_limpio))

        return pasa_longitud and pasa_contenido

    def convertir_a_imagenes(self, pdf_bytes: bytes, paginas: List[int]) -> List[bytes]:
        """
        Convierte páginas específicas del PDF a bytes de imágenes (PNG) para la IA Multimodal.
        Migrado desde: helpers_texto_fluxo.py -> convertir_pdf_a_imagenes
        Nota: Devuelve directamente la lista de bytes para no depender de BytesIO en la clase.
        """
        imagenes_bytes = []
        matriz_escala = fitz.Matrix(2, 2)  # Aumentar resolución para mejor lectura OCR de la IA

        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as documento:
                for num_pagina in paginas:
                    if 0 <= num_pagina - 1 < len(documento):
                        pagina = documento.load_page(num_pagina - 1)
                        pix = pagina.get_pixmap(matrix=matriz_escala)
                        imagenes_bytes.append(pix.tobytes("png"))
                    else:
                        logger.warning(f"[MotorCaratulas] Página {num_pagina} fuera de rango.")
        except Exception as e:
            logger.error(f"[MotorCaratulas] Error convirtiendo PDF a imagen: {e}")
            raise ValueError(f"No se pudo procesar el archivo como PDF: {e}")

        return imagenes_bytes
    
    def identificar_banco_y_datos_estaticos(self, texto: str) -> Dict[str, Any]:
        """
        Analiza el texto crudo para identificar el banco usando Regex y luego extrae 
        datos específicos como RFC y montos. Actúa como el validador estático.
        Migrado desde: pdf_processor.py -> extraer_datos_por_banco
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
        match_banco = self.banco_detection_regex.search(texto)
        if not match_banco:
            return resultados

        banco_estandarizado = self.alias_banco_map.get(match_banco.group(0))
        if not banco_estandarizado:
            return resultados
            
        resultados["banco"] = banco_estandarizado.upper()

        patrones_del_banco = self.patrones_compilados.get(banco_estandarizado)
        if not patrones_del_banco:
            return resultados

        # --- 2. Extraer y procesar datos crudos ---
        for nombre_clave, patron in patrones_del_banco.items():
            coincidencias = patron.findall(texto)
            valor_capturado = self._extraer_unico(coincidencias)

            if valor_capturado:
                # Si el campo es numérico, lo limpiamos y casteamos
                if nombre_clave in ["comisiones", "depositos", "cargos", "saldo_promedio"]:
                    try:
                        monto_limpio = str(valor_capturado).replace(",", "").replace("$", "").strip()
                        resultados[nombre_clave] = float(monto_limpio)
                    except (ValueError, TypeError):
                        resultados[nombre_clave] = None
                else:  
                    # Datos tipo string (como el RFC)
                    resultados[nombre_clave] = str(valor_capturado).upper()

        self._log_debug(1, f"Banco detectado: {resultados.get('banco')}")
        self._log_debug(1, f"Datos extraídos: {resultados}")
        return resultados

    @staticmethod
    def _extraer_unico(coincidencias: List[str]):
        """
        Método auxiliar interno. 
        Toma la lista de resultados de un findall de Regex y devuelve la mejor coincidencia.
        Reemplaza la función externa 'extraer_unico' que tenías en pdf_processor.py.
        """
        if not coincidencias:
            return None
            
        # Limpiamos posibles tuplas o strings vacíos que deja Regex
        validos = []
        for c in coincidencias:
            if isinstance(c, tuple):
                # Si hay grupos en el regex, tomamos el primero que no esté vacío
                match = next((item for item in c if item), None)
                if match: validos.append(match)
            elif isinstance(c, str) and c.strip():
                validos.append(c)
                
        return validos[0] if validos else None
    
    def reconciliar_extracciones(self, datos_regex: dict, datos_qwen: dict, datos_gpt: dict) -> Dict[str, Any]:
        """
        Toma las 3 fuentes de verdad y aplica reglas de negocio para obtener
        el dato más preciso. Evita el uso de max() ciego.
        """
        resultado_final = {}
        
        # Obtenemos todos los campos posibles (usando GPT como base estructural)
        todos_los_campos = set(datos_gpt.keys()) | set(datos_qwen.keys())
        CAMPOS_NUMERICOS = {"comisiones", "depositos", "cargos", "saldo_promedio"}

        for campo in todos_los_campos:
            v_regex = datos_regex.get(campo)
            v_qwen = datos_qwen.get(campo)
            v_gpt = datos_gpt.get(campo)

            # --- REGLA 1: CAMPOS NUMÉRICOS (Montos) ---
            if campo in CAMPOS_NUMERICOS:
                num_qwen = self._limpiar_a_float(v_qwen)
                num_gpt = self._limpiar_a_float(v_gpt)
                num_regex = self._limpiar_a_float(v_regex)

                # A. Consenso total (Qwen y GPT están de acuerdo)
                if num_qwen == num_gpt and num_qwen is not None:
                    resultado_final[campo] = num_qwen
                    self._log_debug(4, f"[{campo}] Ambos modelos coinciden ({num_qwen})")
                
                # B. Desempate usando Regex como ancla de confianza
                elif num_qwen == num_regex and num_qwen is not None:
                    resultado_final[campo] = num_qwen
                    self._log_debug(4, f"[{campo}] Qwen y Regex coinciden ({num_qwen})")

                elif num_gpt == num_regex and num_gpt is not None:
                    resultado_final[campo] = num_gpt
                    self._log_debug(4, f"[{campo}] GPT y Regex coinciden ({num_gpt})")
                
                # C. Discrepancia total: Preferimos GPT como fallback numérico (suele ser más robusto en tablas complejas)
                else:
                    resultado_final[campo] = num_gpt if num_gpt is not None else num_qwen
                    self._log_debug(4, f"[{campo}] Discrepancia. Elegido fallback: {resultado_final[campo]}")

            # --- REGLA 2: DATOS EXACTOS (RFC, CLABE) ---
            elif campo in ["rfc", "clabe_interbancaria"]:
                # El Regex manda en formatos rígidos si lo encontró
                if v_regex and len(str(v_regex)) >= 12:
                    resultado_final[campo] = str(v_regex).upper()
                else:
                    # Si no hay Regex, tomamos el que parezca más válido (ej. CLABE debe tener 18 chars)
                    str_qwen = str(v_qwen).strip() if v_qwen else ""
                    str_gpt = str(v_gpt).strip() if v_gpt else ""
                    
                    if campo == "clabe_interbancaria":
                        resultado_final[campo] = str_gpt if len(str_gpt) == 18 else str_qwen
                    else:
                        # RFC: tomamos el más largo asumiendo que el otro está truncado
                        resultado_final[campo] = str_gpt if len(str_gpt) >= len(str_qwen) else str_qwen

            # --- REGLA 3: TEXTO GENERAL (Nombres, Banco, Moneda) ---
            else:
                str_qwen = str(v_qwen).strip() if v_qwen else ""
                str_gpt = str(v_gpt).strip() if v_gpt else ""
                
                # Preferimos el texto de QwenVL3 para lectura OCR pura, suele alucinar menos texto que GPT
                if str_qwen and str_qwen.lower() not in ["none", "null"]:
                    resultado_final[campo] = str_qwen
                else:
                    resultado_final[campo] = str_gpt

        # Inyectamos el banco del Regex si la IA no supo clasificarlo bien
        if datos_regex.get("banco"):
            resultado_final["banco"] = datos_regex["banco"]

        return resultado_final

    def _es_cuenta_valida(self, datos_reconciliados: dict, texto_rango: str) -> bool:
        """
        Actúa como un filtro de calidad final. Prioriza los datos duros (CLABE) 
        para evitar falsos positivos en documentos largos.
        """
        rfc = str(datos_reconciliados.get("rfc", "")).strip().upper()
        clabe = str(datos_reconciliados.get("clabe_interbancaria", "")).strip()
        
        # 1. Lista negra estricta de RFCs de Bancos
        rfcs_bancos = ["BBA830831LJ2", "BNM840515VB1", "BBA940707IE1", "BMB930211WA9"]
        if rfc in rfcs_bancos:
            self._log_debug(5, f"Descartada: RFC {rfc} pertenece al Banco.")
            return False

        # 2. El "Pase VIP": Si tiene una CLABE de 18 dígitos y superó la lista negra, es válida.
        # Quitamos espacios por si Qwen/GPT los separó
        clabe_limpia = ''.join(filter(str.isdigit, clabe))
        if len(clabe_limpia) >= 18:
            return True

        # 3. Reglas estrictas de texto (Solo aplican si NO tiene CLABE, ej. una hoja suelta)
        # Solo buscamos en los primeros 2000 caracteres (las primeras páginas del rango), 
        # no en todo el documento para no penalizar publicidad o anexos.
        texto_inicio = texto_rango[:2000].lower()
        if "estado de cuenta de inversiones" in texto_inicio:
            self._log_debug(5, f"[Filtro] Cuenta descartada: Sub-sección de Inversiones sin CLABE.")
            return False

        # 4. Verificación final de RFC para cuentas sin CLABE
        if not rfc or len(rfc) < 12:
            self._log_debug(5, f"[Filtro] Cuenta descartada: Carece de CLABE y RFC válido.")
            return False

        return True

    @staticmethod
    def _limpiar_a_float(valor) -> float:
        """Helper interno para asegurar que siempre comparamos números limpios."""
        if valor is None: return None
        try:
            return float(str(valor).replace(",", "").replace("$", "").strip())
        except (ValueError, TypeError):
            return None