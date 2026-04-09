# Fluxo_IA_visual/services/report_generator/sheets/s13_financial_institutions.py
from ..styles import CURRENCY_FORMAT, aplicar_estilo_header

def build(ws, data: dict):
    institutions = data.get("financial_institutions", [])

    headers = [
        "RFC",
        "Razón Social",
        "Nombre Comercial",
        "Sitio Web",
        "Sector",
        "Monto Total (Últimos 3 años)",
        "Primera Transacción",
        "Última Transacción",
        "Meses con Actividad"
    ]
    ws.append(headers)
    aplicar_estilo_header(ws, 1)

    if not institutions:
        ws.append(["No se encontraron operaciones con instituciones financieras en los últimos 3 años."])
    else:
        for inst in institutions:
            # Como es un modelo Pydantic, accedemos con la sintaxis de punto
            try:
                ws.append([
                    inst.rfc,
                    inst.legal_name,
                    inst.trade_name,
                    inst.website,
                    inst.sector,
                    inst.total_amount,
                    inst.first_transaction_date,
                    inst.last_transaction_date,
                    inst.transaction_count
                ])
            except AttributeError:
                # Fallback de seguridad por si en algún punto llega como diccionario
                ws.append([
                    inst.get("rfc"),
                    inst.get("legal_name"),
                    inst.get("trade_name"),
                    inst.get("website"),
                    inst.get("sector"),
                    inst.get("total_amount", 0.0),
                    inst.get("first_transaction_date"),
                    inst.get("last_transaction_date"),
                    inst.get("transaction_count", 0)
                ])

    # --- FORMATOS Y ANCHOS DE COLUMNA ---
    widths = {
        'A': 15,  # RFC
        'B': 45,  # Razón Social
        'C': 30,  # Nombre Comercial
        'D': 25,  # Website
        'E': 40,  # Sector
        'F': 25,  # Monto Total
        'G': 20,  # Primera
        'H': 20,  # Última
        'I': 20   # Meses Activos
    }
    
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    # Formato Moneda solo para la columna F (índice 6)
    for row in ws.iter_rows(min_row=2, min_col=6, max_col=6):
        for cell in row:
            if isinstance(cell.value, (int, float)):
                cell.number_format = CURRENCY_FORMAT