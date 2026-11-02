# DA04 E01 Cuenta propia y configuración inicial

Fecha: 2 de noviembre de 2026. Concreción técnica de T01 y de las decisiones DA04, DA05 y DA11 para SP01-T03.

## Decisión

Implementar `identity.Account` mediante `AbstractBaseUser` y `PermissionsMixin`, con las nueve columnas de `identity_account` definidas en el diccionario. Se conserva el índice funcional único `lower(email)` y los dos CHECK previstos. UUID y fechas tienen valores de aplicación y, cuando corresponde, valores predeterminados de base equivalentes a los del esquema de referencia.

El gestor busca mediante la misma función `lower` del índice y conserva la dirección para entrega. El adaptador de credenciales reutiliza la autenticación de Django. Las contraseñas y las comprobaciones de habilitación no se reimplementan. La API se configura con sesiones y con denegación de permisos por omisión hasta que cada operación incorpore su autorización explícita.

## Compatibilidad de Django

El chequeo genérico de autenticación no reconoce el índice funcional como la unicidad simple del campo. Se mantiene un backend de correo y se sustituye únicamente `auth.W004` por el chequeo de aplicación `identity.E001`. Este exige el modelo y el índice concretos y produce un error si desaparecen. Una prueba retira la restricción del modelo en memoria y comprueba ese fallo. No se añade un índice único redundante que altere el diseño lógico.

Las relaciones de grupos y permisos del mixin crean dos enlaces de infraestructura Django. Las banderas y permisos técnicos siguen separados de las capacidades de M08; el hecho de ser superusuario técnico no abre una operación HTTP sin autorización configurada.

La migración de identidad depende de la última migración de infraestructura auth disponible, pero `AUTH_USER_MODEL` ya sustituye al usuario estándar desde el principio. El grafo demuestra el reemplazo; la aplicación sobre una base vacía se comprobará en SP01-T04.

## Fuentes

- [Personalización de autenticación y primera migración del usuario propio](https://docs.djangoproject.com/en/5.2/topics/auth/customizing/#substituting-a-custom-user-model).
- [Restricciones únicas por expresiones](https://docs.djangoproject.com/en/5.2/ref/models/constraints/#uniqueconstraint).
- [API de contraseñas de Django](https://docs.djangoproject.com/en/5.2/ref/contrib/auth/#django.contrib.auth.models.User.set_password).
