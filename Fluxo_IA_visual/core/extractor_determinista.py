import re
import json

class ExtractorDeterministaOCR:
    def __init__(self):
        self.rx_fecha = re.compile(r'^(\d{2}/\d{2}/\d{4}|0[1-9]|[12]\d|3[01])(?=\s|$)')
        self.rx_monto = re.compile(r'[+-]?\$?\s*\d{1,3}(?:,\d{3})*\.\d{2}')
        self.triggers_basura = [
            "ESTE DOCUMENTO ES UNA REPRESENTACIÓN", "SELLO DIGITAL", "CADENA ORIGINAL", 
            "IPAB", "FONDOS DE INVERSION", "SUMA DE RETIROS", "DETALLES DEL CRÉDITO", 
            "SALDO A FECHA DE CORTE", "COMPROBANTE FISCAL", "FOLIO FISCAL",
            "BANCA MIFEL, S.A", "WWW.MIFEL.COM.MX", "RÉGIMEN FISCAL", "ESTADO DE CUENTA", 
            "CUENTA A LA VISTA", "PÁGINA", "PAGINA", "RFC:", "PROTECCIÓN PARA LA",
            "INSTITUTO AL AHORRO", "REFERENCIA DE ABREVIATURAS", "MENSAJES IMPORTANTES",
            "ACLARACIONES", "CONDUSEF", "INFORMACION IMPORTANTE"
        ]

    def _limpiar_monto(self, texto: str) -> float:
        match = self.rx_monto.search(texto)
        if match:
            try:
                limpio = match.group(0).replace('$', '').replace(',', '').strip()
                return float(limpio)
            except ValueError:
                return 0.0
        return 0.0

    def detectar_carriles(self, filas_estructuradas):
        coordenadas_dinero = []
        for fila in filas_estructuradas[:150]: 
            for bloque in fila["bloques"]:
                if self.rx_monto.search(bloque['texto'].strip()):
                    coordenadas_dinero.append(bloque['left'])
                    
        if len(coordenadas_dinero) < 10:
            return {"retiro": 0.595, "deposito": 0.710, "saldo": 0.825}
            
        coordenadas_dinero.sort()
        
        grupos = []
        grupo_actual = [coordenadas_dinero[0]]
        
        for x in coordenadas_dinero[1:]:
            if x - grupo_actual[-1] < 0.04: 
                grupo_actual.append(x)
            else:
                grupos.append(grupo_actual)
                grupo_actual = [x]
        grupos.append(grupo_actual)
        
        grupos.sort(key=len, reverse=True)
        top_grupos = grupos[:3]
        
        centros = sorted([sum(g) / len(g) for g in top_grupos])
        carriles = {}
        
        if len(centros) == 3:
            carriles["retiro"] = centros[0]
            carriles["deposito"] = centros[1]
            carriles["saldo"] = centros[2]
        elif len(centros) == 2:
            if centros[1] > 0.78: 
                carriles["saldo"] = centros[1]
                if centros[0] < 0.65: carriles["retiro"] = centros[0]
                else: carriles["deposito"] = centros[0]
            else:
                carriles["retiro"] = centros[0]
                carriles["deposito"] = centros[1]
                
        if "retiro" not in carriles: carriles["retiro"] = 0.595
        if "deposito" not in carriles: carriles["deposito"] = 0.710
        if "saldo" not in carriles: carriles["saldo"] = 0.825
        
        return carriles

    def asignar_columna_monto(self, x_obj, carriles, margen=0.08):
        distancias = {
            "retiro": abs(x_obj - carriles["retiro"]),
            "deposito": abs(x_obj - carriles["deposito"]),
            "saldo": abs(x_obj - carriles["saldo"])
        }
        mejor_columna = min(distancias, key=distancias.get)
        if distancias[mejor_columna] <= margen:
            return mejor_columna
        return None

    def _evaluar_estado_tabla(self, texto_limpio, indice_fila, filas_estructuradas):
        score_enviados = 0
        score_recibidos = 0
        
        if any(k in texto_limpio for k in ["SPEI", "SPEL", "TRANSFERENCIA", "TRASPASO"]):
            score_enviados += 1
            score_recibidos += 1
            
        if any(k in texto_limpio for k in ["ENVIAD", "SALIDA", "RETIRO", "EMITID"]):
            score_enviados += 2
        if any(k in texto_limpio for k in ["RECIBID", "ENTRADA", "DEPOSITO", "COBRANZA"]):
            score_recibidos += 2
            
        if "DETALLEDEMOVIMIENTOS" in texto_limpio and "SPEI" not in texto_limpio:
            return "PRINCIPAL"
        if any(k in texto_limpio for k in ["DETALLESDELCREDITO", "DETALLESDELCRÉDITO", "INVERSIONES", "POSICIÓN", "RESUMENFISCAL", "CREDITO"]):
            return "OTRAS_TABLAS"

        if score_enviados == 0 and score_recibidos == 0:
            return None

        montos_por_fila = []
        filas_futuras = filas_estructuradas[indice_fila + 1 : indice_fila + 6]
        
        for f in filas_futuras:
            montos = [b for b in f["bloques"] if self.rx_monto.search(b['texto'].strip())]
            if len(montos) > 0:
                montos_por_fila.append(len(montos))
                
        if montos_por_fila:
            if all(cantidad == 1 for cantidad in montos_por_fila):
                score_enviados += 2
                score_recibidos += 2
            elif any(cantidad >= 2 for cantidad in montos_por_fila):
                score_enviados -= 3
                score_recibidos -= 3

        UMBRAL = 3 
        if score_enviados >= UMBRAL and score_enviados > score_recibidos:
            return "SPEI_ENVIADOS"
        elif score_recibidos >= UMBRAL and score_recibidos > score_enviados:
            return "SPEI_RECIBIDOS"
            
        return None
    
    def procesar_transacciones(self, filas_estructuradas, saldo_inicial):
        carriles = self.detectar_carriles(filas_estructuradas)
        transacciones = []
        slice_actual = None
        saldo_arrastre = saldo_inicial
        seccion_actual = "PRINCIPAL"

        for i, fila in enumerate(filas_estructuradas):
            texto_unido_clean = fila["texto_unido"].upper().replace(" ", "").replace("_", "")
            
            if any(k in texto_unido_clean for k in ["SPEI", "SPEL"]) and "RECIBID" in texto_unido_clean:
                seccion_actual = "SPEI_RECIBIDOS"
                continue
            elif any(k in texto_unido_clean for k in ["SPEI", "SPEL"]) and "ENVIAD" in texto_unido_clean:
                seccion_actual = "SPEI_ENVIADOS"
                continue
            elif "DETALLEDEMOVIMIENTOS" in texto_unido_clean and "SPEI" not in texto_unido_clean:
                seccion_actual = "PRINCIPAL"
                continue
                
            if any(basura.replace(" ", "") in texto_unido_clean for basura in [t.replace(" ", "") for t in self.triggers_basura]):
                continue 

            bloques = fila["bloques"]
            if not bloques: continue

            fecha_encontrada = None
            tiene_dinero = any(self.rx_monto.search(b['texto']) for b in bloques)
            
            for b in bloques[:3]: 
                txt_b = b['texto'].strip()
                match_fecha = self.rx_fecha.match(txt_b)
                if match_fecha:
                    fecha_encontrada = match_fecha.group(1) or match_fecha.group(2)
                    break
            
            if fecha_encontrada and tiene_dinero:
                if slice_actual:
                    tx_val, saldo_arrastre = self._consolidar_y_validar(slice_actual, carriles, saldo_arrastre)
                    if tx_val: transacciones.append(tx_val)
                
                slice_actual = {
                    "fecha": fecha_encontrada,
                    "seccion": seccion_actual,
                    "elementos": [b for b in bloques if b['texto'].strip() != fecha_encontrada] 
                }
            elif slice_actual:
                if len(slice_actual["elementos"]) < 40: 
                    slice_actual["elementos"].extend(bloques)

        if slice_actual:
            tx_val, saldo_arrastre = self._consolidar_y_validar(slice_actual, carriles, saldo_arrastre)
            if tx_val: transacciones.append(tx_val)

        return transacciones

    def _consolidar_y_validar(self, slice_data, carriles, saldo_arrastre):
        seccion = slice_data["seccion"]
        retiro_val = 0.0
        deposito_val = 0.0
        saldo_leido = None
        importe_generico = 0.0
        descripcion_tokens = []
        
        requiere_revision = False
        saldo_inferido = None

        for item in slice_data["elementos"]:
            txt = item['texto'].strip()
            if self.rx_monto.search(txt):
                monto_val = self._limpiar_monto(txt)
                
                if seccion == "PRINCIPAL":
                    columna = self.asignar_columna_monto(item['left'], carriles)
                    if columna == "retiro": retiro_val = monto_val
                    elif columna == "deposito": deposito_val = monto_val
                    elif columna == "saldo": saldo_leido = monto_val
                    else: descripcion_tokens.append(txt) 
                else:
                    if monto_val > importe_generico:
                        importe_generico = monto_val
            else:
                descripcion_tokens.append(txt)

        importe_final = 0.0
        tipo_final = "IMPORTE"

        if seccion == "PRINCIPAL":
            if retiro_val > 0:
                importe_final = retiro_val
                tipo_final = "CARGO"
            elif deposito_val > 0:
                importe_final = deposito_val
                tipo_final = "ABONO"
                
            if saldo_leido is not None:
                saldo_esperado = round(saldo_arrastre - retiro_val + deposito_val, 2)
                if abs(saldo_esperado - saldo_leido) > 0.01:
                    requiere_revision = True
                    saldo_inferido = saldo_esperado
                    saldo_arrastre = saldo_esperado
                else:
                    saldo_arrastre = saldo_leido
            else:
                requiere_revision = True
                saldo_inferido = round(saldo_arrastre - retiro_val + deposito_val, 2)
                saldo_arrastre = saldo_inferido
        else:
            importe_final = importe_generico
            if seccion == "SPEI_RECIBIDOS": tipo_final = "ABONO"
            elif seccion == "SPEI_ENVIADOS": tipo_final = "CARGO"

        if importe_final == 0.0:
            return None, saldo_arrastre

        tx = {
            "fecha": slice_data["fecha"],
            "descripcion": " ".join(descripcion_tokens),
            "importe": importe_final,
            "tipo": tipo_final,
            "seccion": seccion 
        }

        if requiere_revision:
            tx["requiere_revision"] = True
            tx["saldo_inferido"] = saldo_inferido

        return tx, saldo_arrastre
    
    def deduplicar_transacciones(self, todas_las_transacciones):
        PALABRAS_IGNORADAS = {"de", "la", "el", "en", "por", "para", "un", "una", "spei", "pago", "envio", "transferencia", "cv", "sa", "banco"}

        def obtener_palabras_clave(texto: str) -> set:
            limpio = re.sub(r'[^\w\s]', ' ', str(texto).lower())
            return set(p for p in limpio.split() if len(p) > 2 and p not in PALABRAS_IGNORADAS)

        kw_transferencias = ["SPEI", "SPEL", "TRASPASO", "TRANSF", "TRANSFERENCIA", "PAGO", "NETNM", "SOBRANTE"]
        
        padres_candidatos = [
            tx for tx in todas_las_transacciones 
            if tx.get("seccion") == "PRINCIPAL" 
            and any(k in tx.get("descripcion", "").upper() for k in kw_transferencias)
        ]
        
        padres_intocables = [
            tx for tx in todas_las_transacciones 
            if tx.get("seccion") == "PRINCIPAL" 
            and not any(k in tx.get("descripcion", "").upper() for k in kw_transferencias)
        ]
        
        hijos_recibidos = [tx for tx in todas_las_transacciones if tx.get("seccion") == "SPEI_RECIBIDOS"]
        hijos_enviados = [tx for tx in todas_las_transacciones if tx.get("seccion") == "SPEI_ENVIADOS"]
        hijos = hijos_recibidos + hijos_enviados
        
        ids_hijos_fusionados = set()

        for hijo in hijos:
            fecha_hijo = hijo["fecha"]
            importe_hijo = float(hijo["importe"])
            palabras_hijo = obtener_palabras_clave(hijo["descripcion"])

            candidatos = [
                p for p in padres_candidatos 
                if p["fecha"][:2] == fecha_hijo[:2] 
                and abs(float(p["importe"]) - importe_hijo) < 0.01 
            ]

            if len(candidatos) == 1:
                padre = candidatos[0]
                padre["descripcion"] = f"{padre['descripcion']} | DETALLE: {hijo['descripcion']}"
                ids_hijos_fusionados.add(id(hijo))
                continue

            if len(candidatos) > 1:
                for padre in candidatos:
                    palabras_padre = obtener_palabras_clave(padre["descripcion"])
                    coincidencias = palabras_hijo.intersection(palabras_padre)
                    
                    if len(coincidencias) >= 1:
                        padre["descripcion"] = f"{padre['descripcion']} | DETALLE: {hijo['descripcion']}"
                        ids_hijos_fusionados.add(id(hijo))
                        break

        hijos_restantes = [h for h in hijos if id(h) not in ids_hijos_fusionados]
        lista_final = padres_candidatos + padres_intocables + hijos_restantes

        for tx in lista_final:
            tx.pop("seccion", None)

        lista_final.sort(key=lambda x: x["fecha"])
        return lista_final