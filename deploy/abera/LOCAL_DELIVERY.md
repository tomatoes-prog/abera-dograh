# Entrega local de Abera Dograh

El despliegue coordinado sin GitHub Actions se prepara desde la CLI de Automations:
[`delivery access-templates|prepare|run|status`](https://github.com/tomatoes-prog/abera-automation/blob/codex/dograh-basic-readiness/docs/local-delivery.md).
Los cambios están en [Automations #288](https://github.com/tomatoes-prog/abera-automation/pull/288)
y [Payments #101](https://github.com/tomatoes-prog/abera-payments/pull/101), junto con
la preparación comercial de este fork. Deben revisarse y validarse como conjunto.

La vía local se añade a GitHub OIDC, que permanece habilitado. Los workflows DEV
de Automations y Billing y el ejecutor local comparten el mismo bloqueo S3 y
journal. Un fallo o cancelación conserva la exclusión hasta reconciliar la
ejecución. Cuando vuelva la cuota de Actions se podrá usar ese recorrido sin
cambiar la confianza IAM ni retirar el acceso local.

El paquete congela los commits probados de Automations/Billing y exporta Dograh en
la revisión fijada en el manifiesto de producto, incluyendo el Pipecat exacto de
su gitlink. Las imágenes se construyen desde esas fuentes locales. No se incorporan
`.env`, archivos sin seguimiento ni el override de Docker Compose del usuario.
Cambios locales posteriores no se despliegan silenciosamente.

La ejecución necesita Python 3.13, el entorno fijado de Billing, SAM, AWS CLI,
Docker rootless y los perfiles SSO existentes `abera-dev-bootstrap` y
`abera-dev-billing-bootstrap`. El seed-installer mantiene su función; no hace falta
crear otro usuario, grupo ni permission set. Preparar el ejecutor antes de activar
el acceso. El Docker Desktop habitual por sí solo no cumple rootless; usar el
entorno WSL2/Linux documentado y seleccionar su daemon mediante `DOCKER_HOST`.
La CLI usa los roles existentes, revisa cada cambio nativo y conserva un bloqueo
compartido y journal S3. Un resultado incierto no libera automáticamente el bloqueo.

El helper WSL de Automations prepara una unidad de usuario propia
`abera-dev-delivery-docker.service`, sin cambiar el contexto Docker ni los servicios
existentes. Python 3.13 y las dependencias de cada repositorio se mantienen en
entornos separados. El puente de credenciales reutiliza SSO Windows mediante un
pipe; no copia tokens ni guarda claves. El servicio tiene inicio y apagado explícitos.

Los cambios de acceso se proyectan sobre las plantillas instaladas, conservando
permisos y recursos. Se revisan primero `abera-dev-bootstrap` y
`abera-dev-billing-bootstrap`; después el rol apply de Billing permite leer y
preparar la confianza de `abera-billing-dev-catalog` sin ampliar su acceso comercial
a otros productos. Ese tercer paso requiere su propia comparación y revisión nativa.

El boundary del publicador Automations también necesita el permiso acotado del
bloqueo y journal, preservando su identidad y límites. Su proyección parte del
security seed DEV instalado y requiere alojar la plantilla por hash y revisión
nativa separada. Integrar las guardias de los workflows e instalar esos permisos
como una activación coordinada; los workflows anteriores no toman el bloqueo S3.

La [revisión de acceso DEV](DEV_LOCAL_ACCESS_REVIEW.md) conserva los cambios
CloudFormation concretos, hashes, perfiles verificados y estado del ejecutor local.

Publicar una release técnica, promover el default, actualizar clientes y publicar
el catálogo comercial son pasos separados. Los archivos históricos siguen
recuperándose con su release original y las transiciones declaradas. No borrar
shards, tablas, backups o stacks para corregir el despliegue. Las migraciones de
datos requieren su procedimiento compatible de restauración.

La habilitación SSO/IAM y el primer despliegue real requieren revisión. Antes de
activar nuevas ventas siguen pendientes las comprobaciones nativas descritas en
[la preparación comercial](BASIC_COMMERCIAL_READINESS.md), incluida la transición
RDS instalada, restauración y eliminación física. Esta documentación no acredita
un despliegue AWS ni una activación comercial ya realizados.
