# Contraste de esquema y datos sintéticos

SP02-T16 contrasta el esquema implementado con el diccionario lógico v1 y el SQL PostgreSQL del 29 de octubre de 2026. Abarca WI05/WI09, los diez propietarios y DL01–DL20; aporta evidencia parcial de RNF12/RNF14, AT15/AT18 y los VD de integridad asociados. No acredita todavía las transiciones funcionales o el piloto.

## Referencia independiente y reproducible

`backend/tests/reference/logical-schema.json` es una proyección estructural del diseño: nombres, tipos, nulabilidad, valores predeterminados, PK, CHECK, claves únicas, FK, índices y columnas de cuatro vistas. Contiene **37 tablas, 345 campos, 85 FK y 143 CHECK**. No contiene respuestas de encuestas, entrevistas, personas o datos del piloto, ni copia íntegra los documentos de tesis.

El generador `scripts/crear_referencia_esquema.py` verifica la huella del diccionario identificada en `base-documental.json` y la huella fija del SQL de referencia. Comprueba la correspondencia entre ambos antes de generar el contrato: campos, reglas, claves e índices. No conecta a PostgreSQL ni ejecuta el DDL de la tesis. Los originales conservan su huella y estado histórico.

La proyección se reproduce mediante `--dictionary`, `--sql` y `--output`, usando las rutas de las fuentes disponibles en la carpeta DSRM. La regeneración en `.cache/sprint02/t16-referencia-regenerada.json` produjo exactamente los mismos bytes que el contrato del repositorio. Las pruebas no necesitan que la carpeta DSRM exista en otra copia: utilizan el contrato versionado y sus huellas de origen.

Este contrato procede del diseño, no se genera a partir de la base que se intenta comprobar. Una diferencia futura exige revisión; no se debe actualizar la referencia desde la implementación para hacer pasar las pruebas.

## Catálogo, campos y referencias

`tests.support.schema` inspecciona `pg_class`, `pg_attribute`, `pg_constraint`, `pg_index` y los catálogos complementarios. Las lecturas no consultan filas de usuarios o proyectos. Se comprueba:

- Inventario exacto de tablas del producto, sus 345 campos y las cuatro vistas; la infraestructura Django se identifica por separado.
- Tipo, nulabilidad y expresión de valor predeterminado por nombre de columna. Solo se normalizan alias PostgreSQL, espacios de precisión numérica y casts de constantes al tipo de columna ya comprobado; se conservan los literales.
- Las 37 PK, claves únicas y las 85 FK, incluidas sus columnas y orden, destino en el mismo esquema, ON DELETE RESTRICT, ON UPDATE NO ACTION, MATCH SIMPLE, validación y carácter no diferible.
- Índices válidos, listos e inmediatos, método btree, claves/expresiones, dirección, orden de NULL, unicidad, NULLS NOT DISTINCT, ausencia de INCLUDE y clases de operadores.
- Inventario de los 143 CHECK y los filtros de índices; las reglas se comparan además por aceptación de fronteras sintéticas.

Las opciones descendentes se leen de `pg_index.indoption`: la proyección por columna de pg_get_indexdef no basta para comprobar DESC. La dirección de published_at en los dos índices de publicación se conserva. Las clases de operadores se comprueban expresamente; no basta con que exista un índice de nombre parecido.

Una prueba adicional carga los modelos actuales y los modelos históricos de `MigrationExecutor.project_state()`: ambos representan los mismos 345 campos concretos con sus tipos, nulabilidad y PK. El plan hacia las hojas de migración aplicadas está vacío. Los M2M y demás registros técnicos de Django se separan de ese inventario de negocio.

## Concreciones documentadas

El esquema de desarrollo y el reconstruido por migraciones coinciden con el contrato teniendo en cuenta las concreciones explícitas de `schema-adjustments.json`:

| Objeto | Representación de diseño e implementación |
| --- | --- |
| uq_t06_01 de contactos de perfil | Índice único completo → restricción UNIQUE y su índice de apoyo, mismos campos. |
| uq_t22_01 de contactos de oportunidad | Índice único completo → restricción UNIQUE y su índice de apoyo, mismos campos. |
| uq_t34_01 de avisos | Índice único → restricción UNIQUE con sus cuatro campos y NULLS NOT DISTINCT conservados. |
| access_capability_code_72401c64_like | Índice auxiliar que Django crea para patrones sobre la PK varchar, con varchar_pattern_ops; adicional a la PK. |

Las tres conversiones también se comprueban insertando duplicados, incluido channel=NULL en avisos. El registro no admite comodines o exenciones por prefijo. Si se retiran las concreciones del comparador, este detecta las diferencias; si cambian sus campos, unicidad, clase de operador o semántica de NULL, también falla.

Las 36 variaciones de orden físico de columnas por creación/herencia ORM se registran como notas. El contraste se hace por nombre; los índices y las FK mantienen su orden lógico. El resultado contiene **153 índices físicos y 19 restricciones UNIQUE**, frente a 99 índices explícitos y 16 restricciones UNIQUE en la referencia: las tres conversiones reutilizan sus índices y el auxiliar añade uno. Las 37 PK y 85 FK no cambian.

Estas son concreciones técnicas de persistencia, no cambios de requisitos o validaciones de autoridades. Los originales de arquitectura, diccionario y permisos permanecen intactos.

## Fronteras y lógica de tres valores

El comparador evalúa el CHECK de referencia y la expresión instalada por PostgreSQL sobre el mismo conjunto de valores generados. Incluye vacíos/espacios/tabuladores, literales de estados, UUID iguales/distintos, números negativos/cero/positivos, fechas anteriores/iguales/posteriores, booleanos y tipos JSON, incluido JSON null separado de NULL SQL. Las combinaciones usan solo tipos y nulabilidad admisibles de cada columna.

Para CHECK se compara aceptación mediante IS NOT FALSE: PostgreSQL admite TRUE o UNKNOWN. Para un filtro de índice se compara IS TRUE: UNKNOWN no selecciona la fila. No se sustituyen esas reglas por igualdad textual o una interpretación Python de SQL.

Se evaluaron **8568 combinaciones para 156 predicados: 143 CHECK y 13 filtros de índices**, sin discrepancias. Se ejecuta SQL SELECT con parámetros enlazados y un subconjunto de expresiones cerrado; se rechazan sentencias, comentarios, referencias ajenas o llamadas no admitidas, incluso si el nombre de una función coincide con una columna.

Es evidencia sobre un conjunto finito explícito de fronteras, **no una demostración formal para cualquier valor posible**. Las pruebas propietarias existentes siguen comprobando rechazos de inserción, FK, concurrencia y transiciones parciales en sus respectivos ámbitos. Las pruebas nuevas debilitan temporalmente un CHECK a true y cambian acción/deferibilidad de una FK en la base efímera: el contraste detecta ambas alteraciones y el rollback restaura el esquema.

## Fábricas identificadas y aisladas

`tests.support.factories.SyntheticFactory` crea un grafo de las 37 tablas, rellenando sus 345 campos y referencias. Los UUID y etiquetas derivan de un namespace del conjunto; los nombres llevan SINTETICO y los correos/URL usan example.invalid. Dos namespaces generan conjuntos independientes sin compartir posiciones únicas. Se prueban variantes de expediente manual y de correo institucional, ambas pendientes.

La fábrica solo escribe con configuración de prueba, rol entrepares_test, base test_entrepares, host local y cluster privado identificado de PostgreSQL 17. La comprobación del cluster se renueva al cambiar la conexión. Los preflight de pytest se conservan. No hay comando para sembrar estos datos en desarrollo o producción.

Las cuentas tienen contraseña inutilizable y ninguna bandera técnica de privilegio. Verificaciones pendientes, representación y medidas revocadas, concesiones/distinciones terminadas, contenido oculto o borrador, aviso y salida cancelados evitan que el corpus se confunda con actividad o autorización real. Los metadatos de correo llevan sample-only. Son referencias válidas para probar persistencia, no una recreación de decisiones institucionales.

La construcción completa es atómica. Una prueba introduce un fallo después de financiación: se revierte el grafo parcial de varios propietarios y se conserva un conjunto anterior. La lectura posterior de las 37 tablas recupera los 345 valores esperados, decodificando JSON conforme al contrato del campo. Las vistas confirman perfil completo, ausencia de respaldo personal/organizacional y financiación declarada de importe cero, sin confundir conceptos.

## Herramientas y resultados

`scripts/contrastar_esquema.py --output <ruta>` inicia una transacción REPEATABLE READ READ ONLY. Inspecciona metadatos y evalúa fronteras generadas; no inserta o modifica registros del producto. Se ejecuta con el entorno Django del proyecto, por ejemplo mediante el uv fijado y `--env-file .env`. El informe distingue diferencias, notas técnicas, contadores y resultados por predicado; un contraste no satisfactorio devuelve salida distinta de cero.

Las pruebas específicas son `scripts/probar.ps1 -Modo unitarias backend/tests/test_schema_contract.py` y `scripts/probar.ps1 -Modo integracion backend/tests/test_schema_postgresql.py`. Para conservar evidencias, usar `--junitxml` y un `--basetemp` nuevo dentro de `.cache/sprint02`. El flujo general es `scripts/comprobar.ps1 -ConPostgreSQL`.

Las cifras finales, huellas y estado de desarrollo se registran en [la evidencia de T16](evidencias/esquema-y-datos-sinteticos.json). No se añaden modelos, migraciones, dependencias o datos de participantes. La siguiente tarea es **SP02-T17: cerrar las migraciones y sus límites**, con evidencia de instalación desde cero y segunda aplicación sin cambios; SP02 y WI05 conservan su cierre pendiente hasta cumplir ese criterio.
