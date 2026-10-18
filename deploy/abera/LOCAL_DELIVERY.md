# Entrega local de Abera Dograh

El despliegue coordinado sin GitHub Actions se prepara desde la CLI de Automations:
[`delivery access-templates|prepare|run|status`](https://github.com/tomatoes-prog/abera-automation/blob/codex/dograh-basic-readiness/docs/local-delivery.md).
Los cambios están en [Automations #288](https://github.com/tomatoes-prog/abera-automation/pull/288)
y [Payments #101](https://github.com/tomatoes-prog/abera-payments/pull/101), junto con
la preparación comercial de este fork. Deben revisarse y validarse como conjunto.

El paquete congela los commits probados de Automations/Billing y exporta Dograh en
la revisión fijada en el manifiesto de producto, incluyendo el Pipecat exacto de
su gitlink. Las imágenes se construyen desde esas fuentes locales. No se incorporan
`.env`, archivos sin seguimiento ni el override de Docker Compose del usuario.
Cambios locales posteriores no se despliegan silenciosamente.

La ejecución necesita Python 3.13, el entorno fijado de Billing, SAM, AWS CLI,
Docker rootless y un perfil SSO dedicado DEV. Preparar el ejecutor antes de activar
el acceso. El Docker Desktop habitual por sí solo no cumple rootless; usar el
entorno WSL2/Linux documentado y seleccionar su daemon mediante `DOCKER_HOST`.
La CLI usa los roles existentes, revisa cada cambio nativo y conserva un bloqueo
compartido y journal S3. Un resultado incierto no libera automáticamente el bloqueo.

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
