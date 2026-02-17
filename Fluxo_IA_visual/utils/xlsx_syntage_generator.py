import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, NamedStyle, Border, Side
from datetime import datetime

def generar_excel_syntage(data: dict) -> bytes:
    wb = Workbook()
    
    # --- ESTILOS ---
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
    sub_header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    currency_style = NamedStyle(name='currency_style', number_format='$#,##0.00')
    percent_style = NamedStyle(name='percent_style', number_format='0.00%')
    date_style = NamedStyle(name='date_style', number_format='YYYY-MM-DD')
    alert_fill = PatternFill(start_color="C0504D", end_color="C0504D", fill_type="solid")

    def estilo_header(ws, row_idx, col_start=1, col_end=None):
        if col_end is None: col_end = ws.max_column
        for col in range(col_start, col_end + 1):
            cell = ws.cell(row=row_idx, column=col)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')

    # ==========================================
    # HOJA 1: RESUMEN EJECUTIVO (MODIFICADA)
    # ==========================================
    ws1 = wb.active
    ws1.title = "Resumen Ejecutivo"
    
    # 1. Datos Contribuyente (+ Antigüedad)
    ws1.append(["DATOS DEL CONTRIBUYENTE"])
    ws1.merge_cells('A1:D1') # Expandimos a 4 columnas por el requerimiento de dividir celdas
    estilo_header(ws1, 1, 1, 4)
    
    # Cálculo Antigüedad
    antiguedad_str = "N/A"
    reg_date_str = data.get("tax_registration_date")
    if reg_date_str:
        try:
            reg_dt = datetime.fromisoformat(reg_date_str.replace("Z", ""))
            years = (datetime.now() - reg_dt).days // 365
            antiguedad_str = f"{years} Años ({reg_date_str[:10]})"
        except: pass

    ws1.append(["Razón Social", data.get("business_name", "N/A"), "Antigüedad SAT", antiguedad_str])
    ws1.append(["RFC", data.get("rfc", "N/A"), "", ""]) # Merge visual opcional

    # 2. Credenciales (CELDA PARTIDA SOLICITADA)
    ws1.append([])
    ws1.append(["ESTATUS DE CREDENCIALES"])
    ws1.merge_cells('A5:D5')
    estilo_header(ws1, 5, 1, 4)
    
    ciec = data.get("ciec_info", {})
    buro = data.get("buro_info", {})
    opinion = data.get("compliance_opinion", {})

    # Formato solicitado: Col A: Nombre, Col B: Estatus, Col C: Label Extra, Col D: Valor Extra
    ws1.append(["Credencial", "Estatus", "Detalle / Fecha", "Valor / Score"])
    estilo_header(ws1, 6, 1, 4)
    
    # Fila CIEC
    ws1.append(["CIEC", ciec.get("status"), "Última Rev:", ciec.get("last_check_date")])
    # Fila Opinión
    ws1.append(["Opinión Cumpl.", opinion.get("status"), "Última Rev:", opinion.get("last_check_date")])
    # Fila Buró (Split Solicitado)
    ws1.append(["Buró de Crédito", buro.get("status"), "Score:", buro.get("score")])

    # 3. Riesgos
    ws1.append([])
    ws1.append(["INDICADORES DE RIESGO"])
    ws1.merge_cells('A11:D11')
    estilo_header(ws1, 11, 1, 4)
    ws1.append(["Indicador", "Valor", "Riesgoso", ""])
    
    risks = data.get("risk_indicators", [])
    if risks and isinstance(risks, list):
        risk_obj = risks[0]
        for k, v in risk_obj.items():
            if isinstance(v, dict):
                es_riesgoso = "SÍ" if v.get("risky") else "NO"
                ws1.append([k, str(v.get("value")), es_riesgoso, ""])
                if v.get("risky"):
                    ws1.cell(row=ws1.max_row, column=3).fill = alert_fill

    # 4. Actividades Económicas (NUEVO)
    ws1.append([])
    ws1.append(["ACTIVIDADES ECONÓMICAS"])
    ws1.merge_cells(f'A{ws1.max_row}:D{ws1.max_row}')
    estilo_header(ws1, ws1.max_row, 1, 4)
    
    ws1.append(["Actividad", "Porcentaje", "Fecha Inicio", ""])
    acts = data.get("economic_activities", [])
    for act in acts:
        # Formatear porcentaje
        pct = act.get("percentage", 0)
        pct_str = f"{pct}%"
        ws1.append([act.get("name"), pct_str, act.get("start_date"), ""])

    ws1.column_dimensions['A'].width = 30
    ws1.column_dimensions['B'].width = 20
    ws1.column_dimensions['C'].width = 20
    ws1.column_dimensions['D'].width = 20

    # ==========================================
    # HOJA 2: FACTURACIÓN EN EL TIEMPO (RENOVADA)
    # ==========================================
    ws2 = wb.create_sheet("Facturación en el tiempo")
    
    # Matriz solicitada:
    # Cols: Last 24, 12, 9, 6, 3
    # Rows (Bloques): Revenue, Expenses, Inflows, Outflows, NFCF
    # Sub-Rows: Mean, Median Growth, Slope, CAGR
    
    periods_order = ["last_24_months", "last_12_months", "last_9_months", "last_6_months", "last_3_months"]
    metrics_map = ["revenue", "expenditures", "inflows", "outflows", "nfcf"]
    sub_metrics = [
        ("Promedio (Mean)", "mean", currency_style),
        ("Growth Rate (Median)", "median_growth_rate", percent_style),
        ("Slope (Tendencia Lineal)", "linear_slope", currency_style),
        ("CAGR / CMGR", "cagr_cmgr", percent_style)
    ]
    
    # Encabezados de Columnas
    ws2.append(["Métrica / Periodo"] + [p.replace("_", " ").title() for p in periods_order])
    estilo_header(ws2, 1)
    
    stats = data.get("stats_last_months", {})

    for metric_key in metrics_map:
        # Título de Sección (ej. REVENUE)
        ws2.append([metric_key.upper()])
        # Pintar fila de título sección
        curr_row = ws2.max_row
        ws2.cell(row=curr_row, column=1).fill = sub_header_fill
        ws2.cell(row=curr_row, column=1).font = header_font
        
        # Generar las 4 filas de sub-métricas
        for label, sub_key, style in sub_metrics:
            row_data = [label]
            for period in periods_order:
                # Navegar: stats -> period -> metric -> sub_metric
                # ej: stats['last_3_months']['revenue']['mean']
                p_data = stats.get(period) or {}
                m_data = p_data.get(metric_key) or {}
                val = m_data.get(sub_key, 0)
                row_data.append(val)
            
            ws2.append(row_data)
            
            # Aplicar estilos a las celdas de datos
            curr_row = ws2.max_row
            for col_idx in range(2, len(periods_order) + 2):
                cell = ws2.cell(row=curr_row, column=col_idx)
                cell.style = style

        # Espacio vacío
        ws2.append([""])

    ws2.column_dimensions['A'].width = 35
    for i in range(2, 7):
        ws2.column_dimensions[chr(64+i)].width = 20

    # ==========================================
    # HOJA 3: PROYECCIONES (ACTUALIZADA)
    # ==========================================
    ws3 = wb.create_sheet("Proyecciones (Escenarios)")
    
    predictions = data.get("financial_predictions", {})
    metrics_to_export = ["revenue", "expenditures", "inflows", "outflows", "nfcf"]
    raw_history = data.get("raw_data_history", [])
    
    # 1. Obtener Fechas: 12 Pasadas + 12 Futuras
    # Extraemos fechas históricas (últimos 12 meses de la raw data)
    hist_dates_iso = [x["date"] for x in raw_history[-12:]] if raw_history else []
    
    # Extraemos fechas futuras del primer modelo
    future_dates_iso = []
    first_metric = predictions.get("revenue", {})
    if first_metric and first_metric.get("linear"):
        future_dates_iso = [pt["date"] for pt in first_metric["linear"]["scenarios"]["realistic"]]
    
    # Encabezados
    headers = ["Métrica", "Modelo", "Escenario", "Growth Comp.", "Growth Proy."] 
    # Añadir fechas históricas (Colapsadas visualmente o marcadas distinto)
    headers += [f"Hist: {d}" for d in hist_dates_iso]
    # Añadir fechas futuras
    headers += [f"Proy: {d}" for d in future_dates_iso]
    
    ws3.append(headers)
    estilo_header(ws3, 1)

    for metric in metrics_to_export:
        m_data = predictions.get(metric, {})
        if not m_data: continue
        
        # Obtener valores históricos para esta métrica (últimos 12)
        # Mapeamos nombre métrica a clave en raw_data_history
        metric_key_map = {
            "revenue": "revenue", "expenditures": "expenses",
            "inflows": "inflows_amount", "outflows": "outflows_amount",
            "nfcf": "nfcf"
        }
        key = metric_key_map.get(metric)
        hist_vals = [item.get(key, 0.0) for item in raw_history[-12:]]
        
        # Rellenar ceros si falta historia
        if len(hist_vals) < 12:
            hist_vals = [0.0]*(12-len(hist_vals)) + hist_vals

        for model_type in ["linear", "exponential", "seasonal"]:
            model_res = m_data.get(model_type)
            if not model_res: continue
            
            scenarios = model_res.get("scenarios", {})
            
            # Métricas de crecimiento
            # Comparison: Forecast Total vs History Total
            g_comp_r = model_res.get('growth_realistic') 
            g_comp_o = model_res.get('growth_optimistic')
            g_comp_p = model_res.get('growth_pessimistic')

            # Projection: Trend interna (campo nuevo agregado en Forecaster)
            g_proy_r = model_res.get('trend_realistic') 
            g_proy_o = model_res.get('trend_optimistic')
            g_proy_p = model_res.get('trend_pessimistic')
            
            # Función helper para formatear fila
            def make_row(label, comp, proy, futures):
                row = [
                    metric.upper() if label == "Realista" else "", # Métrica
                    model_type.title() if label == "Realista" else "", # Modelo
                    label, # Escenario
                    comp, # Growth Comparison
                    proy  # Growth Projection
                ]
                # Agregamos historia (Siempre la REAL para contexto visual)
                row += hist_vals 
                # Agregamos futuro
                row += [pt.get("value") for pt in futures]
                return row

            # Fila Realista
            ws3.append(make_row("Realista", g_comp_r, g_proy_r, scenarios.get("realistic", [])))
            # Fila Optimista
            ws3.append(make_row("Optimista (+)", g_comp_o, g_proy_o, scenarios.get("optimistic", [])))
            # Fila Pesimista
            ws3.append(make_row("Pesimista (-)", g_comp_p, g_proy_p, scenarios.get("pessimistic", [])))
            
            ws3.append([""]) # Separador visual

    # Estilos Proyecciones
    ws3.column_dimensions['A'].width = 15
    ws3.column_dimensions['B'].width = 15
    ws3.column_dimensions['C'].width = 20
    ws3.column_dimensions['D'].width = 15
    ws3.column_dimensions['E'].width = 15
    
    # Formato Porcentaje (Cols D y E)
    for row in ws3.iter_rows(min_row=2, min_col=4, max_col=5):
        for cell in row: cell.style = percent_style
        
    # Formato Moneda (Desde Col F hasta el final)
    max_col = ws3.max_column
    for row in ws3.iter_rows(min_row=2, min_col=6, max_col=max_col):
        for cell in row: 
            if isinstance(cell.value, (int, float)):
                cell.style = currency_style

    # Separador visual entre historia y futuro
    # La columna donde empieza el futuro es 6 (A-E) + 12 (hist) = 18?
    # A=1, B=2, C=3, D=4, E=5. Historia es 6 a 17. Futuro empieza en 18.
    col_split = 5 + len(hist_vals)
    for row in range(1, ws3.max_row + 1):
        cell = ws3.cell(row=row, column=col_split)
        cell.border = Border(right=Side(style='medium', color="000000"))


    # ==========================================
    # HOJA 4: RAW DATA (NUEVA PAGINA)
    # ==========================================
    ws_raw = wb.create_sheet("Raw Data")
    
    # Encabezados solicitados
    headers_raw = [
        "startDate", "Revenue", "Expenses", 
        "Inflows mxn amounts", "Outflows mxn amounts", 
        "NFCF", "Inflows transactions", "Outflows transactions"
    ]
    ws_raw.append(headers_raw)
    estilo_header(ws_raw, 1)
    
    for item in raw_history:
        # Item es un dict (pydantic model dump)
        ws_raw.append([
            item.get("date"),
            item.get("revenue"),
            item.get("expenses"),
            item.get("inflows_amount"),
            item.get("outflows_amount"),
            item.get("nfcf"),
            item.get("inflows_transactions"),
            item.get("outflows_transactions")
        ])

    # Formatos Raw Data
    ws_raw.column_dimensions['A'].width = 15
    for i in range(2, 9): ws_raw.column_dimensions[chr(64+i)].width = 20
    
    # Moneda para cols B a F
    for row in ws_raw.iter_rows(min_row=2, min_col=2, max_col=6):
        for cell in row: cell.style = currency_style

    # ==========================================
    # HOJA 5: DETALLE DE BURÓ
    # ==========================================
    ws4 = wb.create_sheet("Detalle de Buró")
    
    buro_info = data.get("buro_info", {})
    
    # --- TABLA 1: LÍNEAS DE CRÉDITO ---
    ws4.append(["LÍNEAS DE CRÉDITO ACTIVAS E HISTÓRICAS"])
    ws4.merge_cells('A1:I1')
    estilo_header(ws4, 1, 1, 9)
    
    headers_lines = [
        "Institución", "Tipo Cuenta", "Límite Crédito", "Saldo Actual", 
        "Saldo Vencido", "Frecuencia Pago", "Fecha Apertura", "Último Pago", "Histórico Pagos"
    ]
    ws4.append(headers_lines)
    # Sub-header style
    for col in range(1, 10):
        cell = ws4.cell(row=2, column=col)
        cell.font = header_font
        cell.fill = sub_header_fill # Azul claro definido antes
        cell.alignment = Alignment(horizontal='center')

    lines = buro_info.get("credit_lines", [])
    if not lines:
        ws4.append(["No se encontró información de créditos."])
    else:
        for line in lines:
            ws4.append([
                line.get("institution"),
                line.get("account_type"),
                line.get("credit_limit"),
                line.get("current_balance"),
                line.get("past_due_balance"),
                line.get("payment_frequency"),
                line.get("opening_date"),
                line.get("last_payment_date"),
                line.get("payment_history")
            ])
            
            # Alerta visual si hay saldo vencido > 0
            saldo_vencido = line.get("past_due_balance", 0)
            if saldo_vencido > 0:
                row_idx = ws4.max_row
                ws4.cell(row=row_idx, column=5).font = Font(color="FF0000", bold=True)

    # Formato moneda para columnas C, D, E
    for row in ws4.iter_rows(min_row=3, min_col=3, max_col=5):
        for cell in row: cell.style = currency_style

    ws4.append([""]) # Separador

    # --- TABLA 2: HISTORIAL DE CONSULTAS (CREDIT PULLS) ---
    ws4.append(["HISTORIAL DE CONSULTAS (CREDIT PULLS)"])
    start_row_inq = ws4.max_row
    ws4.merge_cells(f'A{start_row_inq}:D{start_row_inq}')
    estilo_header(ws4, start_row_inq, 1, 4)
    
    headers_inq = ["Institución Solicitante", "Fecha Consulta", "Tipo Contrato", "Importe Solicitado"]
    ws4.append(headers_inq)
    # Sub-header style
    sub_head_row = ws4.max_row
    for col in range(1, 5):
        cell = ws4.cell(row=sub_head_row, column=col)
        cell.font = header_font
        cell.fill = sub_header_fill
        cell.alignment = Alignment(horizontal='center')

    inquiries = buro_info.get("inquiries", [])
    if not inquiries:
        ws4.append(["No hay consultas recientes registradas."])
    else:
        for inq in inquiries:
            ws4.append([
                inq.get("institution"),
                inq.get("inquiry_date"),
                inq.get("contract_type"),
                inq.get("amount")
            ])

    # Formato moneda columna D
    for row in ws4.iter_rows(min_row=sub_head_row+1, min_col=4, max_col=4):
        for cell in row: cell.style = currency_style

    # Ajuste anchos
    ws4.column_dimensions['A'].width = 35
    ws4.column_dimensions['B'].width = 15
    ws4.column_dimensions['C'].width = 15
    ws4.column_dimensions['D'].width = 15
    ws4.column_dimensions['G'].width = 15
    ws4.column_dimensions['H'].width = 15
    ws4.column_dimensions['I'].width = 20

    # ==========================================
    # GUARDAR
    # ==========================================
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()