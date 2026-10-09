# Disponibilidad del runtime administrado

Con `DEPLOYMENT_MODE=abera`, el host comprueba la página de acceso local y señales de vida de ARQ y del orquestador antes de admitir escrituras. ARQ publica cada cinco segundos; el orquestador publica después de suscribirse a eventos, con vencimiento de quince segundos. Un reinicio elimina señales antiguas antes de lanzar los procesos.

Automations establece `abera:updating` antes de migrar. Mientras exista, la API rechaza escrituras con 503, ARQ espera antes de cada trabajo y el orquestador espera antes de procesar campañas. Las consultas siguen disponibles. El host elimina esta señal únicamente después de comprobar todos los contenedores, API, UI y trabajadores. Esta señal es distinta del drenado de llamadas: no impide los callbacks necesarios para terminar una llamada durante el drenado.

Los errores de Redis bloquean escrituras; no autorizan el acceso por omisión. Las señales demuestran que los procesos están vivos, no que cada integración externa funcione. La aceptación real debe probar creación, actualización y caída de UI/trabajadores en DEV.

Validación local: `python -m pytest --noconftest -q api/tests/test_managed_readiness.py` (sin base de datos ni proveedores). Las pruebas comprueban UI fallida, heartbeat ausente, cancelación del orquestador, pausa de trabajos y rechazo de escrituras durante mantenimiento.
