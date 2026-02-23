import re

CONFIGURACION_CSF = {
    "persona_fisica": {
        "identificacion_contribuyente": {
            "rfc_pattern": [r"rfc:\s+([a-z0-9]{12,13})"],
            "curp_pattern": [r"curp:\s+([a-z0-9]{18})"],
            "nombre_pattern": [r"nombre \(s\):\s+([^\n]+)\n"],
            "primer_apellido_pattern": [r"primer apellido:\s+([a-z\s]+)\n"],
            "segundo_apellido_pattern": [r"segundo apellido:\s+([a-z\s]+)\n"],
            "inicio_operaciones_pattern": [r"fecha inicio de operaciones:\s+([0-9]{1,2}\s+de\s+[a-z]+\s+de\s+[0-9]{4})"],
            "estatus_padron_pattern": [r"estatus en el padrón:\s+([a-z]+)"],
            "cambio_estado_pattern": [r"fecha de último cambio de estado:\s+([0-9]{1,2}\s+de\s+[a-z]+\s+de\s+[0-9]{4})"],
            "nombre_comercial_pattern": [r"nombre comercial:\s*(.*?)(?=\s*datos|\n|$)"]
        },
        "domicilio_registrado": {
            "codigo_postal_pattern": [r"c[oó]digo postal:\s*(\d{5})"],
            "nombre_vialidad_pattern": [r"nombre de vialidad:\s+([a-z\s]+)n[uú]mero"],
            "numero_interior_pattern": [r"n[uú]mero interior:\s+([a-z\s]+)nombre"],
            "nombre_localidad_pattern": [r"nombre de la localidad:\s+([a-z\s]+)nombre"],
            "entidad_federativa_pattern": [r"nombre de la entidad federativa:\s+([a-z\s]+)entre"],
            "vialidad_pattern": [r"tipo de vialidad:\s*([^\n]+)"],
            "numero_exterior_pattern": [r"n[uú]mero exterior:\s*([^\n]+)"],
            "colonia_pattern": [r"nombre de la colonia:\s*([^\n]+)"],
            "municipio_pattern": [r"nombre del municipio o demarcaci[oó]n territorial:\s*([^\n]+)"],
            "calle_pattern": [r"entre calle:\s*([^\n]+)"]
        },
        "actividades_economicas": { # Ajustado para capturar múltiples actividades
            # parte 1: orden 
            # parte 2: actividad
            # parte 3: porcentaje
            # parte 4: fecha inicio
            # parte 5: fecha fin (opcional)
            "actividad_pattern": [r"^\s*(\d+)\s+(.+?)\s+(\d{1,3})\s+(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}/\d{2}/\d{4}))?"]
        },
        "regimenes": { # Ajustado para capturar múltiples regímenes
            # parte 1: régimen
            # parte 2: fecha inicio
            # parte 3: fecha fin (opcional)
            "regimen_pattern": [r"^\s*(r[eé]gimen[^\n]+?)\s+(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}/\d{2}/\d{4}))?"]
        }
    },
    "persona_moral": {
        "identificacion_contribuyente": {
            "rfc_pattern": [r"rfc:\s+([a-z0-9]{12,13})"],
            "razon_social_pattern": [r"raz[oó]n social:\s+([^\n]+)"],
            "regimen_capital_pattern": [r"r[eé]gimen capital:\s+([a-z\s]+)\n"],
            "nombre_comercial_pattern": [r"nombre comercial:\s*(.*?)(?=\s*fecha|\n|$)"],
            "inicio_operaciones_pattern": [r"fecha inicio de operaciones:\s+([0-9]{1,2}\s+de\s+[a-z]+\s+de\s+[0-9]{4})"],
            "estatus_padron_pattern": [r"estatus en el padrón:\s+([a-z]+)"],
            "cambio_estado_pattern": [r"fecha de último cambio de estado:\s+([0-9]{1,2}\s+de\s+[a-z]+\s+de\s+[0-9]{4})"]
        },
        "domicilio_registrado": {
            "codigo_postal_pattern": [r"c[oó]digo postal:\s*(\d{5})"],
            "nombre_vialidad_pattern": [r"nombre de vialidad:\s+([a-z\s]+)n[uú]mero"],
            "numero_interior_pattern": [r"n[uú]mero interior:\s+([a-z\s]+)nombre"],
            "nombre_localidad_pattern": [r"nombre de la localidad:\s+([a-z\s]+)nombre"],
            "entidad_federativa_pattern": [r"nombre de la entidad federativa:\s+([a-z\s]+)entre"],
            "vialidad_pattern": [r"tipo de vialidad:\s*([^\n]+)"],
            "numero_exterior_pattern": [r"n[uú]mero exterior:\s*([^\n]+)"],
            "colonia_pattern": [r"nombre de la colonia:\s*([^\n]+)"],
            "municipio_pattern": [r"nombre del municipio o demarcaci[oó]n territorial:\s*([^\n]+)"],
            "calle_pattern": [r"entre calle:\s*([^\n]+)"]
        },
        "actividades_economicas": { # Ajustado para capturar múltiples actividades
            # parte 1: orden 
            # parte 2: actividad
            # parte 3: porcentaje
            # parte 4: fecha inicio
            # parte 5: fecha fin (opcional)
            # parte 6: demás lineas de la actividad (opcional si no inicia con número)
            "actividad_pattern": [r"^\s*(\d+)\s+(.+?)\s+(\d{1,3})\s+(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}/\d{2}/\d{4}))?((?:\n(?!\s*\d).+)*)"]
        },
        "regimenes": { # Ajustado para capturar múltiples regímenes
            # parte 1: régimen
            # parte 2: fecha inicio
            # parte 3: fecha fin (opcional)
            "regimen_pattern": [r"(r[eé]gimen.+?)\s+(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}/\d{2}/\d{4}))?"]
        }
    }
}

PATRONES_CONSTANCIAS_COMPILADO = {}

# Primer iteración para el tipo de persona
for tipo_persona, datos in CONFIGURACION_CSF.items():
    PATRONES_CONSTANCIAS_COMPILADO[tipo_persona] = {} # Inicializa el diccionario para el tipo de persona

    # Segunda para el tipo de persona    
    for seccion_nombre, config in datos.items():
        PATRONES_CONSTANCIAS_COMPILADO[tipo_persona][seccion_nombre] = {} # Inicializa el diccionario para el patrón
    
        # Itera dinámicamente sobre todas las claves de patrones (rfc_pattern, regimen_pattern, etc.)
        for key, pattern_list in config.items():
            if key.endswith("_pattern"):
                flags = re.IGNORECASE
                if seccion_nombre in ["actividades_economicas", "regimenes"]:
                    flags |= re.MULTILINE
                
                # UNIMOS LA LISTA ED PATRONES EN UNA SOLA REGEX "|" y lo envolvimos en (?:...)
                patron_combinado = "|".join(f"(?:{p})" for p in pattern_list)

                # Guardamos el patrón compilado con un nombre de clave limpio (sin '_pattern')
                nombre_clave = key.replace("_pattern", "")
                PATRONES_CONSTANCIAS_COMPILADO[tipo_persona][seccion_nombre][nombre_clave] = re.compile(patron_combinado, flags)