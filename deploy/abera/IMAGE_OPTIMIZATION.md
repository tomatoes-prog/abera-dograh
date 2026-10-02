# Imágenes Dograh: medición y validación

Medición local del 2 de octubre de 2026, Linux amd64. Tamaños de Docker sin
comprimir, en MB decimales. Estos tamaños representan disco y transferencia;
la memoria y la capacidad de llamadas requieren mediciones independientes.

| Imagen | Referencia | Optimizada | Reducción aproximada |
| --- | ---: | ---: | ---: |
| API | 1.598 MB | 1.161 MB | 27 % |
| UI | 327 MB | 262 MB | 20 % |
| Administración de Dograh | 1.688 MB | 632 MB | 63 % |
| Redis 7 | 113 MB | 39 MB | 65 % |

API y UI se comparan con las imágenes `:capacity` existentes. La referencia
administrativa se reconstruyó con los paquetes del Dockerfile anterior en una
sola etapa; la imagen optimizada usa la misma base Amazon Linux y pgvector.
Los cambios posteriores que incorporan el aviso de licencia pueden variar
ligeramente estos tamaños. Las imágenes activas de capacidad se conservan.

## Qué cambió

- API: FFmpeg para audio, construido desde fuente verificada con SHA256.
  Sus dos ejecutables pasan de aproximadamente 392 MiB a 7 MiB. Conserva
  WAV, MP3, OGG/Opus, FLAC y AAC, además de demultiplexado de audio MP4/WebM.
  Se valida codificación, lectura y conversión a PCM. Vídeo, dispositivos de
  captura y protocolos de red de FFmpeg están deshabilitados.
- API: Node se conserva para el validador TypeScript de workflows, con su
  binario reducido. El runtime no contiene npm, git, gcc, make ni uv.
- API: tests, utilidades de desarrollo y fixtures Pipecat viven únicamente en
  el target `test`. Licencias y datos necesarios para la aplicación se conservan.
- UI: salida standalone sobre Alpine, con Node y libstdc++; npm, Yarn, cachés
  de compilación y mapas de fuentes quedan fuera del runtime. Node es PID 1.
- Administración: pgvector se compila en otra etapa. El runtime conserva
  PostgreSQL 17, pgvector, AWS CLI y boto3 para respaldar y verificar restauraciones.
  gcc, git, make y los paquetes de desarrollo quedan en el constructor.
- Redis: misma versión mayor, variante Alpine. PostgreSQL local conserva la
  imagen pgvector; en el despliegue administrado PostgreSQL vive en RDS.
- MinIO: retirados el adaptador Python, el servicio Compose y los recursos Helm.
  Su contenedor/volumen local anterior debe mantenerse hasta migrar sus datos.

El devcontainer conserva herramientas de compilación porque sirve para editar
e instalar dependencias. Sus herramientas no se copian a las imágenes productivas.
Nginx ya usa Alpine; coturn, cloudflared y el init de Bash usan imágenes externas.
No se reconstruyeron estos componentes ni se cambiaron sus implementaciones.

## Por qué la API sigue ocupando aproximadamente 1,16 GB

El entorno Python ocupa unos 874 MiB. Los mayores componentes medidos son:

| Componente | MiB aproximados | Uso |
| --- | ---: | --- |
| LLVM/llvmlite | 171 | Dependencia de Numba para cálculos numéricos del audio |
| OpenCV y bibliotecas | 162 | Conversión de vídeo de WebRTC; candidato para un perfil solo audio |
| PyAV y bibliotecas | 101 | Tramas, códecs y transporte multimedia de WebRTC |
| ONNX Runtime | 49 | Detección local de voz y turnos |
| NumPy y bibliotecas | 48 | Procesamiento de muestras de audio |
| Node, fuera del entorno Python | 103 | Validación de workflows TypeScript |

El código de la aplicación ocupa una fracción de estos tamaños. La API mantiene
compatibilidad con los proveedores y transportes del original. Separar vídeo
y el validador de workflows permitiría otro perfil menor, pero requiere cambios
funcionales y pruebas específicas. Cambiar Python a Alpine no elimina estos
paquetes: Alpine usa musl y las extensiones nativas deben ser compatibles.
Fuentes: [imagen oficial Python](https://hub.docker.com/_/python) y
[etiquetas manylinux/musllinux](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/).

## Construcción reproducible por contexto

Inicializar el submódulo antes de construir. Los dos builds usan la raíz del repo:

```sh
git submodule update --init --recursive
docker build --target runner -f api/Dockerfile -t abera/dograh-api:hardening .
docker build -f ui/Dockerfile -t abera/dograh-ui:hardening .
docker build --target test -f api/Dockerfile -t abera/dograh-api:test-hardening .
```

El Dockerfile administrativo está en Automations, bajo
`products/abera-dograh/admin-image`; construir usando ese directorio como contexto.
En AWS promover imágenes por digest, después de ejecutar las pruebas.

## S3 y migración de datos anteriores

Configurar `S3_BUCKET`, `S3_REGION` y un rol IAM restringido. En local se pueden
usar credenciales AWS temporales mediante las variables AWS habituales. Bloquear
acceso público, habilitar cifrado y configurar CORS para el origen de la UI.
El runtime administrado usa el prefijo `subscriptions/<subscription_id>/`.

Las nuevas cuotas serializan escrituras mediante Redis y comprueban el total de
objetos actuales del prefijo antes de escribir. Las versiones históricas y los
backups se dimensionan aparte. La disponibilidad de Redis es necesaria para
escribir; los uploads gestionados son de un solo uso y tamaño limitado. Esta
validación local no comprueba el IAM ni las políticas de un bucket AWS real.

Para migrar un despliegue con datos MinIO:

1. Cerrar escrituras y respaldar su base y sus objetos.
2. Copiar los objetos conservando las claves; para un runtime administrado,
   anteponer únicamente el prefijo de esa suscripción.
3. Verificar inventario, tamaños y contenido; probar descargas y grabaciones.
4. Actualizar `storage_backend` de los registros migrados en `workflow_runs` y
   `workflow_recordings`, filtrando la organización correspondiente. Conservar
   sus claves relativas. El código rechaza el backend histórico `minio` hasta
   completar esta migración.
5. Reabrir tráfico con S3 y retirar el volumen anterior después de verificar
   la recuperación. Evitar `docker compose down -v` durante la migración.

Cloudflare es opcional: `ENABLE_CLOUDFLARE_TUNNEL=false` y
`BACKEND_API_ENDPOINT=http://localhost:8000` evitan la espera del túnel en local.
Para recibir webhooks telefónicos desde internet, usar una URL pública o activar
explícitamente el túnel y su perfil Compose.

## Verificación y límites

Los scripts `scripts/verify_api_runtime.py` y `scripts/verify_admin_runtime.sh`
comprueban dependencias, audio, ausencia de compiladores y un respaldo/restauración
local con pgvector. La UI optimizada respondió HTTP 200 en `/auth/login`.
Helm y los archivos Compose principales se validaron con valores de prueba.

La suite API se ejecuta con PostgreSQL/Redis exclusivos de pruebas, sin claves
de proveedores. No se gastó saldo de OpenAI en esta revisión.

Resultados de verificación:

- Suite completa inicial: 3.805 aprobadas y 2 omitidas; faltaba el generador
  TypeScript en la imagen de tests. Se incorporó únicamente al target `test`,
  y ambas pruebas de sincronización SDK pasaron.
- Repetición: 3.803 aprobadas y 2 omitidas; apareció una carrera en una
  aserción de interrupción que consultaba la salida antes de que su trabajador
  recibiera el evento. Se añadió espera acotada de su confirmación, manteniendo
  la comprobación de una sola interrupción. Las 145 pruebas del módulo pasaron.
- Verificación dirigida final: 79 aprobadas, incluidas cuotas concurrentes con
  Redis real, autorización de almacenamiento, reclamación SQL atómica del socket,
  SDK, autenticación y bloqueo del tester cuando el modelo no coincide.
- API Basic arrancada con la imagen final: health HTTP 200 en aproximadamente
  450 ms, sin descubrimiento Cloudflare. Este dato no mide capacidad de llamadas.

La integración del original corresponde a `75a299e2`; el submódulo Pipecat está
fijado a `291fa01a`. Se conservó la grabación de Abera en disco, según la resolución
de conflictos aprobada. El perfil de tests incluye fixtures del fork; el runtime
productivo los excluye.

Persisten trabajos de la entrega completa: conexión del contador de billing para
Pro, prueba real de IAM/S3 y ciclo de vida en AWS, migración del almacenamiento
local existente, carga/latencia desde Colombia y promoción de imágenes. Pro sigue
cerrado hasta conectar la autorización de minutos. Las grabaciones Pro conservan
el spool de disco aprobado; no son una subida continua a S3 y sus fallos de envío
todavía necesitan una política durable de reintentos antes de prometer retención.
