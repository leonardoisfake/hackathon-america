[Volver al índice](README.md)

# 1. Definiciones y supuestos

## Resumen general

Las definiciones que usa el equipo en todo el análisis y los supuestos que deciden cuándo una secuencia cuenta como un suceso. Al final, una tabla indica qué ficha de Lee implementa cada definición.

## Definiciones

- **Posesión:** tramo en el que un equipo controla el balón. Empieza otra cuando un equipo demuestra control, aunque sea el mismo equipo tras un saque de banda.
- **Contrapresión (`counterpress`):** presión dentro de los 5 segundos posteriores a perder el balón en juego abierto.
- **Contragolpe (`play_pattern` 6):** posesión que nace de una pérdida rival en juego abierto fuera del último tercio propio, al menos 75% directa y con avance de al menos 18 yardas.
- **Bajo presión (`under_pressure`):** evento que ocurre durante la presión de un rival.
- **Fases de juego (v11):** `is_transition`, `is_controlled_possession`, `possession_directness`, `control_degree` y `location_bucket`. Solo aplican en juego abierto.
- **Salto de líneas:** un pase que genera un espacio defensivo que el equipo puede aprovechar. Los equipos se manejan como 3 bloques horizontales: delanteros, mediocampistas y defensas. Cualquier pase acertado que cruce uno de estos tres bloques se considera un salto de líneas.
- **Fase de presión:** conjunto de presiones sobre el rival en un periodo corto de tiempo para buscar recuperar el balón.
- **Zona de presión alta:** toda presión dentro de los últimos 40 metros de la cancha rival.
- **Fase de inicio:** toda salida del primer tercio, evitando presiones en esa zona.
- **Fase de construcción:** se genera en el segundo tercio de la cancha. Son todos los pases que se hacen buscando llegar a una secuencia ofensiva.
- **Secuencia ofensiva:** toda secuencia de pases que cruce al tercio final o termine en tiro.
- **Transición:** puede ser defensiva (cómo actúa el equipo los primeros 5 segundos tras perder el balón) u ofensiva (cómo actúa los primeros 5 segundos tras ganarlo).

## Supuestos explícitos

- **Umbral mínimo de pases para considerar una posesión:** si no es una jugada a balón parado, se exigen al menos tres pases para descartar rebotes, o menos si hay un tiro. Un toque del rival sin dirección no cuenta como cambio de posesión.
- **Secuencia ofensiva:** para medir qué tan efectiva fue una secuencia se puede usar el xG.
- **Fase de presión:** 3 intentos de recuperación o presiones en menos de 10 segundos. Quedó fijo en las [métricas finales](05_metricas_finales.md).

## Dónde se usan

Las fichas están en `especificaciones_metricas/`, de Lee.

| Definición | Ficha que la implementa | Nota |
| :--- | :--- | :--- |
| Posesión y umbral mínimo de pases | [B1](../especificaciones_metricas/01_objetos_base.md#b1-posesión-válida) | `03_contexto.py` la calcula en `contexto_posesiones` (`is_valid_possession`) |
| Secuencia ofensiva | [B2](../especificaciones_metricas/01_objetos_base.md#b2-secuencia-ofensiva) | |
| Fase de inicio | [B3](../especificaciones_metricas/01_objetos_base.md#b3-fase-de-inicio) | |
| Fase de construcción | [B4](../especificaciones_metricas/01_objetos_base.md#b4-fase-de-construcción) | |
| Fase de presión | [B5](../especificaciones_metricas/01_objetos_base.md#b5-fase-de-presión) | |
| Contragolpe | [B6](../especificaciones_metricas/01_objetos_base.md#b6-contragolpe) | |
| Salto de líneas | [I4](../especificaciones_metricas/04_inicio_y_construccion.md#i4-salto_de_lineas-definición-del-equipo) | Lee dejó abierto cómo se miden los bloques (su punto por confirmar 3) |
| Zona de presión alta | [D1](../especificaciones_metricas/05_presion_y_defensa.md#d1-press_height-y-high_press) | Las [métricas finales](05_metricas_finales.md) fijan 40 metros (x ≥ 76.26 yardas). Pablo calcula las dos; la que vale es `presiones_altas_40m` |
| Contrapresión | [D3](../especificaciones_metricas/05_presion_y_defensa.md#d3-counterpress-y-regain_5s) | |
| Transición | [D5](../especificaciones_metricas/05_presion_y_defensa.md#d5-transition) | |
