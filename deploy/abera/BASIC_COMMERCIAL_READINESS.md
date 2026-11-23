# Preparación comercial de Basic

Estado: implementación y validación local; aceptación de DEV pendiente. Esta
entrega coordina el runtime, `abera-automation` y `abera-payments`. No despliega
PROD ni habilita Pro. El catálogo técnico y el catálogo de ventas se publican
por sus flujos existentes, conservando las releases y los contratos anteriores.

También se prepara una [entrega local coordinada](LOCAL_DELIVERY.md) mediante
Automations CLI y SSO dedicado DEV, con fuentes fijadas, revisión nativa y bloqueo
compartido. La instalación de IAM y el primer despliegue quedan pendientes de revisión.

## Documentos y almacenamiento

La revisión Alembic `d9e621a7f304`, posterior a `c82d4f6a9b10`, registra las
cargas antes de devolver su URL y las obligaciones de eliminación en la misma
transacción que desactiva el documento. El backfill conserva los documentos
activos e históricos y comprueba que cada destino pertenece a su organización.
Un destino inválido aborta la migración completa para su revisión.

Eliminar un documento retira inmediatamente su texto y fragmentos de las
consultas. El worker ARQ existente procesa la limpieza cada cinco minutos:
borra todas las versiones y marcadores de la clave exacta en S3, comprueba su
ausencia y después redacta sus metadatos. Los errores conservan la obligación
en PostgreSQL y se reintentan; perder Redis no pierde la eliminación. No se
considera una lectura denegada como ausencia. La respuesta del endpoint
confirma la baja lógica, no una eliminación física ya terminada.

El inventario paginado encuentra archivos antiguos sin trabajo de cola y
escrituras tardías; conserva documentos activos y no adopta organizaciones
desconocidas. Las cargas abandonadas tienen dos horas de gracia, frente a una
URL firmada de hasta una hora. El proxy administrado limita cada recepción a
300 segundos. Un escritor de contenido mantiene un bloqueo de fila para que
el borrado espere a su cierre; los procesos tardíos no pueden reactivar texto
ni embeddings de un documento eliminado. Los tombstones conservan una huella
de la clave para reconocer una recreación tardía.

La instancia necesita `s3:ListBucketVersions` y `s3:DeleteObjectVersion` sobre
su propio prefijo de datos. Automations entrega ambos permisos con su límite
IAM existente. No se agrega un servicio, bucket ni worker independiente.
S3 continúa siendo el almacenamiento administrado. El adaptador de disco
local completa su interfaz y restringe rutas a su raíz.

## Respaldo y restauración

Antes de actualizar se drena el runtime y se detiene el host. Automations
conserva una copia verificada y versionada del PostgreSQL del cliente, archivos,
objetos y secretos de aplicación. El ledger de pagos queda fuera del respaldo.
La copia previa a UPDATE o RESTORE se protege antes de admitir migradores o
importadores; su protección solo se libera tras éxito o compensación verificada.
La obligación existe antes de que ECS comience a escribir, incluso si la copia
falla a mitad de camino.

Se comprobó la migración con PostgreSQL 17 y datos ficticios, un documento
activo y otro histórico. Un `pg_dump --format=custom` de la revisión anterior
se restauró en otra base mediante `pg_restore --exit-on-error`. Los documentos
antes de migrar, después de migrar y después de restaurar tienen la misma
huella: `a060fde63af98cd446055354ba5dc83e9bda4aad85da047af1704dd3e2333d62`.
La migración generó una obligación `attached` y otra `deleting`. La restauración
recuperó la revisión `c82d4f6a9b10`. Esto complementa la prueba del catálogo y sus
versiones archivadas en [la actualización selectiva](UPSTREAM_UPDATE_2026_10.md).

Ante un fallo, mantener detenido el runtime y usar RESTORE/compensación de
Automations con el manifiesto y VersionId originales. Restaurar juntos base,
archivos, objetos y secretos; arrancar las imágenes compatibles de la copia y
comprobar salud e aislamiento antes de reabrir tráfico. Una imagen anterior
por sí sola no revierte las migraciones. El downgrade rechaza obligaciones de
carga o limpieza pendientes. Un respaldo anterior puede contener datos ya
eliminados: su retención y su restauración requieren el procedimiento revisado.

## Condiciones para aceptar DEV

- Aceptar la release técnica candidata y su actualización piloto antes de
  promover el default y publicar el catálogo comercial de Basic. Payments
  conserva precios y límites y cierra las ofertas Pro hasta aceptar la reserva
  y liquidación de minutos del runtime.
- Comprobar la política instalada: DEV programa respaldo diario y retención de
  un día; PROD conserva intervalo de siete días y recuperación de treinta días.
  Publicar una foundation no actualiza los shards RDS ya instalados. El cambio
  de retención del shard activo necesita su revisión de CloudFormation.
- S3 Lifecycle expira de forma asíncrona; en buckets versionados la eliminación
  de la versión corriente y la de versiones anteriores son pasos diferentes.
  Una regla de un día no demuestra ausencia física a las 24 horas. Medir el
  inventario nativo y no certificar ese máximo estricto con solo la regla.
  Las copias protegidas o archivadas no se borran por una retención ordinaria.
- Probar en una instalación QA expresamente autorizada: suspensión, renovación,
  actualización fallida y recuperación, ARCHIVE/RECOVER y PURGE. Comprobar
  compute, ECS, EFS, datos, versiones, backups y secretos con evidencia nativa.
  No reutilizar la instalación del cliente para una prueba destructiva.
- El retiro automático de nuevos logs RDS está limitado a DEV y a recibos con
  generación y dueño verificables. Los logs históricos sin esa autoridad siguen
  requiriendo revisión; un stack `DELETE_COMPLETE` no prueba que desaparecieron.

La validación local de esta rama incluye 81 pruebas de migración, concurrencia,
aislamiento, reintentos, documentos y enlaces S3; la imagen de producción del
API también compila. Las pruebas simuladas y la restauración local no certifican
el retiro completo de recursos reales ni una cuenta AWS sin huérfanos.
