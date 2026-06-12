# 🦇 Fluxo API - Motor de Análisis Financiero y Fiscal

Fluxo es un motor de procesamiento de alta concurrencia construido en **FastAPI**. Diseñado para extraer, reconciliar y clasificar transacciones bancarias, constancias de situación fiscal (CSF) y recibos de nómina (NomiFlash) a partir de documentos PDF o lotes masivos en ZIP.

Combina extracción espacial determinista con Modelos Multimodales (LLMs + OCR Vision) para lograr precisión absoluta en entornos financieros.

---

## 🏗️ Arquitectura del Sistema

El flujo de procesamiento está diseñado para operaciones de alto rendimiento y cero bloqueos (*non-blocking I/O*), dividiendo la carga de trabajo estratégicamente:

1. **Recepción y Sanitización:** Los archivos se reciben por chunks para prevenir saturación de memoria.
2. **Orquestación Asíncrona (`BackgroundTasks`):** FastAPI responde inmediatamente con un `job_id` (Código 202) mientras los *workers* operan en segundo plano.
3. **Procesamiento CPU-Bound (`ProcessPoolExecutor`):** Un pool global precargado en el estado de la aplicación maneja la carga pesada de extracción espacial y PDF parsing sin estrangular el *Event Loop*.
4. **Motor Híbrido de Clasificación:**
   - **Capa Determinista:** Regex y heurística basada en pesos para transacciones conocidas y limpieza de "basura OCR".
   - **Delegación Semántica (LLMs):** Envío dinámico por lotes a modelos de IA (GPT/Qwen) para clasificar ambigüedades.
5. **Capa de Abstracción de Datos (`StorageService`):** Totalmente desacoplada vía Inyección de Dependencias, preparada para escalar hacia buckets de almacenamiento en la nube.

---

## 🛡️ Seguridad en Profundidad (Security-First)

El sistema ha sido fortificado contra vectores de ataque comunes en el procesamiento de archivos y flujos automatizados:

* **Prevención de SSRF:** El `WebhookService` bloquea peticiones hacia direcciones IP locales, loopback o metadatos de instancias cloud.
* **Defensa Anti Zip-Bomb & Zip-Slip:** Auditoría previa de metadatos de compresión, límites estrictos de expansión y validación de rutas absolutas durante la extracción.
* **Inspección de Magic Bytes:** Bloqueo de *MIME-Type spoofing* (falsificación de extensiones) leyendo las cabeceras binarias reales del archivo.
* **Control OOM (Out-Of-Memory):** Streaming de I/O en la escritura a disco local temporal para archivos masivos.
* **Sanitización de Logs:** Enmascaramiento de información de identificación personal (PII) en tiempo real para cumplimiento normativo.

---

## 🚀 Endpoint Principal y Flujo de Vida

### `POST /api/v1/Fluxo/fluxo/procesar_pdf/`
Recibe uno o múltiples documentos. Delega el trabajo al orquestador general y retorna un pasaporte de seguimiento.

### `GET /api/v1/Fluxo/fluxo/descargar-resultado/{job_id}`
Sistema de *Polling* optimizado:
- **202 Accepted:** Retorna el objeto `PassportData` con métricas de progreso en tiempo real (Páginas procesadas, ETA dinámico).
- **200 OK:** Entrega el binario `.xlsx` o el `.json` final estructurado.

> **Nota:** La API también soporta notificaciones pasivas mediante *Webhooks*, enviando el payload directamente al *backend* del cliente al finalizar.

---

## 💻 Instalación y Desarrollo Local

### Prerrequisitos
* Python 3.10+
* Dependencias del sistema para procesamiento de imágenes (ej. `poppler-utils` para PyMuPDF).

### Levantamiento Rápido

1. **Clonar y preparar entorno:**
   ```bash
   git clone <tu-repo>
   cd fluxo-api
   python -m venv venv
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   ```

2. **Instalar dependencias:**

  ```Bash
    pip install -r requirements.txt
  ```

3. **Variables de Entorno:**

Crea un archivo .env en la raíz basado en el .env.example:

Fragmento de código

  ```Bash
    ENVIRONMENT="development"
    OPENAI_API_KEY_FLUXO="sk-..."
    OPENAI_API_KEY_NOMI="sk-..."
    OPENROUTER_API_KEY="sk-or-..."
  ```

4. **Ejecutar el servidor:**

  ```Bash
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
  ```

5. **Documentación Interactiva:**

Navega a http://localhost:8000/docs para ver el esquema OpenAPI autogenerado con los ejemplos de respuesta y validaciones en vivo.

## 🗺️ Roadmap Cloud (AWS)

Gracias al desacoplamiento estricto de servicios (file_manager.py, storage_service.py), la API está lista para evolucionar hacia una arquitectura Cloud Native:

[ ] Migración a AWS S3: Implementación de aioboto3 para reemplazar el almacenamiento temporal en disco, permitiendo la auto-escalabilidad horizontal (Stateless Containers).

[ ] Despliegue Serverless / Contenedores: Transición del procesamiento en ProcessPoolExecutor hacia servicios de colas y workers efímeros para cargas masivas.