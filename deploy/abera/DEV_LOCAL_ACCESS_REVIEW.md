# Acceso DEV para entrega local y GitHub

Modalidad vigente desde el 19 de octubre de 2026: **conservar ambas vías**.
La confianza SSO local es aditiva; GitHub OIDC, sus sesiones y la recuperación de
estado de Billing siguen habilitados. El bloqueo S3 compartido evita entregas
simultáneas. **No se aplicó IAM, no se desplegaron aplicaciones ni se modificaron
datos de clientes.**

Las dos revisiones anteriores del modo exclusivo se descartaron y retiraron sin
ejecutar. Sus plantillas y evidencia histórica se conservan; sus change sets ya
no autorizan una activación. No usar sus hashes para esta entrega.

## Perfiles existentes

Cuenta `374786578563`, región `us-east-2`. AWS confirmó las dos sesiones renovadas,
sus roles nativos exactos y 25 stacks DEV sin operaciones en curso.

| Perfil | Rol SSO nativo | Destinos |
|---|---|---|
| `abera-dev-bootstrap` | `AWSReservedSSO_abera-dev-bootstrap-operators_03895323ad04423b` | Control plane y publicador de producto |
| `abera-dev-billing-bootstrap` | `AWSReservedSSO_abera-dev-billing-bootstrap_cfa35a75e04d3629` | Plan/apply y publicador comercial Billing |

El seed-installer conserva su función. No se crearon usuarios, grupos ni permission
sets. Las asunciones locales exigen el ARN SSO completo y
`abera:delivery-origin=local`, con duración máxima de una hora. La etiqueta no se
exige a las sesiones OIDC. El operador local no recibe la recuperación de estado.

## Revisiones aditivas preparadas

Ambos change sets están `CREATE_COMPLETE` / `AVAILABLE`. Solo modifican los roles
existentes, con `Replacement=False`; no agregan ni eliminan recursos. Las
proyecciones preservan las declaraciones OIDC, grants de negocio, boundaries,
integraciones, claves y parámetros nativos mediante `UsePreviousValue`.

| Stack | Change set | Recursos |
|---|---|---|
| `abera-dev-bootstrap` | `abera-dev-bootstrap-coexist-71ff70d81ac493cd` | `GitHubDeploymentRole`, `GitHubProductPublisherRole` |
| `abera-dev-billing-bootstrap` | `abera-dev-billing-bootstrap-coexist-baff0d1e10138b58` | `GitHubDeployRole`, `GitHubApplyRole`, `GitHubStateRecoveryRole` |

El rol core ya puede coordinarse con su política instalada del bucket. Los roles
de producto y Billing reciben solo `s3:GetObject`/`s3:PutObject` sobre
`delivery/dev/fence.json` y `delivery/dev/runs/*` del bucket canónico
`abera-dev-artifacts-374786578563-us-east-2`. El rol de recuperación solo añade
ese permiso de coordinación y conserva su confianza OIDC.

| Revisión | SHA-256 de revisión | SHA-256 de TemplateBody | Bytes |
|---|---|---|---:|
| Automations | `0a44b070750760857a2e3470b83ede588d6aef121248c6dec80bc436010640f7` | `7e6727f49e561973143ce8b2f17a32fba69f5cd9d64eaae8f101a590150bc593` | 50.014 |
| Billing | `0155840de14d0b7d548d04e74d6612ff2eb371abf91a5af28621b10e66093706` | `4991ebe260f362ac83709aca92a1797f2c6bf8878c090f157fcf06a39fb613b5` | 20.296 |

La evidencia y los ARN completos están en
`.local-services/basic-readiness/coexisting-access-2026-10-19/`.
Las cuatro plantillas candidatas pasaron cfn-lint 1.54.0; las de bootstrap/catalogo
Billing también pasaron cfn-guard. Las revisiones no se ejecutaron.

## Permiso que falta en el boundary

La lectura IAM nativa confirmó que el boundary del publicador de producto
`abera-dev-product-deployment-boundary` v17 permite objetos de producto/catálogo,
pero todavía no los objetos del bloqueo. Su ampliación limitada sigue pendiente.

`delivery access-templates --security-seed-template <Original-DEV.json>` produce
una proyección del seed instalado que cambia únicamente ese managed policy y
añade una regla de cuenta DEV. Conserva identidades, grants y recursos retenidos.
La plantilla supera 51.200 bytes: requiere alojarla por hash bajo
`bootstrap/dev/templates/` mediante el publicador autorizado y preparar su
change set por `TemplateURL` con el seed-installer. No sustituirla por el seed
completo de otra versión ni retirar el boundary para desbloquear el despliegue.

La confianza del catálogo `abera-billing-dev-catalog` también necesita su lectura
nativa con el rol apply ya habilitado y su revisión aparte. El candidato generado
con selección Dograh sigue marcado `catalogNativeComparisonRequired=true`;
no reemplaza las particiones comerciales vecinas.

## Activación coordinada pendiente

1. Integrar los workflows con la guardia de bloqueo en las ramas de entrega.
   Terminar o cancelar los jobs anteriores, incluidos los que sigan en cola: sus
   commits no participan en el bloqueo S3 aunque se integre el workflow nuevo.
2. Revalidar hashes, parámetros, plantillas base y operaciones en curso; aplicar
   únicamente las dos revisiones bootstrap aditivas exactas.
3. Alojar y revisar el cambio mínimo del boundary con el seed-installer. Leer y
   proyectar el catálogo nativo con apply Billing, preservando todas sus particiones;
   revisar y aplicar únicamente su confianza y permiso de coordinación.
4. Inicializar el estado del bloqueo con el coordinador Automations y verificar
   permisos efectivos de todos los actores. Un acceso denegado no equivale a ausencia.
5. Preparar cada review/apply desde el nuevo paquete probado. Mantener separadas
   publicación de release, promoción de default y actualización de clientes.

Los workflows toman el bloqueo antes de escribir y comprueban su propietario antes
de los pasos bash, incluso al cambiar de rol. Solo un job exitoso lo libera.
Un fallo, cancelación o resultado incierto conserva el bloqueo para reconciliación;
no borrarlo ni iniciar otra selección. Restaurar acceso local consiste en retirar
su confianza mediante un cambio revisado; OIDC no necesita volver a habilitarse.

## Ejecutor y pendientes

El ejecutor propio WSL Ubuntu-22.04 usa Python 3.13.15, entornos separados,
SAM y credenciales temporales por pipe desde Windows. Pasó de nuevo las
comprobaciones de sesiones, Docker rootless y capacidades CPU/memoria/procesos.
Su unidad `abera-dev-delivery-docker.service` quedó apagada y sin habilitación al
inicio de sesión. El contexto WSL continúa en `default`; Windows utiliza su
contexto `desktop-linux`. No se modificaron esos contextos ni otros servicios.

La aceptación vigente terminó con **23 controles PASS, 4.952 pruebas pasadas y
3 omisiones PowerShell**. El paquete de coexistencia tiene 4.810 archivos y SHA-256
`948fb365b5e7c888abaae95ebe6446ffc75ba4cfd3e3c8e383a25527efd8086c`.
Se verificó completo en almacenamiento nativo de Ubuntu, se actualizó el lanzador
propio y se repitieron arranque, sesión, capacidades y apagado. Su ubicación es
`/home/abe/.local/share/abera-dev-delivery/bundles/<SHA>/`; el lanzador es
`/home/abe/.local/share/abera-dev-delivery/run-dev-delivery.sh`.

El código y procedimiento están coordinados en
[Automations #288](https://github.com/tomatoes-prog/abera-automation/pull/288),
[Billing #101](https://github.com/tomatoes-prog/abera-payments/pull/101) y
[Dograh #4](https://github.com/tomatoes-prog/abera-dograh/pull/4).
Las bases integradas conservan la reactivación pagada y observabilidad recientes.

El ejecutor CloudFormation heredado de Billing conserva `iam:*` sobre `*`, sin
boundary; su reducción requiere otra revisión de compatibilidad y sigue pendiente.
La preparación no acredita aún restauración nativa, transición RDS 7→1 día DEV,
caducidad física S3, eliminación completa de huérfanos ni disponibilidad comercial.
Ver [preparación comercial](BASIC_COMMERCIAL_READINESS.md) y
[operación local](LOCAL_DELIVERY.md).
