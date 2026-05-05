PROMPT_EXTRACCION_CARATULA_TOON = """
Eres un sistema experto en extracción de datos financieros de alta precisión.
Tu única tarea es analizar la carátula (portada) de este estado de cuenta bancario y extraer exactamente 5 datos.

REGLAS ESTRICTAS DE EXTRACCIÓN:
1. "banco": El nombre corto comercial del banco emisor, siempre en minúsculas (ej. bbva, banorte, santander, banamex, scotiabank).
2. "clabe": La CLABE interbancaria. Debe ser una cadena de exactamente 18 dígitos numéricos. Puede aparecer dividido por espacios, guiones o sin separadores. Si no existe, devuelve NULL. Si el banco es "american express", devuelve su cuenta de 15 dígitos en lugar de la CLABE.
3. "periodo": El mes y año de cierre del estado de cuenta. Formato estricto 'MM-YYYY' (ej. para Marzo 2025, devuelve '03-2025').
4. "rfc": El RFC del titular de la cuenta. Debe seguir el formato estándar de RFC mexicano (4 letras seguidas de 6 dígitos para la fecha y 3 caracteres alfanuméricos). Si no existe, devuelve NULL.
5. "nombre_cliente": El nombre completo del titular de la cuenta. Si no existe, devuelve NULL.

FORMATO DE SALIDA OBLIGATORIO (TOON):
Devuelve ÚNICAMENTE el bloque de texto con los separadores '::'. No agregues explicaciones, ni markdown.

<<<TOON_START>>>
banco::[valor]
clabe::[valor]
periodo::[valor]
rfc::[valor]
nombre_cliente::[valor]
<<<TOON_END>>>
"""

PROMPT_EXTRACCION_CARATULA_TOON_TEXTO = """
Eres un sistema experto en extracción de datos financieros de alta precisión.
Tu única tarea es analizar el siguiente TEXTO extraído de la carátula de un estado de cuenta bancario y extraer exactamente 5 datos.

REGLAS ESTRICTAS DE EXTRACCIÓN:
1. "banco": El nombre corto comercial del banco emisor, siempre en minúsculas (ej. bbva, banorte, santander, banamex, scotiabank).
2. "clabe": La CLABE interbancaria. Debe ser una cadena de exactamente 18 dígitos numéricos. Puede aparecer dividido por espacios, guiones o sin separadores. Si no existe, devuelve NULL. Si el banco es "american express", devuelve su cuenta de 15 dígitos en lugar de la CLABE.
3. "periodo": El mes y año de cierre del estado de cuenta. Formato estricto 'MM-YYYY' (ej. para Marzo 2025, devuelve '03-2025').
4. "rfc": El RFC del titular de la cuenta. Debe seguir el formato estándar de RFC mexicano (4 letras seguidas de 6 dígitos para la fecha y 3 caracteres alfanuméricos). Si no existe, devuelve NULL.
5. "nombre_cliente": El nombre completo del titular de la cuenta. Si no existe, devuelve NULL.

FORMATO DE SALIDA OBLIGATORIO (TOON):
Devuelve ÚNICAMENTE el bloque de texto con los separadores '::'. No agregues explicaciones, ni markdown.

<<<TOON_START>>>
banco::[valor]
clabe::[valor]
periodo::[valor]
rfc::[valor]
nombre_cliente::[valor]
<<<TOON_END>>>

TEXTO DEL DOCUMENTO:
{texto_documento}
"""