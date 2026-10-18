[Volver al índice](README.md)

# `posiciones`

## Resumen general

Los tramos de posición de cada jugador en el partido: dónde jugó, desde y hasta qué momento, y por qué empezó y terminó cada tramo. Con ella se calculan minutos y se detectan cambios y rojas.

- Grano y llave: Un tramo por fila. Llave: (`match_id`, `team_id`, `player_id`, `posicion_idx`).
- Quién la produce: 02_limpieza.py (Yordi), con acuerdo de Lee
- Columnas: 14
- Filas: 4,150 en los parquet crudos
- Fuente: Endpoint `lineups` (`data/raw/parquet/lineups.parquet`), lista `positions` dentro de cada jugador de `lineup`.

Reglas principales:

- `to` nulo significa que el jugador siguió hasta el silbatazo final: 1,976 de 4,150 tramos (47.6%), todos con `end_reason` = Final Whistle y último tramo del jugador. No se imputa un minuto.
- `from` y `to` son texto HH:MM:SS.mmm con el reloj corrido del partido: el segundo tiempo empieza en 00:45:00.000. `to − from` es la duración solo si `from_period` = `to_period`; en los 1,227 tramos que cruzan de periodo la duración se suma por periodo, con el evento Half End de `eventos` (detalle en la regla de `to`). El inicio de los periodos 3 y 4 (tiempo extra) no está verificado, y la regla da solo una cota. `from_period` y `to_period` son enteros (`to_period` con nulos).
- `posicion_idx` cuenta los tramos del jugador desde 0.
- `end_reason` sirve para detectar rojas.
- 1,003 de los 3,820 jugadores de la cédula no tienen tramos en `posiciones` ni fila en `player_match_stats`: son la banca que no entró. No aparecen en esta tabla.

Decisiones que la afectan:

| # | decisión | default vigente | quién decide | fecha límite |
|---|---|---|---|---|
| C9 | `posiciones.to` nulo (47.6%) | El nulo significa que el jugador siguió hasta el silbatazo final; no se imputa un minuto. Verificado con los 91 partidos: 1,976 de 4,150 tramos tienen `to` nulo, todos con `end_reason` = Final Whistle y último tramo del jugador | RESUELTA (usuario) | resuelta |
| C17 | Quién produce `posiciones` | `02_limpieza.py` (Yordi), con acuerdo de Lee | RESUELTA (usuario) | resuelta |
| C18 | Partidos que no pasan los filtros de calidad (plan 7.1) | Se excluyen y se reportan en `data/interim/partidos_excluidos.csv`; ya no detienen la corrida. Los filtros son `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. Todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga` traen solo los `match_id` de `partidos`. Las 4 tablas de `02_auxiliares.py` (`related_events`, `tactics_lineup`, `defensive_responsibility` y `shot_freeze_frame`) deben salir de `data/interim/eventos.parquet`, y no de los crudos, para traer solo los `match_id` de `partidos` | RESUELTA (usuario) | resuelta |

## Columnas (14)

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `team_id` | Int64 | Equipo. | `team_id` | Llave. |
| `player_id` | Int64 | Jugador. | `lineup[].player_id` | Llave. |
| `posicion_idx` | Int64 | Orden del tramo del jugador en el partido. | posición en `lineup[].positions` | explode con contador desde 0. |
| `position_id` | Int64 | Número de la posición (1 a 25; ver tabla de valores). | `lineup[].positions[].position_id` | Int64. |
| `position` | category | Nombre de la posición (portero, lateral, mediocampista, delantero, etc.). | `lineup[].positions[].position` | strip. |
| `from` | string | Inicio del tramo: texto HH:MM:SS.mmm, reloj corrido del partido (el segundo tiempo empieza en 00:45:00.000). `to − from` es la duración solo si `from_period` = `to_period`; si no, ver la regla. | `lineup[].positions[].from` | Texto HH:MM:SS.mmm, reloj corrido del partido: el segundo tiempo empieza en 00:45:00.000 aunque el primero haya terminado más tarde. `to − from` es la duración solo si `from_period` = `to_period`. 1,227 de los 2,174 tramos con `to` cruzan de periodo y en 2 de ellos `to` es menor que `from`. Si el tramo cruza de periodo, la duración se suma por periodo: el fin de cada periodo en el reloj corrido es el inicio de ese periodo más el `timestamp` del evento Half End de ese periodo en `eventos` (el `timestamp` se reinicia en cada periodo). Inicio verificado de los periodos 1 y 2 (mínimo de `from` por `from_period`): periodo 1 en 00:00:00.000 y periodo 2 en 00:45:00.000. Los periodos 3 y 4 (tiempo extra) no tienen inicio verificado, porque ningún tramo empieza al arrancarlos: 1 partido tiene tiempo extra y 17 tramos tocan esos periodos. Los datos son consistentes con inicios en 01:30:00.000 y 01:45:00.000, pero eso no está comprobado; el mínimo observado de `from` es 01:38:00.001 en el periodo 3 y 01:47:14.520 en el periodo 4 y solo sirve como cota, no como inicio. Verificado en los 4,150 tramos: todos los valores no nulos tienen el formato, el mínimo de `from` con `from_period` = 2 es exactamente 00:45:00.000 y el máximo de `to` es 02:01:11.394. |
| `to` | string | Fin del tramo: texto HH:MM:SS.mmm, reloj corrido del partido (el segundo tiempo empieza en 00:45:00.000). `to − from` es la duración solo si `from_period` = `to_period`; si no, ver la regla. | `lineup[].positions[].to` | Texto HH:MM:SS.mmm, reloj corrido del partido: el segundo tiempo empieza en 00:45:00.000 aunque el primero haya terminado más tarde. `to − from` es la duración solo si `from_period` = `to_period`. 1,227 de los 2,174 tramos con `to` cruzan de periodo y en 2 de ellos `to` es menor que `from`. Si el tramo cruza de periodo, la duración se suma por periodo: el fin de cada periodo en el reloj corrido es el inicio de ese periodo más el `timestamp` del evento Half End de ese periodo en `eventos` (el `timestamp` se reinicia en cada periodo). Inicio verificado de los periodos 1 y 2 (mínimo de `from` por `from_period`): periodo 1 en 00:00:00.000 y periodo 2 en 00:45:00.000. Los periodos 3 y 4 (tiempo extra) no tienen inicio verificado, porque ningún tramo empieza al arrancarlos: 1 partido tiene tiempo extra y 17 tramos tocan esos periodos. Los datos son consistentes con inicios en 01:30:00.000 y 01:45:00.000, pero eso no está comprobado; el mínimo observado de `from` es 01:38:00.001 en el periodo 3 y 01:47:14.520 en el periodo 4 y solo sirve como cota, no como inicio. Verificado en los 4,150 tramos: todos los valores no nulos tienen el formato, el mínimo de `from` con `from_period` = 2 es exactamente 00:45:00.000 y el máximo de `to` es 02:01:11.394. Nulo en 1,976 de 4,150 tramos (47.6%): el jugador siguió hasta el silbatazo final (end_reason = Final Whistle, último tramo del jugador). No se imputa un minuto; para calcular la duración, el fin es el Half End del último periodo jugado (C9; el periodo 5 son penales). |
| `from_period` | Int64 | Tiempo del partido en que empezó en esa posición (1 = primer tiempo, 2 = segundo, 3 y 4 = tiempos extra, 5 = penales). | `lineup[].positions[].from_period` | Int64. |
| `to_period` | Int64 | Tiempo del partido en que terminó en esa posición. | `lineup[].positions[].to_period` | Float con vacíos -> Int64. |
| `start_reason` | category | Por qué empezó en esa posición: once inicial, cambio, ajuste táctico, etc. | `lineup[].positions[].start_reason` | strip. |
| `end_reason` | category | Por qué terminó: silbatazo final, cambio, tarjeta roja, ajuste táctico, etc. | `lineup[].positions[].end_reason` | strip; sirve para detectar rojas. |
| `counterpart_id` | Int64 | En un cambio, id del jugador que entró o salió en su lugar. | `lineup[].positions[].counterpart_id` | Float con vacíos -> Int64. |
| `counterpart_name` | string | En un cambio, nombre del jugador que entró o salió en su lugar. | `lineup[].positions[].counterpart_name` | strip. |
