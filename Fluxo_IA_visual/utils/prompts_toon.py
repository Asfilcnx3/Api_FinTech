"""
Prompts en formato TOON para extracción OCR con Qwen-VL.

El formato TOON (Table-Object-Ordered-Notation) estructura la salida para:
- Máxima velocidad de parsing
- Consistencia en los datos
- Fácil validación
"""

# Prompt base para todos los documentos
HEADER_TOON = """
=== INSTRUCCIONES DE EXTRACCIÓN ===

Eres un sistema OCR de alta precisión. Analiza las imágenes del documento y extrae TODOS los campos solicitados.

REGLAS OBLIGATORIAS:
1. Responde ÚNICAMENTE en formato TOON (Table-Object-Ordered-Notation)
2. Los valores NULL deben escribirse como NULL
3. Los números deben ir sin símbolos $ ni comas (ej: 31001.50)
4. Las fechas en formato YYYY-MM-DD
5. Texto en MAYÚSCULAS
6. Si no encuentras un campo, usa NULL (no inventes valores)

FORMATO TOON:
<<<TOON_START>>>
campo1::valor1
campo2::valor2
campo3::valor3
<<<TOON_END>>>

=== CAMPOS A EXTRAER ===
"""

# Prompt específico para RECIBO DE NÓMINA
PROMPT_TOON_NOMINA = HEADER_TOON + """
TIPO: RECIBO DE NÓMINA (CFDI)

CAMPOS REQUERIDOS:
- nombre::unicamente el nombre del empleado
- apellido_paterno::unicamente el primer apellido
- apellido_materno::unicamente el segundo apellido
- rfc::captura el que esté cerca del nombre, normalmente aparece como "r.f.c", los primeros 10 caracteres del rfc y curp son iguales
- curp::es un código de 4 letras, 6 números, 6 letras y 2 números
- dependencia::Secretaría o institución pública
- secretaria::(ejemplo: 'Gobierno del Estado de Puebla' o 'SNTE')
- numero_empleado::puede aparecer como  'NO. EMPLEADO'
- puesto_cargo::Puesto o cargo, puede aparecer como 'DESCRIPCIÓN DEL PUESTO'
- categoria::(ejemplo: "07", "08", "T")
- salario_neto::Normalmente aparece como 'Importe Neto'
- total_percepciones::aparece a la derecha de 'Total percepciones'
- total_deducciones::aparece a la derecha de 'Total deducciones'
- periodo_inicio::Devuelve en formato "2025-12-25"
- periodo_fin::Devuelve en formato "2025-12-25"
- fecha_pago::Devuelve en formato "2025-12-25"
- periodicidad::(es la cantidad de días entre periodo_inicio y periodo_fin pero en palabra, ejemplo: "Quincenal", "Mensual") 
- error_lectura_nomina::Null por defecto

VALIDACIÓN:
- El RFC debe tener 12-13 caracteres
- El CURP debe tener 18 caracteres
- Las fechas deben ser válidas
- Los montos deben ser números positivos

Responde SOLO con el bloque TOON. Sin explicaciones adicionales.
Ignora cualquier otra parte del documento. No infieras ni estimes valores.
En caso de no encontrar ninguna similitud, coloca Null en todas y al final retorna en "error_lectura_nomina" un "Documento sin coincidencias" 
"""

# Prompt específico para ESTADO DE CUENTA
PROMPT_TOON_ESTADO = HEADER_TOON + """
TIPO: ESTADO DE CUENTA BANCARIO

CAMPOS REQUERIDOS:
- clabe:: puede iniciar con 0 el número de cuenta clabe del usuario/cliente, puede aparecer como 'No. cuenta CLABE', extraelo todo
- nombre_usuario:: el nombre del usuario/cliente
- rfc:: captura el que esté cerca del nombre, normalmente aparece como "r.f.c"
- numero_cuenta:: el número de cuenta, puede aparecer como 'No. de Cuenta'
- error_lectura_estado:: Null por defecto

VALIDACIÓN:
- CLABE debe tener 18 dígitos
- RFC debe ser válido (12-13 caracteres)
- Las fechas en formato correcto

Responde SOLO con el bloque TOON. Sin explicaciones adicionales.
Ignora cualquier otra parte del documento. No infieras ni estimes valores.
En caso de no encontrar ninguna similitud, coloca Null en todas y al final retorna en "error_lectura_estado" un "Documento sin coincidencias" 
"""

# Prompt específico para COMPROBANTE DE DOMICILIO
PROMPT_TOON_COMPROBANTE = HEADER_TOON + """
TIPO: COMPROBANTE DE DOMICILIO (Recibo de servicio)

CAMPOS REQUERIDOS:
- domicilio::El domicilio completo, normalmente está junto al nombre del cliente
- inicio_periodo::Inicio del periodo facturado (YYYY-MM-DD)
- fin_periodo::Fin del periodo facturado (YYYY-MM-DD)

VALIDACIÓN:
- El domicilio debe ser una dirección completa
- Fechas en formato YYYY-MM-DD
- A veces el periodo puede no ser un rango de fechas sino un mes, en este caso el inicio y fin serán la misma fecha en el formato indicado.

Responde SOLO con el bloque TOON. Sin explicaciones adicionales.
Ignora cualquier otra parte del documento. No infieras ni estimes valores.
En caso de no encontrar ninguna similitud, coloca Null en todas y al final retorna en "error_lectura_estado" un "Documento sin coincidencias" 
"""

# Segunda nómina (versión reducida)
PROMPT_TOON_NOMINA_SEGUNDA = HEADER_TOON + """
TIPO: SEGUNDO RECIBO DE NÓMINA (CFDI) - Versión Compacta

CAMPOS REQUERIDOS:
- nombre::unicamente el nombre del empleado
- apellido_paterno::unicamente el primer apellido
- apellido_materno::unicamente el segundo apellido
- rfc::captura el que esté cerca del nombre, normalmente aparece como "r.f.c", los primeros 10 caracteres del rfc y curp son iguales
- curp::es un código de 4 letras, 6 números, 6 letras y 2 números
- error_lectura_nomina::Null por defecto

VALIDACIÓN:
- el RFC debe tener 12-13 caracteres
- el CURP debe tener 18 caracteres

Responde SOLO con el bloque TOON.
Ignora cualquier otra parte del documento. No infieras ni estimes valores.
En caso de no encontrar ninguna similitud, coloca Null en todas y al final retorna en "error_lectura_nomina" un "Documento sin coincidencias" 
"""

# Helper para construir prompts personalizados
def construir_prompt_toon(
    tipo_documento: str,
    campos_requeridos: list,
    campos_opcionales: list = None,
    instrucciones_extra: str = ""
) -> str:
    """
    Construye un prompt TOON personalizado.
    
    Args:
        tipo_documento: Nombre del tipo de documento
        campos_requeridos: Lista de campos obligatorios
        campos_opcionales: Lista de campos opcionales
        instrucciones_extra: Instrucciones adicionales
        
    Returns:
        Prompt completo en formato string
    """
    campos_opcionales = campos_opcionales or []
    
    prompt = HEADER_TOON + f"\nTIPO: {tipo_documento}\n\n"
    prompt += "CAMPOS REQUERIDOS:\n"
    for campo in campos_requeridos:
        prompt += f"- {campo}::Descripción del campo\n"
    
    if campos_opcionales:
        prompt += "\nCAMPOS OPCIONALES:\n"
        for campo in campos_opcionales:
            prompt += f"- {campo}::Descripción del campo\n"
    
    if instrucciones_extra:
        prompt += f"\nINSTRUCCIONES ADICIONALES:\n{instrucciones_extra}\n"
    
    prompt += "\nResponde SOLO con el bloque TOON. Sin explicaciones adicionales."
    
    return prompt


# Diccionario de prompts por tipo
PROMPTS_TOON = {
    "nomina": PROMPT_TOON_NOMINA,
    "nomina_segunda": PROMPT_TOON_NOMINA_SEGUNDA,
    "estado_cuenta": PROMPT_TOON_ESTADO,
    "comprobante": PROMPT_TOON_COMPROBANTE
}
