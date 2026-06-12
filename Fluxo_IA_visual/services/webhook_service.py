# services/webhook_service.py

import httpx
import logging
import ipaddress
import socket
from urllib.parse import urlparse
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class WebhookService:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def _es_url_segura(self, url: str) -> bool:
        """Valida que la URL no apunte a direcciones internas/locales (Prevención SSRF)."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ["http", "https"]:
                return False
            
            # Resolver el dominio a IP
            ip_str = socket.gethostbyname(parsed.hostname)
            ip = ipaddress.ip_address(ip_str)
            
            # Bloquear IPs locales, loopback, link-local (AWS IMDS) y privadas
            if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast:
                return False
            return True
        except Exception:
            return False

    async def notificar(self, webhook_url: Optional[str], payload: Dict[str, Any]) -> None:
        """
        Envía el resultado de forma asíncrona al cliente.
        Falla de forma silenciosa para no tumbar el hilo principal,
        ya que Laravel tiene la opción de consultar por Polling si esto falla.
        """
        if not webhook_url:
            return

        if not self._es_url_segura(webhook_url):
            logger.warning(f"Intento de SSRF bloqueado. URL sospechosa: {webhook_url}")
            return

        async with httpx.AsyncClient() as client:
            try:
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