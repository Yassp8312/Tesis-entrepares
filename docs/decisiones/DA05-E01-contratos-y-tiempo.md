# DA05 E01 Interfaces propietarias y tiempo de operación

Fecha: 2 de noviembre de 2026; cierre el 3 de noviembre. Concreción de DA01, DA05, DA12 y DL20 en SP01-T05.

## Decisión

Delimitar `commands`, `selectors` y `contracts` en los diez módulos. Las escrituras pertenecen al propietario y la coordinación al caso de aplicación. La primera interfaz ejecutable usa el modelo de cuenta existente: creación ordinaria y lectura mínima de su estado técnico. Los datos intercambiados no son instancias ORM. M02–M10 incorporarán funciones y tipos durante sus incrementos; esta preparación no declara completos sus contratos funcionales.

`core` conserva solo utilidades técnicas de biblioteca estándar: generación de UUID, conversión explícita de instantes conscientes de zona, protocolo de reloj y contexto de correlación. La capa de entrada inyecta el reloj y crea la correlación. Esta viaja explícitamente entre llamadas y luego se vinculará con el identificador del error HTTP y de la auditoría.

El tiempo no queda congelado en un contexto de solicitud. `OperationContext.now()` vuelve a consultar el reloj y normaliza a UTC, para que el coordinador pueda evaluar condiciones en el momento protegido. Se conserva la posibilidad de reutilizar un instante dentro de una decisión concreta. Las fechas automáticas de modelos y base permanecen como están definidas; no se altera su mecanismo mediante una sustitución global.

## Motivación y límites

Las llamadas internas permiten compartir transacción en el monolito. Las interfaces de propietario hacen visible qué componente lee o modifica cada registro. La proyección mínima de M01 evita entregar credenciales y banderas de privilegio a consumidores que solo necesitan conocer su identidad y habilitación.

La inyección temporal permite ensayar instantes anteriores, iguales y posteriores a un plazo sin esperas reales. La evaluación completa de una oportunidad o una concesión necesita sus reglas y registros; no se implementa en `core`. Las decisiones pendientes Q03 y Q08 no se resuelven mediante una duración constante o una aritmética de fechas genérica.

Las comprobaciones de importaciones cubren código estático, rutas relativas y nombres importados desde un paquete. Las entradas CLI permiten `application`; los paquetes de negocio lo rechazan. La importación de modelos de otro propietario está restringida y todavía no tiene excepciones de lectura. Esta evidencia parcial de AT01 no sustituye las pruebas de escritura, transacción y autorización de los casos reales.

## Referencias

- [Guía de interfaces y reloj](../contratos-y-reloj.md), con contratos implementados, comandos y fuentes técnicas.
- [Base documental](../base-documental.json): DA01, DA05, DA12; DL18, DL20; AT01 y preparación temporal de AT09.
