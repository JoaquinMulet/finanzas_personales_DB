## **Informe Técnico: Especificación de Arquitectura de Base de Datos v2.1**

**Documento ID:** DB-ARCH-SPEC-2.1
**Fecha:** 25 de agosto de 2025
**Autor:** Gemini AI
**Estado:** Final
**Destinatarios:** Equipo de Desarrollo de Base de Datos y Backend

### **1. Introducción**

Este documento proporciona la especificación técnica completa para la implementación de la base de datos de la aplicación de finanzas personales. La arquitectura designada como **v2.1** está diseñada para ofrecer máxima integridad de datos, escalabilidad a largo plazo y una flexibilidad que permita modelar escenarios financieros complejos del mundo real.

El cumplimiento estricto de esta especificación es fundamental para garantizar la robustez, seguridad y rendimiento de la aplicación.

### **2. Principios Fundamentales de la Arquitectura**

La base de datos se rige por los siguientes principios no negociables:

* **Integridad de Datos (ACID):** Todas las operaciones que modifiquen el estado financiero (ej. una transferencia) deben estar encapsuladas en transacciones de base de datos para garantizar Atomicidad, Consistencia, Aislamiento y Durabilidad. No hay margen para estados financieros inconsistentes.
* **Normalización (3NF):** El esquema está normalizado hasta la Tercera Forma Normal para eliminar la redundancia de datos. Cada pieza de información (como el nombre de una categoría) se almacena una sola vez, asegurando consistencia y eficiencia en las actualizaciones.
* **Inmutabilidad del Libro Contable:** Las transacciones financieras son hechos históricos. Este principio se implementa en la tabla `Transactions` mediante un patrón de "solo-añadir" (`append-only`). **Las transacciones nunca se eliminan (`DELETE`) o se modifican (`UPDATE`) directamente**. En su lugar, se anulan o corrigen creando nuevos registros, preservando un rastro de auditoría perfecto.
* **Uso de UUIDs:** Las claves primarias para entidades principales (`Accounts`, `Transactions`, etc.) serán de tipo `UUID`. Esto previene la enumeración de recursos por parte de atacantes, facilita la federación de datos en futuras arquitecturas distribuidas y evita conflictos en operaciones de inserción masiva.

---

### **3. Esquema Detallado de Tablas**

A continuación se detalla la estructura y el propósito de cada tabla en el sistema.

#### **Sección 3.1: Entidades de Definición (Los "Sustantivos")**

Estas tablas almacenan la configuración y los elementos que el usuario define para organizar sus finanzas.

##### **Tabla: `Accounts`**
* **Objetivo:** Representa cualquier contenedor financiero, ya sea un activo (dinero que se tiene) o un pasivo (dinero que se debe). Es la entidad fundamental para calcular el patrimonio neto del usuario. Cada movimiento financiero debe estar asociado a una cuenta.
* **Instrucciones de Uso:** Al crear una cuenta, se debe especificar su `account_type` correctamente, ya que esto dicta cómo su saldo contribuye al patrimonio total. El `initial_balance` sirve como el punto de partida para todos los cálculos de saldo posteriores.

| Nombre del Campo | Tipo de Dato | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- |
| `account_id` | `UUID` | `PRIMARY KEY` | Identificador único de la cuenta. |
| `account_name` | `VARCHAR(255)` | `UNIQUE`, `NOT NULL` | Nombre descriptivo (ej. "Tarjeta de Crédito Santander"). |
| `account_type` | `ENUM('Asset', 'Liability')`| `NOT NULL` | Clasificación fundamental: Activo o Pasivo. |
| `currency_code` | `VARCHAR(3)` | `NOT NULL` | Código de divisa ISO 4217 (ej. "CLP", "USD"). |
| `initial_balance` | `DECIMAL(19, 4)` | `NOT NULL` | Saldo inicial en la divisa de la cuenta. |

##### **Tabla: `Categories`**
* **Objetivo:** Crear una taxonomía jerárquica para clasificar cada transacción. Esta tabla es el motor del análisis de gastos e ingresos, permitiendo al usuario entender a dónde va su dinero.
* **Instrucciones de Uso:** El campo `parent_category_id` permite anidar categorías (ej. "Transporte" > "Gasolina"). Si es `NULL`, es una categoría de nivel superior. Los campos de clasificación (`purpose_type`, `nature_type`) son cruciales para análisis avanzados (ej. "Necesidades vs. Deseos").

| Nombre del Campo | Tipo de Dato | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- |
| `category_id` | `INT` | `PRIMARY KEY`, `AUTO_INCREMENT`| Identificador único. |
| `category_name` | `VARCHAR(255)` | `UNIQUE`, `NOT NULL` | Nombre de la categoría (ej. "Supermercado"). |
| `parent_category_id` | `INT` | `FOREIGN KEY (Categories.category_id)` | Clave auto-referenciada para la jerarquía. |
| `purpose_type` | `ENUM('Need', 'Want', 'Savings/Goal')` | | Propósito del gasto/ingreso. |
| `nature_type` | `ENUM('Fixed', 'Variable')` | | Naturaleza del gasto/ingreso. |

##### **Tabla: `Merchants`**
* **Objetivo:** Normalizar la información de los comercios. Evita tener múltiples variaciones del mismo nombre (ej. "Lider", "lider", "Lider Supermercado") y permite asociar un comercio a una categoría por defecto para agilizar la clasificación.
* **Instrucciones de Uso:** Antes de crear una transacción, la aplicación debe buscar si el `merchant_name` ya existe. Si no, debe crearlo. Esto enriquece los datos y permite análisis por comercio.

| Nombre del Campo | Tipo de Dato | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- |
| `merchant_id` | `UUID` | `PRIMARY KEY` | Identificador único del comercio. |
| `merchant_name` | `VARCHAR(255)` | `UNIQUE`, `NOT NULL` | Nombre canónico del comercio (ej. "Jumbo"). |
| `default_category_id`| `INT` | `FOREIGN KEY (Categories.category_id)` | Categoría sugerida al registrar un gasto aquí. |

##### **Tabla: `Tags`**
* **Objetivo:** Proporcionar un sistema de etiquetado flexible y multidimensional. A diferencia de las categorías (que son una jerarquía estricta), los tags permiten agrupar transacciones de diferentes categorías bajo un mismo evento o concepto (ej. "Vacaciones 2025", "Proyecto Casa").
* **Instrucciones de Uso:** Los tags se conectan a las transacciones a través de la tabla de unión `Transaction_Tags`.

| Nombre del Campo | Tipo de Dato | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- |
| `tag_id` | `INT` | `PRIMARY KEY`, `AUTO_INCREMENT`| Identificador único. |
| `tag_name` | `VARCHAR(255)` | `UNIQUE`, `NOT NULL` | Nombre de la etiqueta. |

---

#### **Sección 3.2: Entidades de Eventos (Los "Verbos")**

Estas tablas registran las acciones y hechos financieros. Son el corazón del sistema.

##### **Tabla: `Transactions`**
* **Objetivo:** El libro diario contable inmutable. Cada registro es un evento financiero atómico que afecta a una cuenta. Esta tabla está diseñada para auditoría y trazabilidad completa.
* **Instrucciones de Uso CRÍTICAS:**
    * **Creación:** Se crea un nuevo registro con `status = 'ACTIVE'`.
    * **"Eliminación":** NUNCA usar `DELETE`. Se actualiza el `status` del registro a `'VOID'`. El registro permanece pero se excluye de los cálculos.
    * **"Edición":** NUNCA usar `UPDATE` para cambiar los detalles financieros. El proceso es:
        1.  Actualizar el `status` del registro original a `'SUPERSEDED'`.
        2.  Crear un **nuevo** registro con los datos corregidos y `status = 'ACTIVE'`.
        3.  En el nuevo registro, el campo `revises_transaction_id` debe apuntar al `transaction_id` del registro original.

| Nombre del Campo | Tipo de Dato | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- |
| `transaction_id` | `UUID` | `PRIMARY KEY` | Identificador único del evento. |
| `account_id` | `UUID` | `FOREIGN KEY (Accounts.account_id)`, `NOT NULL` | Cuenta afectada por la transacción. |
| `merchant_id` | `UUID` | `FOREIGN KEY (Merchants.merchant_id)`| Comercio involucrado (opcional). |
| `category_id` | `INT` | `FOREIGN KEY (Categories.category_id)` | **NULLEABLE**. Si es `NULL`, la info está en `Transaction_Splits`. |
| `base_currency_amount`| `DECIMAL(19, 4)` | `NOT NULL` | Monto en la divisa base del usuario. Negativo para egresos. |
| `original_amount` | `DECIMAL(19, 4)` | `NOT NULL` | Monto en la divisa original de la transacción. |
| `original_currency_code`| `VARCHAR(3)`| `NOT NULL` | Divisa original de la transacción. |
| `transaction_date` | `TIMESTAMP WITH TIME ZONE`| `NOT NULL`, `INDEX` | Fecha y hora exactas del evento. |
| `status` | `ENUM('ACTIVE', 'VOID', 'SUPERSEDED')` | `NOT NULL`, `DEFAULT 'ACTIVE'`, `INDEX` | Estado del ciclo de vida de la transacción. |
| `revises_transaction_id` | `UUID` | `FOREIGN KEY (Transactions.transaction_id)` | Apunta a la transacción que este registro corrige. |
| `related_transaction_id`| `UUID` | `FOREIGN KEY (Transactions.transaction_id)` | Para vincular las dos partes de una transferencia. |

##### **Tabla: `Transaction_Splits`**
* **Objetivo:** Permitir que una única transacción (ej. una compra de supermercado) se divida en múltiples categorías (ej. "Comida", "Limpieza", "Farmacia").
* **Instrucciones de Uso:** Si una transacción se divide, su registro en `Transactions` tendrá `category_id = NULL`. Se crearán múltiples registros en esta tabla, cada uno vinculado al `transaction_id` principal. La suma de los `amount` en los splits debe ser igual al `base_currency_amount` de la transacción madre.

| Nombre del Campo | Tipo de Dato | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- |
| `split_id` | `UUID` | `PRIMARY KEY` | Identificador único de la división. |
| `transaction_id` | `UUID` | `FOREIGN KEY (Transactions.transaction_id)`, `NOT NULL` | Transacción "madre" a la que pertenece. |
| `category_id` | `INT` | `FOREIGN KEY (Categories.category_id)`, `NOT NULL` | Categoría de esta porción del gasto. |
| `amount` | `DECIMAL(19, 4)` | `NOT NULL` | Monto de esta división. |

##### **Tabla: `Transaction_Tags`**
* **Objetivo:** Tabla de unión que implementa la relación muchos-a-muchos entre `Transactions` y `Tags`.
* **Instrucciones de Uso:** Para asociar una o más etiquetas a una transacción, se insertan registros aquí.

| Nombre del Campo | Tipo de Dato | Restricciones / Índices |
| :--- | :--- | :--- |
| `transaction_id` | `UUID` | `FOREIGN KEY (Transactions.transaction_id)` |
| `tag_id` | `INT` | `FOREIGN KEY (Tags.tag_id)` |
| `(transaction_id, tag_id)` | | `PRIMARY KEY` |

---

#### **Sección 3.3: Entidades de Seguimiento y Planificación (El "Futuro" y la "Riqueza")**

##### **Tabla: `Asset_Valuation_History`**
* **Objetivo:** Rastrear el valor de activos no líquidos (cuyo valor cambia sin una transacción explícita), como propiedades, vehículos o carteras de inversión. Es esencial para un cálculo preciso del patrimonio neto total.
* **Instrucciones de Uso:** Periódicamente, el usuario puede registrar una nueva valoración para un activo. Para calcular el valor actual de una cuenta de este tipo, la aplicación debe buscar la última entrada en esta tabla para el `account_id` correspondiente.

| Nombre del Campo | Tipo de Dato | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- |
| `valuation_id` | `UUID` | `PRIMARY KEY` | Identificador único de la valoración. |
| `account_id` | `UUID` | `FOREIGN KEY (Accounts.account_id)`, `NOT NULL` | El activo que está siendo valorado. |
| `valuation_date` | `DATE` | `NOT NULL`, `INDEX` | Fecha en que se registra el nuevo valor. |
| `value` | `DECIMAL(19, 4)` | `NOT NULL` | El valor de mercado del activo en esa fecha. |

##### **Tabla: `Goals` y `Goal_Accounts`**
* **Objetivo:** Permitir al usuario definir metas financieras y vincularlas directamente a las cuentas de ahorro destinadas a cumplirlas.
* **Instrucciones de Uso:** Se crea una meta en la tabla `Goals`. Luego, en `Goal_Accounts`, se asocia esa meta a una o más cuentas (`Accounts`) de tipo 'Asset'. El progreso de la meta (`current_amount`) ya no se actualiza manualmente; se calcula en tiempo real sumando los saldos de las cuentas vinculadas.

**Tabla: `Goals`**

| Nombre del Campo | Tipo de Dato | Restricciones / Índices | Descripción |
| :--- | :--- | :--- | :--- |
| `goal_id` | `UUID` | `PRIMARY KEY` | Identificador único de la meta. |
| `goal_name` | `VARCHAR(255)`| `NOT NULL` | Nombre de la meta (ej. "Pie para Departamento"). |
| `target_amount`| `DECIMAL(19, 4)`| `NOT NULL` | Monto objetivo a alcanzar. |
| `target_date` | `DATE` | | Fecha límite para la meta (opcional). |

**Tabla: `Goal_Accounts` (Unión)**

| Nombre del Campo | Tipo de Dato | Restricciones / Índices |
| :--- | :--- | :--- |
| `goal_id` | `UUID` | `FOREIGN KEY (Goals.goal_id)` |
| `account_id` | `UUID` | `FOREIGN KEY (Accounts.account_id)` |
| `(goal_id, account_id)` | | `PRIMARY KEY` |

---

#### **Sección 3.4: Entidades de Optimización**

##### **Tabla: `Monthly_Category_Summary`**
* **Objetivo:** Aumentar drásticamente el rendimiento de los reportes históricos. En lugar de escanear la tabla `Transactions` (que puede crecer a millones de registros), los dashboards consultarán esta tabla pre-calculada.
* **Instrucciones de Uso:** Un proceso nocturno (batch job) debe ejecutarse para agregar las transacciones del día anterior y actualizar esta tabla. La aplicación debe ser instruida para leer de esta tabla para cualquier reporte que involucre agregados mensuales por categoría.

| Nombre del Campo | Tipo de Dato | Restricciones / Índices |
| :--- | :--- | :--- |
| `year` | `INT` | `PRIMARY KEY` |
| `month` | `INT` | `PRIMARY KEY` |
| `category_id` | `INT` | `PRIMARY KEY`, `FOREIGN KEY` |
| `total_amount` | `DECIMAL(19, 4)`| `NOT NULL` |
| `transaction_count`| `INT` | `NOT NULL` |

### **4. Lógica de Negocio y Relaciones Clave**

* **Cálculo de Saldos:** El saldo de una cuenta líquida (`Asset` o `Liability`) se calcula dinámicamente: `initial_balance` + `SUM(base_currency_amount)` de todas las transacciones `ACTIVE` para esa cuenta. No debe almacenarse un campo `current_balance` en la tabla `Accounts` para evitar la denormalización y posibles inconsistencias.
* **Manejo de Transferencias:** Una transferencia entre cuentas propias debe generar **dos** registros en `Transactions`:
    1.  Un registro de egreso (`DEBIT`) en la cuenta de origen.
    2.  Un registro de ingreso (`CREDIT`) en la cuenta de destino.
    3.  Ambos registros deben apuntarse mutuamente usando el campo `related_transaction_id`. Esta operación debe estar envuelta en una transacción de base de datos para garantizar su atomicidad.

### **5. Recomendaciones de Implementación**

* **SGBD:** Se recomienda **PostgreSQL** por su robustez, conformidad con el estándar SQL, y tipos de datos avanzados como `UUID`, `ENUM` y `NUMERIC`.
* **Tipos Monetarios:** Utilizar exclusivamente `DECIMAL(19, 4)` o `NUMERIC` para todos los campos que almacenen valores monetarios. El uso de `FLOAT` o `DOUBLE` está estrictamente prohibido debido a su imprecisión.
* **Índices:** Además de las claves primarias y foráneas, se deben crear índices en columnas frecuentemente usadas en cláusulas `WHERE`, como `Transactions.transaction_date` y `Transactions.status`.