# Framework analítico - Hackathon ITAM + Club América

Versión del 20 de octubre de 2026. Autor: Pato (narrativa y coordinación). Fuentes: `K-Pumas.pdf` (framework, restricciones y decisiones de limpieza), `K-Pumas 2.pdf` (métricas finales) y `scripts/03_jugadores.py`.

## Resumen general

Reúne lo que el equipo acordó para analizar a Jardine con el Club América (91 partidos de Liga MX, datos StatsBomb): las definiciones y los supuestos del análisis, sus límites, las decisiones que se tomaron al limpiar los datos y el bloque de jugadores. Las fichas de Lee en `especificaciones_metricas/` toman sus definiciones base de este framework, y el HTML final usa estas mismas palabras.

Cada archivo empieza con un resumen y se puede leer por separado. El [índice](#índice) lleva a cada uno.

## Qué cubre

El framework sigue el reparto de la sección 14 del plan de trabajo.

| Fase del plan | Tarea | Archivo |
| :--- | :--- | :--- |
| 1. Decisiones y datos (16 y 17 oct) | Framework de 1 página: definiciones, umbrales propuestos y límites del análisis | [01](01_definiciones_y_supuestos.md) y [02](02_restricciones_y_riesgos.md) |
| 2. Limpieza (18 oct) | Tabla de decisiones de limpieza, que después se convierte en la sección de metodología del HTML | [03](03_decisiones_de_limpieza.md) |
| 3. Transformación (19 oct) | `role_group`, minutos, formación por periodo e impacto de las sustituciones | [04](04_jugadores.md) |
| 3. Transformación (19 oct) | Definición final de cada métrica (qué mide, fórmula, unidad y umbral), para que el HTML y el video usen las mismas palabras | [05](05_metricas_finales.md) |

## Índice

| Sección | Qué contiene | Archivo |
| :--- | :--- | :--- |
| 1. Definiciones y supuestos | Las 12 definiciones del equipo (posesión, secuencia ofensiva, transición, fase de presión...) y los 3 supuestos explícitos | [01_definiciones_y_supuestos.md](01_definiciones_y_supuestos.md) |
| 2. Restricciones y riesgos | Lo que el análisis no puede afirmar y cómo se reporta | [02_restricciones_y_riesgos.md](02_restricciones_y_riesgos.md) |
| 3. Decisiones de limpieza | Cada decisión de `02_limpieza.py` con su problema, acción y justificación, en 9 secciones | [03_decisiones_de_limpieza.md](03_decisiones_de_limpieza.md) |
| 4. Jugadores | Fichas J1, J2a y J2b de `scripts/03_jugadores.py`: cómo se corre, qué calcula, salidas y decisiones por confirmar | [04_jugadores.md](04_jugadores.md) |
| 5. Métricas finales | Las 8 definiciones finales (posesión válida, transición, secuencia ofensiva, fases de construcción, inicio y presión, zona de presión alta y salto de líneas) y dónde se calcula cada una | [05_metricas_finales.md](05_metricas_finales.md) |
