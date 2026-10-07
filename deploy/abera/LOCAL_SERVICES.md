# Abera Dograh sin MPS

La aplicación usa sus servicios locales y los proveedores configurados por cada
organización. `ENABLE_DOGRAH_MPS=false` es el valor predeterminado. El modo
`DEPLOYMENT_MODE=abera` y las plantillas de despliegue lo mantienen apagado.
La integración antigua permanece aislada para facilitar futuras actualizaciones
del fork, sin ejecutarse en Abera.

## Funciones conservadas

| Función | Implementación |
| --- | --- |
| PDF, PDF escaneado, Word, TXT, Markdown y JSON | Lector local en ARQ; PDF con pypdf, OCR con Poppler y Tesseract, DOCX con python-docx, DOC con antiword |
| Documento completo | Texto en PostgreSQL; no requiere embeddings |
| Búsqueda por fragmentos | Fragmentos locales, embeddings del proveedor del cliente e índice pgvector existente |
| Consulta durante la conversación | La herramienta existente conserva el filtro de organización y los documentos asociados al nodo |
| Catálogo de voces | Consulta directa a ElevenLabs, Cartesia, Deepgram, Rime; catálogo local de Sarvam e ingreso manual de IDs |
| Transcripción de archivos | OpenAI, Deepgram o ElevenLabs configurado por la cuenta; admite la clave de OpenAI Realtime como alternativa |
| Crear un agente con IA | LLM configurado por la organización; valida el grafo y guarda un borrador editable |
| Telefonía | Los proveedores configurados por el cliente; deja de aprovisionar Cloudonix automáticamente mediante MPS |
| API keys y usuarios | Autenticación, claves e identidad locales conservadas |
| Historial y métricas de llamadas | Persistencia y consultas locales conservadas |
| Audios pregrabados y sonido de fondo | Cargas por el mecanismo de Abera con tamaño autorizado y cuota de almacenamiento |

La transcripción de un archivo es una operación distinta de la conversación
Realtime. Cuando usa una clave de OpenAI Realtime, llama a
`gpt-4o-mini-transcribe` para el archivo. No modifica el modelo de conversación
`gpt-realtime-2.1-mini` ni su voz. OpenAI, Deepgram y ElevenLabs pueden cobrar
estas operaciones según las condiciones de la cuenta del cliente.

## Configuración y actualización

1. Construir la API con `docker build -f api/Dockerfile -t abera/dograh-api:local-services .`
   El Dockerfile incluye lectores y datos de OCR para español e inglés. El
   tokenizador se descarga durante la construcción y queda cacheado en la imagen.
2. Construir la UI con `docker build -f ui/Dockerfile -t abera/dograh-ui:local-services .`.
3. Usar ambas imágenes en el despliegue y mantener `ENABLE_DOGRAH_MPS=false`.
4. En **Modelos**, configurar los proveedores y API keys de la organización.
   Configurar embeddings para búsqueda por fragmentos. Los documentos completos
   no requieren una clave adicional.

Para actualizar la instalación local que ya está corriendo en Windows, después
de construir las dos imágenes:

```powershell
./deploy/abera/activate-local.ps1
```

El script reutiliza los archivos de Compose, la configuración efectiva y el
almacenamiento de los contenedores actuales, aunque provengan de otro worktree.
Actualiza API y UI, mantiene MPS y telemetría apagados y deja el idioma
predeterminado en español LATAM. Los parámetros sensibles se pasan mediante un
archivo temporal que se elimina al terminar; no se imprimen ni se guardan en Git.

### Dependencias de la interfaz

La UI usa Next.js 15.5.27, que incluye los parches de ejecución remota de código
publicados en agosto de 2026. El lockfile también actualiza los lectores de
imágenes y las dependencias auxiliares compatibles. El override de PostCSS
mantiene una versión corregida de la misma versión principal, porque Next.js 15
todavía declara una versión anterior. Conservarlo al integrar upstream hasta que
su dependencia incluya esos parches; validar con `npm ci`, la compilación y
`npm audit --omit=dev` después de modificar estas resoluciones.

### Proveedor de embeddings por URL

En **Modelos → Embedding**, seleccionar **Compatible con OpenAI** y completar:

- **URL del proveedor:** URL base de la API con su ruta de versión, por ejemplo
  `https://proveedor.example/v1`. La aplicación agrega `/embeddings`.
- **Modelo de búsqueda:** identificador del modelo indicado por el proveedor.
- **API key:** credencial de esa cuenta. Se envía en el encabezado de autorización,
  nunca como parte de la URL.

Al cambiar la URL se debe volver a ingresar la API key. Esto evita enviar una
credencial guardada y oculta a un destino diferente.

El proveedor debe aceptar el formato de embeddings compatible con OpenAI y
devolver vectores de 1536 dimensiones, que es el tamaño del índice actual.
Al guardar se comprueba el modelo con un texto corto; el proveedor puede cobrar
esa solicitud. Un modelo con otro tamaño se rechaza antes de indexar documentos.
Las consultas y la carga usan la misma URL y el mismo modelo de la organización.
Si se cambia de modelo o proveedor, volver a procesar los documentos por fragmentos
para generar el índice correspondiente. Las URLs internas se permiten en OSS;
en Abera se aplica la protección existente contra acceso a redes privadas.

Los usuarios, agentes, documentos, grabaciones y credenciales existentes no se
borran ni se convierten automáticamente. Las configuraciones antiguas cuyo
proveedor era `dograh` necesitan proveedores propios antes de iniciar otra
llamada. La UI lo informa y no reemplaza secretos de forma silenciosa.

## Límites y seguridad

- Archivos de conocimiento: 5 MiB; PDF hasta 200 páginas y dos millones de
  caracteres extraídos; Word comprimido hasta 32 MiB y 2.000 entradas.
- El lector corre como subproceso sin heredar credenciales de AWS, base de datos
  o proveedores. Tiene 512 MiB de espacio de direcciones, 60 segundos de CPU y
  180 segundos de tiempo total. Tesseract y el tokenizador usan un hilo.
- Redis limita a un lector por runtime y libera su turno al finalizar o vencer
  la reserva. Los demás trabajos vuelven a la cola, con reintentos limitados.
- El API y el trabajador validan organización, documento y ruta S3 antes de
  descargar o escribir. Los índices anteriores se mantienen si falla la nueva
  indexación.
- Los catálogos reciben claves nuevas por POST, sin ponerlas en URLs. Las claves
  guardadas se resuelven por organización y proveedor.
- Transcripción: archivo de hasta 25 MiB y duración de hasta una hora, copiado en
  bloques a un archivo temporal y eliminado al terminar.
- El nuevo lector conserva formatos, búsqueda y OCR de PDF, pero su extracción
  difiere de Docling en tablas complejas y diseño de página. Validar documentos
  representativos del cliente; no asumir resultados idénticos al procesador anterior.

## Facturación

Basic usa proveedores propios y no requiere créditos de Dograh. Las compras de
MPS y sus service keys quedan deshabilitadas. La facturación comercial de Abera
pertenece a `abera-payments`; no se reemplaza por un contador local.

Pro administrado conserva el bloqueo de admisión mientras no esté conectado su
control de minutos de Abera. Apagar MPS no permite saltarse esa comprobación.
Esta sustitución de servicios auxiliares no completa por sí sola los backups,
el ciclo de vida de Automations ni la integración comercial de Pro.

## Validación sin gasto de IA

Los tests de lectores ejecutan OCR y extracción reales. Las respuestas de los
proveedores se simulan; el contenedor se ejecuta sin acceso a la red. Los tests
de la integración heredada necesitan la fixture explícita `mps_enabled`; el
resto usa MPS apagado. Usar siempre `api/.env.test` y una base de pruebas.
