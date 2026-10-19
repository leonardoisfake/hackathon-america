[Volver al índice](README.md)

# `shot_freeze_frame`

## Resumen general

Los jugadores visibles en el momento de cada tiro, con su posición en la cancha. Sirve para ver quién estaba en la línea de tiro y dónde estaba el portero.

- Grano y llave: Un jugador visible por tiro. Llave: (`match_id`, `index`, `jugador_idx`).
- Quién la produce: 02_auxiliares.py (Lee)
- Columnas: 10
- Filas: 30,057 en los parquet crudos
- Fuente: Endpoint `events`, columna `shot.freeze_frame` (lista JSON).

Reglas principales:

- La lista se explota con un contador `jugador_idx` desde 0.
- `x` e `y` salen de `location`.
- No estaba en la lista original de tareas; se agregó porque el plan 7.3.7 pide explotar `shot.freeze_frame`.
- Debe salir de `data/interim/eventos.parquet` y no de los crudos, para traer solo los `match_id` de `partidos` (C18).

Decisiones que la afectan:

| # | decisión | default vigente | quién decide | fecha límite |
|---|---|---|---|---|
| C1 | Unidad de distancia | Yardas (nativas de StatsBomb; 1 yarda = 0.9144 m) | RESUELTA (Yordi) | resuelta |
| C4 | Tabla extra `shot_freeze_frame` | Se incluye; la produce `02_auxiliares.py` | Lee | vigente por defecto; confirmar antes del lun 19 |
| C18 | Partidos que no pasan los filtros de calidad (plan 7.1) | Se excluyen y se reportan en `data/interim/partidos_excluidos.csv`; ya no detienen la corrida. Los filtros son `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. Todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga` traen solo los `match_id` de `partidos`. Las 4 tablas de `02_auxiliares.py` (`related_events`, `tactics_lineup`, `defensive_responsibility` y `shot_freeze_frame`) deben salir de `data/interim/eventos.parquet`, y no de los crudos, para traer solo los `match_id` de `partidos` | RESUELTA (Yordi) | resuelta |

## Columnas (10)

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `index` | Int64 | Índice del tiro. | `index` | Llave junto con match_id. |
| `jugador_idx` | Int64 | Orden del jugador dentro del freeze frame. | posición en la lista | explode con contador desde 0. |
| `teammate` | boolean | El jugador es compañero del tirador. | `shot.freeze_frame[].teammate` | Sin cambios. |
| `player_id` | Int64 | Jugador. | `shot.freeze_frame[].player.id` | Int64. |
| `player_name` | string | Nombre. | `shot.freeze_frame[].player.name` | strip. |
| `position_id` | Int64 | Posición. | `shot.freeze_frame[].position.id` | Int64. |
| `position_name` | category | Nombre de la posición. | `shot.freeze_frame[].position.name` | strip. |
| `x` | float64 | Coordenada x. | `shot.freeze_frame[].location` | Se separa [x, y]. |
| `y` | float64 | Coordenada y. | `shot.freeze_frame[].location` | Se separa [x, y]. |
