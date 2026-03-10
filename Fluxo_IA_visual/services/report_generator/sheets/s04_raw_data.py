# Fluxo_IA_visual/services/report_generator/sheets/s04_raw_data.py
from ..styles import CURRENCY_FORMAT, aplicar_estilo_header

def build(ws, data: dict):
    raw_history = data.get("raw_data_history", [])
    
    headers_raw = [
        "startDate", "Revenue", "Expenses", 
        "Inflows mxn amounts", "Outflows mxn amounts", 
        "NFCF", "Inflows transactions", "Outflows transactions"
    ]
    ws.append(headers_raw)
    aplicar_estilo_header(ws, 1)
    
    for item in raw_history:
        # Extraemos con fallback seguro por si hay diferencias de tipado
        ws.append([
            item.get("date"),
            item.get("revenue", 0.0),
            item.get("expenses", 0.0),
            item.get("inflows_amount", 0.0),
            item.get("outflows_amount", 0.0),
            item.get("nfcf", 0.0),
            item.get("inflows_count", 0),  # Notar que en tu modelo se llamaba _count
            item.get("outflows_count", 0)
        ])

    # Formatos Raw Data
    ws.column_dimensions['A'].width = 15
    for i in range(2, 9): 
        ws.column_dimensions[chr(64+i)].width = 20
    
    # Moneda para cols B a F (índices 2 al 6)
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=6):
        for cell in row: 
            cell.number_format = CURRENCY_FORMAT