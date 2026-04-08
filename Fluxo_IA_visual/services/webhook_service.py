import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class WebhookService:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    async def notificar(self, webhook_url: Optional[str], payload: Dict[str, Any]) -> None:
        """
        Envía el resultado de forma asíncrona al cliente.
        Falla de forma silenciosa para no tumbar el hilo principal,
        ya que Laravel tiene la opción de consultar por Polling si esto falla.
        """
        if not webhook_url:
            return

        async with httpx.AsyncClient() as client:
            try:
                # Disparamos el POST a Laravel
                response = await client.post(
                    webhook_url, 
                    json=payload, 
                    timeout=self.timeout
                )
                response.raise_for_status()
                logger.info(f"Webhook enviado con éxito a {webhook_url} para job_id: {payload.get('job_id')}")
            
            except httpx.HTTPStatusError as exc:
                logger.error(f"Error HTTP en Webhook ({exc.response.status_code}) para {webhook_url}.")
            except Exception as exc:
                logger.error(f"Falla de conexión al enviar Webhook a {webhook_url}: {str(exc)}")