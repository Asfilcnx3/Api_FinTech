import uvicorn
from fastapi import FastAPI, Request
import json
import logging

# Desactivamos los logs de acceso por defecto para ver más limpio nuestro print
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

app = FastAPI()

@app.post("/webhook-receptor")
async def recibir_webhook(request: Request):
    """
    Este endpoint simula ser tu servidor de Laravel.
    Recibe el POST, extrae el JSON y lo imprime bonito en la consola.
    """
    try:
        payload = await request.json()
        
        print("\n" + "="*60)
        print("🔔 ¡WEBHOOK RECIBIDO EXITOSAMENTE! 🔔")
        print("="*60)
        print(f"Job ID: {payload.get('job_id', 'NO_ID')}")
        print("Estado:", payload.get("estatus", "NO_STATUS"))
        print("\nPayload Completo:")
        print(json.dumps(payload, indent=4, ensure_ascii=False))
        print("="*60 + "\n")
        
        # Le respondemos a tu FastAPI principal que todo salió bien (HTTP 200)
        return {"mensaje": "Recibido fuerte y claro"}
        
    except Exception as e:
        print(f"❌ Error al parsear el webhook: {e}")
        return {"error": "Bad Request"}

if __name__ == "__main__":
    print("🚀 Iniciando simulador de Laravel (Webhook Receiver) en el puerto 8001...")
    uvicorn.run(app, host="0.0.0.0", port=8001)