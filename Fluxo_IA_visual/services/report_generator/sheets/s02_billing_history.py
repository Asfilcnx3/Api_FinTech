# Fluxo_IA_visual/services/report_generator/sheets/s02_billing_history.py
from ..styles import (
    HEADER_FONT, SUB_HEADER_FILL, 
    CURRENCY_FORMAT, PERCENT_FORMAT, 
    aplicar_estilo_header
)

def build(ws, data: dict):
    periods_order = ["last_24_months", "last_12_months", "last_9_months", "last_6_months", "last_3_months"]
    metrics_map = ["revenue", "expenditures", "inflows", "outflows", "nfcf"]
    
    # Formatos ahora apuntan directamente a nuestras constantes string
    sub_metrics = [
        ("Promedio (Mean)", "mean", CURRENCY_FORMAT),
        ("Mediana (Median)", "median", CURRENCY_FORMAT),
        ("Crecimiento vs Periodo Anterior", "period_growth_rate", PERCENT_FORMAT),
        ("Slope (Tendencia Lineal)", "linear_slope", CURRENCY_FORMAT),
        ("CAGR / CMGR", "cagr_cmgr", PERCENT_FORMAT)
    ]
    
    ws.append(["Métrica / Periodo"] + [p.replace("_", " ").title() for p in periods_order])
    aplicar_estilo_header(ws, 1)
    
    stats = data.get("stats_last_months", {})

    for metric_key in metrics_map:
        ws.append([metric_key.upper()])
        curr_row = ws.max_row
        ws.cell(row=curr_row, column=1).fill = SUB_HEADER_FILL
        ws.cell(row=curr_row, column=1).font = HEADER_FONT
        
        for label, sub_key, fmt in sub_metrics:
            row_data = [label]
            for period in periods_order:
                p_data = stats.get(period) or {}
                m_data = p_data.get(metric_key) or {}
                val = m_data.get(sub_key, 0)
                row_data.append(val)
            
            ws.append(row_data)
            
            curr_row = ws.max_row
            for col_idx in range(2, len(periods_order) + 2):
                ws.cell(row=curr_row, column=col_idx).number_format = fmt

        ws.append([""])

    ws.column_dimensions['A'].width = 35
    for i in range(2, 7):
        ws.column_dimensions[chr(64+i)].width = 20