# Revisión del acceso para entrega local DEV

Evidencia consultada el 18 de octubre de 2026, hora de Bogotá. Cuenta
`374786578563`, región `us-east-2`. **Los cambios IAM están preparados y no se han
ejecutado. No se desplegaron aplicaciones ni se modificaron datos de clientes.**

Al retomar el 19 de octubre, el paquete pasó la verificación en almacenamiento
nativo de Ubuntu. AWS confirmó que ambas sesiones de operadores habían vencido
durante la pausa. La revalidación nativa actual y cualquier activación IAM requieren
renovar esa sesión compartida; los hashes y resultados de código permanecen válidos.

Se integraron las bases remotas consultadas durante esta preparación:
Automations `d2701533acf03c3ec0bf35acc0facc5f1457901e` y Billing
`212787ad280381c1c11540ff5008a14aac478bb7`. Incluyen verificación de reactivación
pagada, validación de solicitudes y mejor observación de fallos. La resolución
conserva los escenarios de restauración Dograh, las pruebas de origen de una
operación y la distinción entre cancelación normal por pago y fallo real.

## Accesos reutilizados

Se verificaron por STS las sesiones existentes y se leyeron las políticas fuente
con los lectores ya autorizados. Los dos roles SSO de bootstrap no tienen boundary,
políticas adjuntas ni denegaciones explícitas en sus políticas inline. El
seed-installer conserva su función; no se crearon usuarios, grupos ni permission
sets. La evaluación efectiva de STS sobre los roles destino sigue pendiente de
instalar la confianza revisada: hoy responde `AccessDenied` porque solo acepta OIDC.

La delegación usa confianza directa al rol IAM de la misma cuenta. AWS permite ese
recorrido sin un Allow adicional en la política de identidad, sujeto a boundaries
y denegaciones aplicables. [Referencia de AWS sobre políticas de confianza](https://aws.amazon.com/blogs/security/how-to-use-trust-policies-with-iam-roles/).

| Perfil existente | Rol SSO nativo | Destinos de entrega |
|---|---|---|
| `abera-dev-bootstrap` | `AWSReservedSSO_abera-dev-bootstrap-operators_03895323ad04423b` | Control plane y publicador de producto |
| `abera-dev-billing-bootstrap` | `AWSReservedSSO_abera-dev-billing-bootstrap_cfa35a75e04d3629` | Plan/apply Billing y publicador comercial |

Las confianzas fijan el ARN completo del rol SSO, con su sufijo nativo. Las sesiones
destino exigen `abera:delivery-origin=local` y duran como máximo una hora. Activar
este modo deniega OIDC y las acciones de sesiones sin esa etiqueta, incluso si se
emitieron antes. No cancela operaciones CloudFormation que ya estén corriendo.

## Cambios nativos preparados

Ambos change sets terminaron `CREATE_COMPLETE`, `ExecutionStatus=AVAILABLE`.
`DescribeEvents` confirmó la creación satisfactoria. Pasaron cfn-lint 1.54.0 y las
reglas cfn-guard fijadas. Se proyectaron sobre las plantillas instaladas; no copian
los permisos adicionales de una versión posterior del bootstrap.

| Stack | Change set | Modificaciones |
|---|---|---|
| `abera-dev-bootstrap` | `abera-dev-bootstrap-local-51a61fafec79aff4` | `GitHubDeploymentRole`, `GitHubProductPublisherRole` |
| `abera-dev-billing-bootstrap` | `abera-dev-billing-bootstrap-local-53caff6917ac864c` | `GitHubDeployRole`, `GitHubApplyRole`, `GitHubStateRecoveryRole` |

Todos son cambios `Modify`, `Replacement=False`; no agregan ni eliminan recursos.
Conservan grants, boundaries, identidades, buckets y claves instalados. Las
políticas reciben únicamente la denegación de sesiones sin origen local. El rol
de recuperación del estado Billing recibe la denegación OIDC, **sin conceder su
autoridad al operador local**. La recuperación de clientes sigue en API/worker/driver.

Hallazgo heredado: `abera-dev-billing-cfn-execution` conserva `iam:*` sobre `*` y
no tiene permissions boundary. Su política deniega usuarios y claves permanentes,
pero sigue teniendo autoridad IAM amplia. Reducir esa política requiere otra
revisión de todos los recursos de Billing; queda pendiente antes de afirmar que
su despliegue está completamente endurecido. Esta preparación mantiene sus grants
instalados y registra el hallazgo en la evidencia de permisos nativos.

Hashes de las revisiones locales de los resultados nativos:

- Automations: `d5ef75bcb49c57ed98808ca87b55638b5e3aa90ee86726b431576bf7e1017d6f`.
- Billing: `a759d2d129416f3d15f21c471b9d73d4b0b56c8501614514da90e7c2d09cb5c0`.

SHA-256 de los TemplateBody preparados:

- Automations, 50.249 bytes: `dec34fe6a2b48933a8fa4b3eeba77f183737b215a1638617aa38dcbea6d44f56`.
- Billing, 20.279 bytes: `ed3c1c0b8d0a55f8862ad95c71a2024fc90410c06b67c0224606b103afb6fea4`.

El detalle completo, ARN de cada change set, plantillas Original, parámetros
`UsePreviousValue`, eventos y pruebas de acceso se conservan en
`.local-services/basic-readiness/existing-access-2026-10-18/`. No contienen claves
exportadas ni copias de la caché SSO.

## Secuencia de activación pendiente

1. Revisar y autorizar estos dos cambios. Antes de ejecutarlos, volver a comprobar
   los hashes, plantillas base, parámetros y ausencia de operaciones nativas en curso.
2. Aplicar secuencialmente con sus perfiles bootstrap existentes y verificar el
   resultado nativo y las asunciones STS etiquetadas. Una denegación bloquea el avance.
3. Con el rol apply Billing ya habilitado, leer la plantilla Original de
   `abera-billing-dev-catalog`, proyectar únicamente su confianza y denegación de
   sesiones y preparar otro change set. Su revisión sigue pendiente; el perfil
   bootstrap actual no permite leer esa plantilla. Conservar las particiones
   comerciales vecinas, sin sustituirlas por una selección exclusiva de Dograh.
4. Solo después de esa revisión y activación, ejecutar `delivery status` y preparar
   cada review/apply desde el paquete probado. La CLI comprueba los cinco roles y
   la ausencia de operaciones previas antes de tomar el bloqueo S3.

Para revertir el acceso, preparar otro cambio revisado con las plantillas Original
conservadas y los parámetros nativos compatibles. Confirmar antes el cierre de la
entrega y las operaciones activas. No borrar roles, buckets, stacks ni bloqueos.
Restablecer OIDC habilita de nuevo los escritores GitHub y exige coordinación.

## Ejecutor local comprobado

Se reutilizó `Ubuntu-22.04`, usuario `abe` (UID 1000), con Python 3.13.15 y entornos
separados para Automations y Billing. Las dependencias se copiaron de la imagen
validada `sha256:71823e8e9a01a49278200c55f5c17ae164fecef841fa038a6119dd97592d755a`;
ambos entornos pasaron `pip check`. SAM 1.165.0 y AWS CLI existentes se conservaron.

El empaquetado Billing valida el rol de ejecución del stack API autorizado; usa el
bucket `abera-dev-billing-artifacts-374786578563` observado en el bootstrap, sin
pedir al rol apply acceso al stack del instalador. Una identidad de ejecución
diferente bloquea el empaquetado antes de subir archivos.

La unidad propia `abera-dev-delivery-docker.service` usa un socket y almacenamiento
separados. No está habilitada al iniciar sesión. El puente `credential_process`
reutiliza las sesiones Windows mediante un pipe, sin guardar credenciales. STS
confirmó ambos perfiles dentro del ejecutor.

Una prueba real rootless verificó 32 MiB, media CPU y 32 procesos en cgroup v2, y
retiró su contenedor. El contexto Docker sigue en `default`; los contenedores
anteriores no se reiniciaron. Se añadió únicamente delegación temporal para
`user@1000.service` en `/run/systemd/system/user@1000.service.d/abera-dev-delivery.conf`.
Se pierde al reiniciar WSL y debe volver a comprobarse antes de publicar.

También se construyó una imagen mínima sin red mediante buildx y se comprobó que
quedara en el daemon rootless verificado. El Docker original no recibió esa imagen;
la imagen de prueba se retiró al terminar. El builder existente declara soporte
para AMD64 y ARM64. Esta prueba valida el enrutamiento del builder; las imágenes
completas del producto siguen la revisión/publicación fijada de la entrega.

Operar solo la unidad propia mediante `scripts/local_delivery_wsl.py start|check|stop`
desde Automations, con su entorno y variables documentadas. Los datos y entornos
propios están en `/home/abe/.local/share/abera-dev-delivery`. Conservar el paquete,
journal y revisiones si una entrega termina con resultado incierto.

Después de comprobarlo, el daemon propio quedó `inactive`, sin habilitación al
inicio de sesión y sin contenedores auxiliares de dependencias. El contexto Docker
global continúa en `default`. El lanzador permite iniciarlo explícitamente cuando
el acceso y la revisión estén listos.

La preparación local y los change sets no acreditan aún restauración nativa,
caducidad física de backups, eliminación de recursos ni disponibilidad comercial.
Se mantienen los pendientes de [preparación comercial](BASIC_COMMERCIAL_READINESS.md).

La preparación de esta estación deja el lanzador local
`/home/abe/.local/share/abera-dev-delivery/run-dev-delivery.sh`, con rutas al paquete
inmutable y los entornos propios. La copia y verificación de sus 4.806 archivos se
completó el 19 de octubre en almacenamiento nativo de Ubuntu, evitando el bloqueo
de lectura observado en el disco montado. El SHA del paquete es
`d9b75c620244265cde70d23a0b80221aadee09a38f70592ee4eda143e1cb9ccd`.
Se conserva otra copia del lanzador en `.local-services/basic-readiness/`.
Desde PowerShell:

```powershell
wsl -d Ubuntu-22.04 --cd /home/abe --exec sh /home/abe/.local/share/abera-dev-delivery/run-dev-delivery.sh start
wsl -d Ubuntu-22.04 --cd /home/abe --exec sh /home/abe/.local/share/abera-dev-delivery/run-dev-delivery.sh status
```

`start|check|stop` operan únicamente el ejecutor local. `status` necesita la
confianza IAM activa y no toma el bloqueo. Para una revisión de aplicación, usar
`run --step review-control-plane --output <ruta-WSL-nueva>` y revisar su resultado
antes del apply correspondiente. El lanzador no ejecuta despliegues al arrancar.
