# Actualización selectiva de Dograh — octubre de 2026

Rama: `codex/upstream-selectivo-2026-10`, basada en `codex/privacy-defaults` (`fba406e81934ed7ef7e6564803b01e9f7fa96a14`). Se conserva el archivo local `docker-compose.override.yaml` fuera de los commits.

La referencia original revisada es [dograh-hq/dograh, 417c9a74](https://github.com/dograh-hq/dograh/commit/417c9a74156f518de814cc55b579eb96a9656d5a). Se seleccionaron cambios funcionales posteriores a la referencia que ya incorporaba el fork (`75a299e2`). Los commits de integración conservan las referencias originales. El despliegue y la activación de WhatsApp quedan para después de revisar el PR.

## Cambios incorporados

| Área | Resultado | Referencias originales |
| --- | --- | --- |
| Estabilidad | Finalización de herramientas al colgar, cancelación de respaldos y diagnóstico de errores de telefonía y transcripción | [#857](https://github.com/dograh-hq/dograh/pull/857), [#878](https://github.com/dograh-hq/dograh/pull/878), [#893](https://github.com/dograh-hq/dograh/pull/893), [#896](https://github.com/dograh-hq/dograh/pull/896) |
| Campañas | Pausa ante errores del proveedor, coordinación de reintentos y deduplicación de resultados | [#882](https://github.com/dograh-hq/dograh/pull/882) |
| Modelos | Conexiones por proveedor, configuraciones con nombre, respaldos de LLM y controles de temperatura y velocidad compatibles con el modelo | [#853](https://github.com/dograh-hq/dograh/pull/853), [#858](https://github.com/dograh-hq/dograh/pull/858), [#866](https://github.com/dograh-hq/dograh/pull/866), [#869](https://github.com/dograh-hq/dograh/pull/869), [#875](https://github.com/dograh-hq/dograh/pull/875) |
| Chat | Respuestas por SSE, recuperación de turnos aceptados tras desconexión y persistencia durante el cierre del API | [#870](https://github.com/dograh-hq/dograh/pull/870) |
| Editor y herramientas | Nombres y notas de versiones, vistas de configuración y mensajes durante operaciones | [#862](https://github.com/dograh-hq/dograh/pull/862), [#871](https://github.com/dograh-hq/dograh/pull/871), [#890](https://github.com/dograh-hq/dograh/pull/890) |
| Voz y evaluación | Catálogos directos de voces, MiniMax por WebSocket y Gemini en evaluación | [#848](https://github.com/dograh-hq/dograh/pull/848), [#880](https://github.com/dograh-hq/dograh/pull/880), [#883](https://github.com/dograh-hq/dograh/pull/883) |
| WhatsApp | Llamadas entrantes, sincronización de números de Meta y asignación de agentes por número | [#732](https://github.com/dograh-hq/dograh/pull/732), [#901](https://github.com/dograh-hq/dograh/pull/901), [#892](https://github.com/dograh-hq/dograh/pull/892) |

Se excluyeron los cambios de MinIO, correcciones exclusivas de MPS, banners promocionales, incrementos de versión y reorganizaciones visuales ajenas a estas funciones. El orden de imports de algunos archivos existentes se corrigió porque impedía compilar la base.

## Adaptaciones de Abera

- Se conservan S3, los proveedores locales, las cuotas de Abera, la compresión del historial, WebRTC de audio y las preferencias de privacidad. Las pruebas heredadas que necesitan MPS lo habilitan explícitamente; las comprobaciones de Abera mantienen su prohibición, incluso si se activa accidentalmente la bandera de MPS.
- Panel, API y SDK utilizan `/api/v1/model-connections`. Las rutas V2 reemplazadas se retiran y OpenAPI y los clientes se regeneran juntos.
- La migración conserva proveedores, claves individuales y grupos de claves, modelos, voces, parámetros y URLs de embeddings. Incluye agentes archivados y todas las versiones históricas. También migra las configuraciones completas de agentes cuya organización carecía de una predeterminada.
- Una configuración incompleta que no puede convertirse detiene el backfill antes de escribir conexiones o vínculos. El error identifica filas y motivos sin incluir secretos ni textos del cliente. Las revisiones anteriores de Alembic pueden haberse aplicado: cada revisión tiene su propia transacción.
- Cambiar la URL de un proveedor de embeddings exige ingresar una clave nueva explícitamente. Se comprueban los modelos afectados y la dimensión de los vectores al guardar. Las llamadas no repiten esas comprobaciones externas y la actualización no reindexa documentos automáticamente.
- El catálogo reutiliza esquemas estáticos. La caché incluye las clases registradas y la política de proveedores; no contiene configuraciones, claves ni datos de organizaciones.
- WhatsApp verifica HMAC antes de ejecutar acciones, exige Redis para arbitrar eventos repetidos, valida el identificador externo del número contra la configuración autenticada y comprueba cuotas y concurrencia. La paginación de Meta no puede reenviar credenciales a otro destino y los errores no devuelven cuerpos del proveedor.
- El proxy de Abera transmite SSE sin almacenamiento intermedio. El API dispone de 60 segundos de cierre en Compose y permite terminar o persistir los turnos de chat aceptados.
- La interfaz, ayudas, mensajes de error y accesibilidad nuevos se adaptan mediante `es-419`. Los nombres, instrucciones, notas, identificadores y mensajes aportados por clientes se conservan. La guía de WhatsApp está en español.

Pipecat avanza únicamente de `291fa01acdab91c8dd20209f8a041ea7b3a95824` a `93f62ca909fcbf6713e3ff99b26f33d4bb7b157e`, la revisión requerida por estos cambios. Se revisaron los contratos de llamadas diferidas, respaldos, MiniMax, ElevenLabs y los adaptadores propios. El submódulo permanece limpio, sin actualizarlo a una etiqueta posterior.

## Validación

Se utilizan Python **3.13.15**, PostgreSQL **17 con pgvector**, Redis **7** y `api/.env.test`, con bases desechables. Las pruebas de API no usan la base de desarrollo ni almacenamiento real. La compilación del panel usa Node **22.23.3** y Next.js **15.5.27** en Linux; las comprobaciones locales del panel y del SDK TypeScript usan Node **24.4.1**.

| Comprobación | Base `fba406e8` | Resultado actualizado |
| --- | --- | --- |
| API | 3.147 correctas, 1 omitida; detenida al registrar 20 fallos | 4.986 casos verificados, 2 omitidos y 17 subpruebas; pasada completa y repetición selectiva |
| Panel | 225 correctas | 426 correctas |
| TypeScript del panel | Correcto | Correcto |
| SDK TypeScript | Sin medición inicial independiente | 21 correctas y compilación correcta |
| Auditoría de traducción | 2.578 mensajes, 89 excepciones revisadas | 2.984 mensajes, 127 excepciones revisadas; 4 pruebas de auditoría correctas |
| Metadatos de la API en español | Correcto | Correcto |
| Compilación de producción del panel | Compila, pero falla ESLint por imports desordenados | Correcta: TypeScript, ESLint y generación de 33 páginas |
| Migración y restauración | Esquema anterior como punto de partida | Correctas sobre datos ficticios; huella lógica idéntica al restaurar |

Los fallos iniciales incluían pruebas de MPS que no habilitaban su integración, una expectativa antigua de envío de correo a telemetría, deriva del SDK y falta de TypeScript en el ayudante MCP de la imagen de pruebas. Se conservaron los controles de privacidad y se corrigieron las expectativas y la preparación del entorno. Los casos temporales que fallaron durante la ejecución concurrente con la compilación pasaron al repetirlos aisladamente.

La pasada completa del código final produjo 4.929 casos correctos; quedaron 3 expectativas de facturación heredada y 54 errores de preparación causados por una referencia obsoleta al cliente MPS en las pruebas nuevas de voces. Después de corregir únicamente esos archivos de pruebas, se repitieron los tres módulos afectados: **78 casos correctos**. El código de producción de API y Pipecat no cambió entre ambas ejecuciones. La cobertura agregada corresponde a los 4.986 casos actuales, sin sumar dos veces los repetidos.

Los dos casos omitidos son el adaptador opcional de Anthropic, ausente en la imagen de pruebas, y una prueba negativa de Speechify que no aplica porque esta revisión ya incluye ese módulo. Los 10 casos de localización se repitieron después de completar los últimos mensajes y pasaron.

La cobertura incluye migración atómica e idempotente, configuraciones históricas y archivadas, aislamiento entre organizaciones, protección de credenciales, embeddings por URL, cuotas, documentos, grabaciones y compresión del historial; además, chat progresivo y recuperación, herramientas al colgar, campañas, firmas inválidas y números ajenos en WhatsApp. La deduplicación se comprueba con 16 entregas concurrentes contra Redis real y los proveedores externos se simulan.

Se conserva una advertencia anterior de React sobre la dependencia `fetchPreferences` en `OrganizationPreferencesSection.tsx`; no bloquea la compilación. No se desactivan comprobaciones de TypeScript, ESLint ni hooks.

## Medición reproducible del catálogo

Se hicieron tres repeticiones por revisión, cada una con 20 consultas de calentamiento y 200 solicitudes ASGI con concurrencia 8, en la misma imagen y sin llamadas a proveedores. La base consulta `/api/v1/user/configurations/defaults` y la versión nueva `/api/v1/model-connections/catalog`: son los contratos que cada panel usa para obtener los metadatos de modelos.

| Mediana de las repeticiones | Base | Actualizado |
| --- | ---: | ---: |
| Latencia mediana de solicitud | 55,90 ms | 24,05 ms |
| p95 de solicitud | 99,40 ms | 44,15 ms |
| CPU para 200 solicitudes | 12,178 s | 0,787 s |
| Solicitudes por segundo | 16,42 | 258,28 |
| Memoria pico del proceso | 316,94 MiB | 329,54 MiB |
| Tamaño de respuesta | 66.835 bytes | 72.276 bytes |

El p95 baja aproximadamente un 56 % y la CPU un 94 % en este ensayo; la memoria pico aumenta un 4 %. La respuesta nueva contiene más metadatos. Estas cifras no miden latencia de voz, ancho de banda ni capacidad de producción. Las muestras y las condiciones se conservan en [validation/upstream-2026-10.json](validation/upstream-2026-10.json).

Para repetir la medición en cada checkout Linux, carga exclusivamente el entorno de pruebas, deshabilita S3, MPS y telemetría, y ejecuta el mismo [script](../../scripts/benchmark_model_catalog.py) con `--requests 200 --concurrency 8`. El script admite la API anterior y la nueva y no inicia el ciclo de vida de servicios externos.

## Migraciones y restauración

Las revisiones nuevas son `91a84e0a1947` (metadatos de versiones), `4c8d92e6f503` (catálogo y snapshots), `a7128e93bc40` (simplificación de conexiones), `b3c1d9e4f7a2` (backfill) y `c82d4f6a9b10` (mensajes de herramientas).

El ensayo ejecutó las migraciones de la base, creó datos ficticios con grupos de claves, temperatura implícita, embeddings por URL, herramientas y versiones archivadas, guardó un `pg_dump` en formato personalizado, actualizó a `head` y comprobó los valores efectivos. Después restauró la copia anterior en otra base y comparó los datos y la revisión de Alembic. Las huellas coinciden: `105716c06eb453c06ecc28db9128cab92af745294871b27e2c2e67c98e667dda`.

Antes de un despliegue aprobado:

1. Detén la admisión de llamadas y los trabajadores que escriben, deja terminar las ejecuciones y guarda una copia completa de PostgreSQL, de la configuración del despliegue y de las referencias a objetos S3. Protege las copias que contienen claves.
2. Ensaya la actualización sobre una copia de esa base. Si el preflight identifica filas incompletas, corrígelas y repite; no sustituyas sus modelos por valores predeterminados.
3. Despliega panel, API y SDK compatibles en conjunto y ejecuta Alembic hasta `head`. Verifica las cuotas, el catálogo, el chat, la lectura de documentos y las grabaciones antes de reabrir la admisión.
4. Si hace falta restaurar, detén todas las escrituras de la versión nueva y conserva por separado la actividad posterior a la copia. Restaura la copia completa en una base limpia y vuelve al conjunto de servicios del commit inicial. Comprueba la revisión, las configuraciones y los objetos S3 antes de reabrir tráfico.

No uses un downgrade como sustituto de la copia completa: el esquema anterior no puede representar variantes y mensajes diferidos de herramientas, notas nuevas ni ediciones posteriores del catálogo. La migración rechaza los downgrades de mensajes que perderían información.

## Comprobaciones que requieren credenciales reales

Quedan para un entorno autorizado tras revisar el PR: llamadas y calidad de audio con proveedores reales, MiniMax WebSocket y voces en vivo, evaluación con Gemini, embeddings contra el destino real, subida y lectura de grabaciones con S3 y llamadas reales de WhatsApp a través de Meta. También debe comprobarse el acceso HTTPS, la configuración de TURN y la disponibilidad de llamadas en la cuenta y los números de Meta.

No se ha desplegado esta rama fuera del entorno local, habilitado llamadas en Meta ni iniciado llamadas de pago.

## Arranque de la instalación local existente

El 16 de octubre se construyeron las imágenes de producción con los Dockerfile de esta rama y se actualizaron API y panel en el proyecto local `abera-dograh`. Se reutilizaron sus contenedores y volúmenes de PostgreSQL, Redis y almacenamiento S3 compatible; los demás proyectos de Docker continuaron funcionando. El panel está en `http://localhost:3010` y la API en `http://localhost:8000`.

La instalación limpia del panel detectó una entrada faltante en `package-lock.json`: la dependencia opcional `@swc/helpers@0.5.23` de `next-intl`. Se regeneró esa entrada con el mismo Node 22 y npm del Dockerfile, sin actualizar los demás paquetes. Después pasaron `npm ci`, la compilación, TypeScript, ESLint y la generación de las 33 páginas.

Antes de migrar se guardó un `pg_dump` completo de la base local. Se restauró en otra base, se ensayaron las migraciones y se comprobó la imagen nueva de API con Python 3.13.15. La instalación quedó en `c82d4f6a9b10`, conservando sus dos agentes y cinco versiones. La comparación con la imagen anterior verificó siete registros y 77 campos efectivos, incluidas las claves, modelos y parámetros, además de las huellas del contenido del cliente. Coinciden al normalizar las listas de una sola clave y excluir los metadatos de validación del contrato anterior.

API, panel, PostgreSQL, Redis y almacenamiento quedaron saludables. Pasaron 18 comprobaciones HTTP de API directa y proxy del panel: autenticación, agentes, catálogo, conexiones sin secretos, configuraciones V3, configuración predeterminada y locale de acceso. También pasó la lectura autenticada del bucket local. En el navegador se comprobaron los agentes, proveedores y editor de modelos en español con la sesión existente, sin guardar cambios de configuración.

Este arranque local no valida llamadas ni conexiones con proveedores reales. Se mantienen pendientes las comprobaciones externas enumeradas arriba. Los respaldos, secretos y registros locales permanecen fuera de Git.

## Corrección de la carga de documentos en el navegador

La prueba de carga completa detectó que los enlaces firmados usaban el host interno de Docker y que el bucket local no tenía reglas CORS. Se agregó `S3_PUBLIC_ENDPOINT_URL`, opcional, para firmar los enlaces GET/PUT directamente con el host accesible por el navegador. Las operaciones de la API mantienen `S3_ENDPOINT_URL` y los consumidores que solicitan enlaces internos conservan ese destino. No se reescriben enlaces después de firmarlos. Al omitir la nueva variable se conserva el comportamiento anterior.

En esta instalación se usa `S3_PUBLIC_ENDPOINT_URL=http://localhost:9000`, mientras la API conserva su destino interno. El bucket permite GET, PUT y HEAD únicamente desde `http://localhost:3010` y `http://127.0.0.1:3010`, con los encabezados necesarios para estas cargas. Se guardó la configuración CORS anterior; la política de acceso a objetos no se modificó. Otros despliegues con almacenamiento compatible deben configurar sus propios orígenes, en lugar de reutilizar estos valores locales.

Al continuar el procesamiento apareció otra incompatibilidad: el contexto de `StreamingBody` devuelve la respuesta HTTP subyacente, cuyo método `read()` no acepta un tamaño. La descarga acotada ahora conserva el wrapper del SDK y lee a través de él. Se mantienen el cierre del contexto, la comprobación de longitud y el límite de 5 MB. La prueba de regresión usa el `StreamingBody` real: reproduce dos fallos antes de la corrección y pasa después.

Pasaron 57 pruebas de enlaces firmados, lecturas acotadas, cuotas, cargas administradas, parsing y recuperación local de documentos, usando Python 3.13, `api/.env.test` y PostgreSQL/Redis desechables. No se llamó a proveedores de embeddings ni se modificó la configuración de modelos.

La repetición desde el navegador terminó con `prueba-documento-completo.md` en estado **Completado**, modo documento completo y cero fragmentos. La lectura del contenido respondió HTTP 200 y la herramienta de conocimiento recuperó su texto para el agente sin embeddings. Se archivó únicamente el registro ficticio del intento fallido de reproducción; el documento correcto queda disponible como evidencia local.
