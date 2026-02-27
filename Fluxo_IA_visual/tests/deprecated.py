## EN ESTE ARCHIVO IRÁN PRUEBAS DE FUNCIONES QUE YA NO SE USAN, PERO QUE PODRÍAN SER ÚTILES EN EL FUTURO

from procesamiento.auxiliares import verificar_total_depositos # ya no existe la carpeta procesamiento


def test_verificar_total_depositos(): # ya no existe la función verificar_total_depositos
    """Probamos la lógica de la suma de los depósitos"""
    # Caso 1: La suma es mayor a 250,000
    datos_mayor = [{"depositos": 200000.0}, {"depositos": 60000.0}]
    assert verificar_total_depositos(datos_mayor) is True

    # Caso 2: La suma es menor a 250,000
    datos_menor = [{"depositos": 100000.0}, {"depositos": 20000.0}]
    assert verificar_total_depositos(datos_menor) is False

    # Caso 3: Faltan datos o son nulos
    datos_vacios = [{"depositos": 10000.0}, {"otro_campo":50000.0}, {"depositos": None}]
    assert verificar_total_depositos(datos_vacios) is False


"""
CRITERIO DE ACEPTACIÓN EXCLUSIVO:
    Una transacción SOLO es válida si su descripción contiene alguna de estas frases exactas: 
        Reglas de la extracción de una línea: 
            - venta tarjetas
            - venta tdc inter
            - ventas crédito
            - ventas débito 
            - financiamiento # si aparece esta palabra, colocala en la salida
            - credito # si aparece esta palabra, colocala en la salida
            - ventas nal. amex
        Reglas de la extracción multilinea, para que sea válida debe cumplir con ambas condiciones en la misma transacción:
            la primer línea debe contener:
            - t20 spei recibido santander, banorte, stp, afirme, hsbc, citi mexico
            - spei recibido banorte
            - t20 spei recibidostp
            - w02 spei recibidosantander
            - traspaso ntre cuentas
            - deposito de tercero
            - t20 spei recibido jpmorgan
            - traspaso entre cuentas propias
            - traspaso cuentas propias
            las demás líneas deben contener:
            - deposito bpu
            - mp agregador s de rl de cv 
            - anticipo {nombre comercial}
            - 0000001af
            - 0000001sq
            - trans sr pago
            - dispersion sihay ref
            - net pay sapi de cv
            - getnet mexico servicios de adquirencia s
            - payclip s de rl de cv
            - pocket de latinoamerica sapi de cv
            - cobra online sapi de cv
            - kiwi bop sa de cv
            - kiwi international payment technologies
            - traspaso entre cuentas
            - deposito de tercero
            - bmrcash ref # si aparece esta palabra, colocala en la salida
            - zettle by paypal
            - pw online mexico sapi de cv
            - liquidacion wuzi
    IMPORTANTE: Cualquier otro tipo de depósito SPEI, transferencias de otros bancos o pagos de nómina que no coincidan con las frases de arriba de forma exacta, son tratados como 'GENERALES'."""

# --- FUNCIÓN PARA EXTRAER MOVIMIENTOS CON POSICIONES ---
def detectar_rangos_y_texto(pdf_bytes: bytes) -> Tuple[Dict[int, str], List[Tuple[int, int]]]:
    """
    Escanea el PDF para extraer el texto crudo por página y detectar 
    dónde empiezan y terminan las cuentas (Rangos).
    YA NO EXTRAE MOVIMIENTOS (Eso lo hará la fase geométrica dedicada).
    """
    texto_por_pagina = {}
    rangos_detectados = []
    inicio_actual = None
    
    # Configuración de triggers (Asegúrate de tener TRIGGERS_CONFIG importado)
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            total_paginas = len(doc)
            
            for page_index, page in enumerate(doc):
                page_num = page_index + 1
                page_text = page.get_text("text").lower()
                texto_por_pagina[page_num] = page_text
                
                # --- LÓGICA DE RANGOS (INTACTA) ---
                if inicio_actual is None:
                    if any(trig in page_text for trig in TRIGGERS_CONFIG["inicio"]):
                        inicio_actual = page_num

                if inicio_actual is not None:
                    encontrado_fin = False
                    # A. Fin explícito
                    if any(trig in page_text for trig in TRIGGERS_CONFIG["fin"]):
                        rangos_detectados.append((inicio_actual, page_num))
                        inicio_actual = None
                        encontrado_fin = True
                    
                    # B. Nuevo inicio (Cascada)
                    elif page_num > inicio_actual and any(trig in page_text for trig in TRIGGERS_CONFIG["inicio"]):
                        rangos_detectados.append((inicio_actual, page_num - 1))
                        inicio_actual = page_num
                    
                    # C. Fin de documento
                    if not encontrado_fin and inicio_actual is not None and page_num == total_paginas:
                        rangos_detectados.append((inicio_actual, total_paginas))
                        inicio_actual = None

    except Exception as e:
        logger.error(f"Error detectando rangos: {e}")

    # Fallback si no hay rangos
    if not rangos_detectados:
        rangos_detectados = [(1, len(texto_por_pagina))]

    return texto_por_pagina, rangos_detectados

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
        tarea_gemini = analizar_con_ocr_fluxo(prompt, pdf_bytes, paginas_a_procesar=paginas_para_ia)

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
    tarea_gemini = analizar_con_ocr_fluxo(prompt, pdf_bytes, paginas_a_procesar=paginas_a_analizar)
    
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


def _aplicar_reglas_negocio_y_calcular_totales(self, analisis_ia, transacciones):
        """
        ÚNICA fuente de verdad para los totales.
        Ahora con matching flexible para TPV y logs de depuración.
        """
        if not analisis_ia: return

        # Inicializar en 0
        totales = {
            "EFECTIVO": 0.0, "TRASPASO": 0.0, "FINANCIAMIENTO": 0.0,
            "BMRCASH": 0.0, "MORATORIOS": 0.0, "TPV": 0.0, "DEPOSITOS": 0.0
        }
        
        # DEBUG: Contador para saber qué está pasando
        conteo_categorias = {"TPV": 0, "GENERAL": 0, "OTROS": 0}

        for tx in transacciones:
            try:
                # Limpieza robusta del monto
                monto_str = str(tx.monto).replace("$", "").replace(",", "").strip()
                monto = float(monto_str)
            except: 
                monto = 0.0
            
            # Solo nos importan los abonos para las sumas de ingresos
            # Aseguramos que el tipo se compare en minúsculas
            tipo_lower = str(tx.tipo).lower().strip()
            
            # Si NO es abono/deposito/credito, lo saltamos (es cargo)
            if tipo_lower not in ["abono", "deposito", "depósito", "credito", "crédito"]:
                continue

            # Suma al total general de depósitos
            totales["DEPOSITOS"] += monto

            desc = str(tx.descripcion).lower()
            
            # Normalizamos la categoría que viene de la IA
            cat_ia = str(tx.categoria).upper().strip()

            # --- JERARQUÍA DE REGLAS (Python manda sobre IA) ---
            
            if any(p in desc for p in PALABRAS_EXCLUIDAS):
                continue 

            if any(p in desc for p in PALABRAS_EFECTIVO):
                totales["EFECTIVO"] += monto
                tx.categoria = "EFECTIVO" # Sobrescribimos para el reporte individual
                conteo_categorias["OTROS"] += 1
                
            elif any(p in desc for p in PALABRAS_TRASPASO_ENTRE_CUENTAS):
                totales["TRASPASO"] += monto
                tx.categoria = "TRASPASO"
                conteo_categorias["OTROS"] += 1
                
            elif any(p in desc for p in PALABRAS_TRASPASO_FINANCIAMIENTO):
                totales["FINANCIAMIENTO"] += monto
                tx.categoria = "FINANCIAMIENTO"
                conteo_categorias["OTROS"] += 1
                
            elif any(p in desc for p in PALABRAS_BMRCASH):
                totales["BMRCASH"] += monto
                tx.categoria = "BMRCASH"
                conteo_categorias["OTROS"] += 1
                
            elif any(p in desc for p in PALABRAS_TRASPASO_MORATORIO):
                totales["MORATORIOS"] += monto
                tx.categoria = "MORATORIOS"
                conteo_categorias["OTROS"] += 1
                
            else:
                # --- AQUÍ ESTABA EL ERROR ---
                # Antes: if tx.categoria == "TPV":
                # Ahora: Flexible (contiene TPV o es TERMINAL)
                
                es_tpv = "TPV" in cat_ia or "TERMINAL" in cat_ia or "PUNTO DE VENTA" in cat_ia
                
                if es_tpv:
                    totales["TPV"] += monto
                    # Forzamos la etiqueta limpia para el Excel
                    tx.categoria = "TPV" 
                    conteo_categorias["TPV"] += 1
                else:
                    # Es GENERAL
                    conteo_categorias["GENERAL"] += 1
                    pass

        # LOG DE DIAGNÓSTICO (Importante para ver si está funcionando)
        # logger.info(f"📊 Resumen de Clasificación para Sumas:")
        # logger.info(f"   TPV Detectados: {conteo_categorias['TPV']} | Monto: ${totales['TPV']:,.2f}")
        # logger.info(f"   General/Otros : {conteo_categorias['GENERAL']}")
        # logger.info(f"   Reglas Python : {conteo_categorias['OTROS']}")

        # Inyectamos los totales calculados al objeto padre (AnalisisIA)
        
        analisis_ia.depositos_en_efectivo = totales["EFECTIVO"]
        analisis_ia.traspaso_entre_cuentas = totales["TRASPASO"]
        analisis_ia.total_entradas_financiamiento = totales["FINANCIAMIENTO"]
        analisis_ia.entradas_bmrcash = totales["BMRCASH"]
        analisis_ia.total_moratorios = totales["MORATORIOS"]
        analisis_ia.entradas_TPV_bruto = totales["TPV"]
        
        # Calculamos Neto
        try:
            com_str = str(analisis_ia.comisiones).replace("$", "").replace(",", "")
            comisiones = float(com_str) if analisis_ia.comisiones else 0.0
        except:
            comisiones = 0.0
            
        analisis_ia.entradas_TPV_neto = totales["TPV"] - comisiones