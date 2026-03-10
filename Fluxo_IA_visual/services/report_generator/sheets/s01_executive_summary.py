# Fluxo_IA_visual/services/report_generator/sheets/s01_executive_summary.py
from openpyxl.styles import Font, Alignment
from datetime import datetime
from ..styles import (
    HEADER_FONT, HEADER_FILL, SUB_HEADER_FILL, ALERT_FILL, 
    CURRENCY_FORMAT, PERCENT_FORMAT, 
    aplicar_estilo_header, aplicar_estilo_subheader
)

def build(ws, data: dict):
    # 1. DATOS DEL CONTRIBUYENTE
    ws.append(["DATOS DEL CONTRIBUYENTE"])
    ws.merge_cells('A1:D1')
    aplicar_estilo_header(ws, 1, 1, 4)
    
    antiguedad_str = "N/A"
    reg_date_str = data.get("tax_registration_date")
    if reg_date_str:
        try:
            reg_dt = datetime.fromisoformat(reg_date_str.replace("Z", ""))
            years = (datetime.now() - reg_dt).days // 365
            antiguedad_str = f"{years} Años ({reg_date_str[:10]})"
        except: pass

    ws.append(["Razón Social", data.get("business_name", "N/A"), "Antigüedad SAT", antiguedad_str])
    ws.append(["RFC", data.get("rfc", "N/A"), "", ""])

    # 2. ESTATUS DE CREDENCIALES
    ws.append([])
    ws.append(["ESTATUS DE CREDENCIALES"])
    ws.merge_cells('A5:D5')
    aplicar_estilo_header(ws, 5, 1, 4)
    
    ws.append(["Credencial", "Estatus", "Detalle / Fecha", "Valor / Score"])
    aplicar_estilo_header(ws, 6, 1, 4)

    def format_ciec_date(date_str):
        if not date_str: return ""
        try:
            d = datetime.fromisoformat(str(date_str).replace("Z", "").split(".")[0])
            return f"{d.month}/{d.day}/{d.year}"
        except: return date_str
    
    ciec = data.get("ciec_info", {})
    buro = data.get("buro_info", {})
    opinion = data.get("compliance_opinion", {})

    ws.append(["CIEC", ciec.get("status"), "Última Rev:", ciec.get("last_check_date")])
    ws.append(["CIEC última extracción", ciec.get("status"), "última extracción", format_ciec_date(ciec.get("last_extraction_date"))])
    ws.append(["Opinión Cumpl.", opinion.get("status"), "Última Rev:", opinion.get("last_check_date")])
    ws.append(["Buró de Crédito", buro.get("status"), "Score:", buro.get("score")])

    # 3. INDICADORES DE RIESGO
    ws.append([])
    ws.append(["INDICADORES DE RIESGO"])
    fila_actual = ws.max_row
    ws.merge_cells(f'A{fila_actual}:D{fila_actual}')
    aplicar_estilo_header(ws, fila_actual, 1, 4)
    ws.append(["Indicador", "Valor", "Riesgoso", ""])
    
    risks = data.get("risk_indicators", [])
    if risks and isinstance(risks, list):
        risk_obj = risks[0]
        for k, v in risk_obj.items():
            if isinstance(v, dict):
                es_riesgoso = "SÍ" if v.get("risky") else "NO"
                ws.append([k, str(v.get("value")), es_riesgoso, ""])
                if v.get("risky"):
                    ws.cell(row=ws.max_row, column=3).fill = ALERT_FILL

    # 4. ACTIVIDADES ECONÓMICAS
    ws.append([])
    ws.append(["ACTIVIDADES ECONÓMICAS"])
    ws.merge_cells(f'A{ws.max_row}:D{ws.max_row}')
    aplicar_estilo_header(ws, ws.max_row, 1, 4)
    ws.append(["Actividad", "Porcentaje", "Fecha Inicio", ""])
    acts = data.get("economic_activities", [])
    for act in acts:
        pct_str = f"{act.get('percentage', 0)}%"
        ws.append([act.get("name"), pct_str, act.get("start_date"), ""])

    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 20
    ws.column_dimensions['D'].width = 20

    # 5. RESUMEN DE BURÓ
    summary = buro.get("summary_metrics")
    if summary:
        ws.append([])
        ws.append(["RESUMEN DE BURÓ"])
        ws.merge_cells(f'A{ws.max_row}:D{ws.max_row}')
        aplicar_estilo_header(ws, ws.max_row, 1, 4)

        trend_pct = summary.get("inquiries_trend_pct", 0.0)
        if trend_pct > 0:
            ws.append(["", "Han ido aumentando sus consultas", trend_pct, ""])
            ws.cell(row=ws.max_row, column=3).number_format = PERCENT_FORMAT
        elif trend_pct < 0:
            ws.append(["", "Han ido disminuyendo sus consultas", trend_pct, ""])
            ws.cell(row=ws.max_row, column=3).number_format = PERCENT_FORMAT
        else:
            ws.append(["", "Estables", "0%", ""])
            
        ws.append([])
        
        metricas_globales = [
            ("Monto Máximo Abierto", summary.get("total_open_max_amount", 0.0), CURRENCY_FORMAT),
            ("Saldo Vigente", summary.get("total_current_balance", 0.0), CURRENCY_FORMAT),
            ("Saldo Vencido Total", summary.get("total_past_due", 0.0), CURRENCY_FORMAT),
            ("Pago Mensual 1", summary.get("monthly_payment_1", 0.0), CURRENCY_FORMAT),
            ("Pago Mensual 2", summary.get("monthly_payment_2", 0.0), CURRENCY_FORMAT),
            ("Plazo Ponderado (años)", summary.get("weighted_term_years", 0.0), '0.00')
        ]
        for titulo, valor, fmt in metricas_globales:
            ws.append([titulo, valor, "", ""])
            ws.cell(row=ws.max_row, column=2).number_format = fmt

        ws.append([])
        
        def print_bucket(label, key):
            b_data = summary.get(key, {})
            amt = b_data.get("amount", 0.0)
            pct = b_data.get("percentage", 0.0)
            val_str = amt if amt > 0 else "-"
            ws.append([label, val_str, pct if amt > 0 else "", ""])
            if amt > 0:
                ws.cell(row=ws.max_row, column=2).number_format = CURRENCY_FORMAT
                ws.cell(row=ws.max_row, column=3).number_format = PERCENT_FORMAT
            else:
                ws.cell(row=ws.max_row, column=2).alignment = Alignment(horizontal='right')

        print_bucket("saldoVencidoDe1a29Dias", "bucket_1_29")
        print_bucket("saldoVencidoDe30a59Dias", "bucket_30_59")
        print_bucket("saldoVencidoDe60a89Dias", "bucket_60_89")
        print_bucket("saldoVencidoDe90a119Dias", "bucket_90_119")
        print_bucket("saldoVencidoDe120a179Dias", "bucket_120_179")
        print_bucket("saldoVencidoDe180DiasOMas", "bucket_180_plus")

    # 6. RESUMEN FINANCIERO (BALANCE Y RESULTADOS)
    financials = data.get("financial_ratios_history", [])
    if financials:
        financials_sorted = sorted(financials, key=lambda x: str(x.get("year", "")))
        years = [str(f.get("year", "N/A")) for f in financials_sorted]
        max_cols = len(years) + 1

        ws.append([])
        ws.append(["RESUMEN FINANCIERO (BALANCE Y RESULTADOS)"] + [""] * (len(years) - 1))
        ws.merge_cells(start_row=ws.max_row, start_column=1, end_row=ws.max_row, end_column=max_cols)
        aplicar_estilo_header(ws, ws.max_row, 1, max_cols)

        ws.append(["Concepto"] + years)
        aplicar_estilo_subheader(ws, ws.max_row, 1, max_cols)

        def print_fin_row(label, key, is_bold=False):
            row_data = [label]
            for f in financials_sorted:
                row_data.append(f.get(key, 0.0))
            ws.append(row_data)
            
            curr_row = ws.max_row
            if is_bold: ws.cell(row=curr_row, column=1).font = Font(bold=True)
            for col_idx in range(2, max_cols + 1):
                ws.cell(row=curr_row, column=col_idx).number_format = CURRENCY_FORMAT

        ws.append(["BALANCE GENERAL"] + [""] * len(years))
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True, italic=True)
        
        print_fin_row("Activo", "input_assets")
        print_fin_row("Pasivo", "input_liabilities")
        print_fin_row("Capital Contable", "input_equity")
        
        ws.append([]) 

        ws.append(["ESTADO DE RESULTADOS"] + [""] * len(years))
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True, italic=True)

        print_fin_row("Ingresos Netos", "input_revenue")
        print_fin_row("Utilidad (Pérdida) Bruta", "input_gross_profit")
        print_fin_row("Utilidad (Pérdida) de Operación", "ebit")
        print_fin_row("Utilidad (Pérdida) antes de Impuestos", "ebt")
        print_fin_row("Impuestos a la Utilidad", "input_taxes")
        print_fin_row("Utilidad (Pérdida) Neta", "input_net_income", is_bold=True)