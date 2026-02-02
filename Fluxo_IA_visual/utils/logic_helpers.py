from typing import List, Dict

def inyectar_tipo_por_geometria(
    transacciones_llm: List[Dict], 
    mapa_montos: List[Dict]
) -> List[Dict]:
    """
    Recibe la transcripción del LLM (donde el 'tipo' puede ser erróneo)
    y el mapa geométrico (donde el 'tipo' es preciso).
    Sobrescribe el tipo en las transacciones del LLM basándose en el monto.
    """
    # Creamos una copia del mapa para ir "consumiendo" los montos encontrados
    # Agrupamos por valor para búsqueda rápida: { 500.0: [item1, item2], ... }
    mapa_indexado = {}
    for item in mapa_montos:
        val = item["monto_float"]
        if val not in mapa_indexado:
            mapa_indexado[val] = []
        mapa_indexado[val].append(item)

    transacciones_finales = []

    for tx in transacciones_llm:
        try:
            monto_llm = float(str(tx.get("monto", "0")).replace(",", ""))
        except:
            # Si el LLM extrajo algo que no es número, lo dejamos pasar pero sin clasificar
            transacciones_finales.append(tx)
            continue

        # BUSCAMOS MATCH EN GEOMETRÍA
        candidatos = mapa_indexado.get(monto_llm, [])
        
        if candidatos:
            # Match encontrado!
            # Tomamos el primero de la lista (asumiendo orden cronológico/vertical similar)
            mejor_candidato = candidatos.pop(0) 
            
            # INYECCIÓN DE LA VERDAD GEOMÉTRICA
            tx["tipo"] = mejor_candidato["tipo"] # "cargo" o "abono"
            tx["_debug_geo"] = "match_exacto" # Flag para debug
        else:
            # No encontramos el monto en la geometría (quizás el LLM corrigió un OCR malo o alucinó)
            # Mantenemos lo que dijo el LLM por defecto o marcamos como 'indefinido'
            tx["tipo"] = "cargo" 
            tx["_debug_geo"] = "sin_match_fallback"
            pass 

        transacciones_finales.append(tx)

    return transacciones_finales