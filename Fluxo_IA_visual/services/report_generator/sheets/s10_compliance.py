from openpyxl.styles import Alignment, Font
from ..styles import aplicar_estilo_header

def build(ws, data: dict):
    ws.append(["ANÁLISIS DE LA OPINIÓN DE CUMPLIMIENTO (32-D) CON IA"])
    ws.merge_cells('A1:E1')
    aplicar_estilo_header(ws, 1, 1, 5)
    
    ws.append([])
    
    ws.append(["Resumen y Hallazgos del Documento Original:"])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
    
    # Obtenemos la explicación que inyectó el RiskProcessor
    explanation = data.get("compliance_llm_explanation", "Sin análisis disponible.")
    
    ws.append([explanation])
    ws.merge_cells(start_row=ws.max_row, start_column=1, end_row=ws.max_row, end_column=5)
    
    # Formato para que el texto largo se acomode automáticamente
    ws.cell(row=ws.max_row, column=1).alignment = Alignment(wrap_text=True, vertical='top')
    ws.row_dimensions[ws.max_row].height = 80 # Altura suficiente para 4 renglones
    
    ws.column_dimensions['A'].width = 30