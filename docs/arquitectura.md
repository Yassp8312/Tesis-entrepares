# Arquitectura inicial de Entrepares

Se adopta la arquitectura documental v1 del 29 de octubre de 2026 y el desglose SP00–SP19 del plan OpenUP. Las ubicaciones se crean en SP01-T01; las funciones, dependencias, datos y contratos se implementarán en sus tareas correspondientes.

La resolución de dependencias de SP01-T02 ajusta la referencia DRF 3.16 a DRF 3.18.3 por avisos de seguridad corregidos. La decisión [DA03 E01](decisiones/DA03-E01-dependencias.md) registra la evidencia, compatibilidad e impacto en el tratamiento de errores. El registro documental original conserva su huella histórica.

## Capas

`frontend/src` contiene la interfaz. `backend/api/v1` adapta HTTP; `backend/application` coordina casos, autorización y transacciones. Los propietarios de reglas y persistencia son los módulos de `backend/modules`. `backend/config` aloja los ajustes y puntos de arranque. `backend/core` reserva utilidades técnicas sin datos de negocio.

Los paquetes de negocio no dependen de HTTP ni de la coordinación de aplicación. Los puntos de entrada CLI autorizados de Django en `management/commands` sí pueden llamar a `application`. Tener varios procesos web o de ejecución programada con el mismo código conserva el monolito modular.

## Propiedad de módulos

Cada paquete es propietario lógico de los registros indicados. La responsabilidad de desarrollo todavía no se ha distribuido entre colaboradores.

| ID | Paquete en `backend/modules` | Responsabilidad propietaria |
| --- | --- | --- |
| M01 | `identity` | Cuenta, credenciales, sesiones, control de correo y recuperación de identidad |
| M02 | `profiles` | Perfil, formación, experiencia, méritos declarados, contactos y completitud |
| M03 | `academics` | Instituciones, disciplinas, ámbitos, dominios reconocidos, verificación personal y distinción de investigador |
| M04 | `organizations` | Entidades, expedientes de verificación y representación vigente |
| M05 | `opportunities` | Proyectos que buscan colaboración, necesidades, financiación declarada, contacto público y vigencia |
| M06 | `publications` | Novedades, eventos, destacados y titularidad del contenido |
| M07 | `moderation` | Reportes, decisiones, medidas, restricciones y revisión |
| M08 | `access` | Capacidades, concesiones y reglas de autorización por contexto y recurso |
| M09 | `notifications` | Avisos, salida persistente, reclamación, intentos y resultado del envío |
| M10 | `audit` | Evidencia transversal de decisiones y acceso autorizado al historial |

## Condiciones de implementación

Vue y la API comparten origen. Se mantienen sesiones del servidor y CSRF explícito. Los módulos escriben a través de sus interfaces propietarias; los casos de aplicación coordinan los cambios y la auditoría requerida dentro de una transacción. Las notificaciones externas se ejecutan después de confirmar los registros persistentes correspondientes.

El usuario propio se prepara antes de la primera migración de autenticación. Las claves compuestas del modelo lógico requieren migraciones controladas. No se presume que una `ForeignKey` simple las represente ni se sustituyen las pruebas de PostgreSQL por SQLite.

La verificación personal no se deduce de representar una organización. La información declarada tampoco equivale a un respaldo. Las proyecciones públicas de contenidos no exponen los contactos privados de perfiles. Las condiciones PB y Q, y las propuestas RF45 y RF59, conservan el estado de la base documental y se resuelven en la operación afectada.

## Referencias

`base-documental.json` registra archivos de origen, versiones y huellas SHA256. Los originales permanecen en la carpeta DSRM de la tesis. Los documentos no se copian íntegros al repositorio; este registro permite identificar la versión utilizada sin incorporar datos de participantes.
