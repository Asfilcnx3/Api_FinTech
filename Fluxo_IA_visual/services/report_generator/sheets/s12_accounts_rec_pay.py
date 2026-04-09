# Fluxo_IA_visual/services/report_generator/sheets/s12_accounts_rec_pay.py
from ..styles import CURRENCY_FORMAT, aplicar_estilo_header

def build(ws, data: dict):
    # Intentar obtener el objeto o instanciar uno vacío
    acc_data = data.get("accounts_receivable_payable")
    if not acc_data:
        ws.append(["No hay datos de Cuentas por Cobrar y Pagar para este RFC."])
        return

    # Si tu objeto es Pydantic, lo usamos directo. Si es un dict (depende de cómo se exporte), usamos .get()
    try:
        receivable = acc_data.receivable
        payable = acc_data.payable
    except AttributeError:
        # Si es un diccionario (al serializar)
        receivable = acc_data.get("receivable", {})
        payable = acc_data.get("payable", {})

    # Función helper para dibujar tablas
    def draw_table(title, node, start_row):
        ws.cell(row=start_row, column=1, value=title)
        
        headers = ["Start Date", "Label", "Metric (Amount)"]
        ws.append(headers)
        header_row_idx = ws.max_row
        aplicar_estilo_header(ws, header_row_idx)
        
        # Manejar si es Pydantic o Dict
        try: non_cum = node.non_cumulative
        except: non_cum = node.get("non_cumulative", [])
            
        try: cum = node.cumulative
        except: cum = node.get("cumulative", [])

        # Non-Cumulative
        ws.append(["--- No Acumulado ---"])
        for record in non_cum:
            try:
                ws.append([record.start_date, record.label, record.metric])
            except AttributeError:
                ws.append([record.get("start_date"), record.get("label"), record.get("metric")])
                
        # Cumulative
        ws.append(["--- Acumulado ---"])
        for record in cum:
            try:
                ws.append([record.start_date, record.label, record.metric])
            except AttributeError:
                ws.append([record.get("start_date"), record.get("label"), record.get("metric")])
                
        return ws.max_row + 2 # Retornar dónde debe empezar la siguiente tabla

    # Dibujar Cuentas por Cobrar
    next_row = draw_table("ACCOUNTS RECEIVABLE (Cuentas por Cobrar)", receivable, 1)
    
    # Dibujar Cuentas por Pagar
    draw_table("ACCOUNTS PAYABLE (Cuentas por Pagar)", payable, next_row)

    # Formatos
    ws.column_dimensions['A'].width = 20
    ws.column_dimensions['B'].width = 25
    ws.column_dimensions['C'].width = 20

    # Moneda para la columna C
    for row in ws.iter_rows(min_row=2, min_col=3, max_col=3):
        for cell in row:
            # Ignoramos si es un string (como "--- No Acumulado ---" o los headers)
            if isinstance(cell.value, (int, float)):
                cell.number_format = CURRENCY_FORMAT