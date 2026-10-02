# Prueba de cinco llamadas con GPT Realtime 2.1

Esta prueba mide llamadas WebRTC reales a Dograh con el proveedor propio del
cliente `openai_realtime` y el modelo `gpt-realtime-2.1`. La máquina que genera
las llamadas queda fuera de la EC2 o de la VM de Docker medida. El script no
crea agentes ni configura claves: usa una organización y workflows preparados
por el administrador de la suscripción Basic.

## Qué estamos comprobando

Queremos saber si el runtime de Basic puede atender cinco conversaciones reales
con 2 vCPU y 4 GiB, sin subir el tamaño de la instancia. Primero medimos una,
dos y cinco llamadas; luego repetimos cinco durante tiempo suficiente para ver
si se agotan los créditos de CPU de la EC2. Los cambios de TURN hacen posible
WebRTC desde otra red. Los monitores registran CPU, RAM, cortes y respuesta de
audio. Esta prueba **no fija por sí sola el cupo comercial**: también hay que
probar telefonía del cliente, variación de workflows y recuperación ante fallos.

| Valor | Dónde se configura | Para qué sirve |
|---|---|---|
| Clave API de OpenAI | En Dograh: `/model-configurations` → **Speech to Speech** → proveedor `openai_realtime` → **API Key(s)**. | Autoriza las llamadas de prueba a `gpt-realtime-2.1`. Es la clave propia del cliente Basic; no se coloca en Docker, billing ni Automations. |
| `DOGRAH_TEST_ACCESS_TOKEN` | Variable de entorno solo en la terminal que ejecuta el generador. | JWT de una sesión iniciada en Dograh para crear y consultar sus llamadas de prueba. |
| `DOGRAH_DEVOPS_SECRET` | Misma cadena aleatoria en el runtime API y en la terminal del generador. | Permite leer el endpoint interno de salud durante la medición. |
| `TURN_SECRET` | API y servidor TURN; Automations lo genera por suscripción en AWS. | Produce credenciales temporales para el relay WebRTC. No es una clave de OpenAI. |

No pegues ninguno de estos valores en tickets, chats, comandos compartidos ni
archivos versionados. El campo de la clave en Dograh oculta su texto en pantalla.

## Preparación

1. En Dograh, abre `/model-configurations` → **Speech to Speech**, configura
   la clave de OpenAI de la organización, selecciona `openai_realtime`, modelo
   `gpt-realtime-2.1`, voz e idioma español y guarda. Configura también el LLM
   que la pantalla exige para extracción y QA. Verifica
   por la UI que cada workflow usa esa configuración y que su duración máxima
   supera la duración de la prueba. El límite de Dograh es 1.200 segundos por
   llamada; usa 1.170 segundos para la ronda larga.
2. Usa un WAV con frases reales en español, mono, PCM16 y 48 kHz. El script
   envía fragmentos de voz de cinco segundos cada veinte segundos, desplazados
   entre los cinco clientes. No guardes en el repositorio grabaciones con datos
   personales.
3. Instala `api/load_tests/requirements.txt` en un entorno Python separado.
   Define `DOGRAH_TEST_ACCESS_TOKEN` con el JWT obtenido al iniciar sesión y
   `DOGRAH_DEVOPS_SECRET` con el secreto del runtime. No los pases como argumentos
   ni los guardes en el JSON de resultados.
4. Comprueba que `GET /api/v1/turn/credentials` responde para el usuario. En
   AWS, la misma EC2 sirve TURN en TCP/UDP 3478 y UDP 49152–49200; la API usa
   la dirección privada y el navegador, la pública. DEV fuerza el relay para
   incluir su costo en la prueba.

## Ejecución local

Limita la **VM de Docker Desktop completa** a 2 vCPU y 4 GiB. Limitar solo el
contenedor API deja UI, worker, Redis y TURN fuera de la prueba. Inicializa el
submódulo `pipecat`, prepara `.env` con `scripts/start_docker.ps1` y detén ese
primer arranque si quedó en primer plano. Para esta ronda añade a `.env`
`ENABLE_COTURN=true`, `TURN_HOST=<IPv4 de tu equipo en la LAN>`,
`TURN_INTERNAL_HOST=coturn`, `TURN_SECRET=<valor aleatorio>`,
`TURN_TLS_PORT=0`, `FORCE_TURN_RELAY=true` y `DOGRAH_DEVOPS_SECRET=<otro valor
aleatorio>`. Mantén esos valores solo en `.env`, que está ignorado por Git.

Construye este fork y levanta el perfil TURN con el override de esta carpeta:

```powershell
docker compose -f docker-compose.yaml -f api/load_tests/docker-compose.capacity.yaml --profile local-turn up -d --build
docker compose -f docker-compose.yaml -f api/load_tests/docker-compose.capacity.yaml ps
```

Identifica los nombres reales de los contenedores con `docker compose ps`. El
monitor rechaza una VM más grande. PostgreSQL y MinIO locales también usan
recursos de la VM, así que la comparación local es conservadora frente a AWS,
donde RDS y S3 están fuera de la EC2.

En una terminal PowerShell, inicia la medición durante la ronda de llamadas:

```powershell
$containers = docker compose -f docker-compose.yaml -f api/load_tests/docker-compose.capacity.yaml --profile local-turn ps -q
python -m api.load_tests.monitor_docker --containers $containers --duration 1300 --interval 10 --output .\capacity-docker.json
```

En otra terminal, desde el equipo generador de carga:

```powershell
python -m api.load_tests.realtime_capacity --base-url http://localhost:8000 --workflow-ids 123 --wav .\voz-es-48k.wav --clients 1 --seconds 120 --output .\capacity-1.json
python -m api.load_tests.realtime_capacity --base-url http://localhost:8000 --workflow-ids 123 --wav .\voz-es-48k.wav --clients 2 --seconds 120 --output .\capacity-2.json
python -m api.load_tests.realtime_capacity --base-url http://localhost:8000 --workflow-ids 123 --wav .\voz-es-48k.wav --clients 5 --seconds 1170 --output .\capacity-5.json
```

Los cinco clientes pueden usar el mismo workflow o cinco IDs separados por
comas. Un solo workflow de prueba deja margen para los otros cuatro agentes
del plan Basic. Repite la ronda de cinco durante al menos dos ciclos de
20 minutos con 40 minutos de reposo entre ciclos. La prueba local aproxima
CPU y RAM; el crédito de CPU solo puede validarse en la EC2 real.

## Ejecución en DEV

Usa un suscriptor Basic de prueba en `t3a.medium` y ejecuta el generador
desde otra máquina, con `--base-url https://<host>.apps.dev.abera.cloud`.
Recoge CPU, memoria, disco y red de la instancia; `CPUCreditBalance` se
publica con resolución de cinco minutos, por lo que hay que observar más de
un ciclo de 20/40 minutos. Después de terminar:

```powershell
python -m api.load_tests.collect_aws_metrics --instance-id i-xxxxxxxxxxxxxxxxx --subscription-id <subscription-id> --start 2026-09-30T02:00:00Z --end 2026-09-30T05:00:00Z --region us-east-2 --output .\capacity-aws.json
```

El recolector comprueba los tags de producto, suscripción y entorno antes de
consultar CloudWatch. El JSON de llamadas incluye los estados de cada sesión,
audio recibido, tiempos de respuesta, uso registrado por Dograh, llamadas
activas y retraso del event loop. El JSON de Docker incluye CPU y RAM por
proceso; el de AWS incluye CPU de EC2, saldo de créditos y las métricas del
agente. Conserva los tres resultados de la misma ventana temporal.

**Criterio para habilitar el cupo:** cinco de cinco llamadas terminan con audio
de respuesta y run finalizado, sin OOM, reinicios ni desconexiones; la RAM
mantiene margen para los procesos de fondo, el retraso del event loop y la
latencia de voz son aceptables en el caso real, y el saldo de créditos no
desciende ciclo tras ciclo. La CPU media de cada hora de prueba debe quedar
por debajo de la línea base de `t3a.medium` (20 % de utilización de EC2), con
margen para backups y picos. Documenta el umbral de latencia aceptado antes
de anunciar concurrencia comercial. Repite desde una red colombiana y con
telefonía del cliente: WebRTC con OpenAI no mide el costo de ese transporte.

Si todavía no hay imágenes publicadas, AWS DEV o credenciales, conserva el
resultado como **pendiente**. `provisioningEnabled: false` impide contratar
Dograh mientras no pasen estos ensayos y los controles de aislamiento y
restauración.
