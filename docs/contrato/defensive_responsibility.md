[Volver al índice](README.md)

# `defensive_responsibility`

## Resumen general

La probabilidad de responsabilidad defensiva que StatsBomb asigna a cada jugador en cada evento.

- Grano y llave: Un jugador por evento. Llave: (`match_id`, `index`, `player_id`).
- Quién la produce: 02_auxiliares.py (Lee)
- Columnas: 6
- Filas: 1,794,080 en los parquet crudos
- Fuente: Endpoint `events`, columna `defensive_responsibility.players` (lista JSON).

Reglas principales:

- La lista se explota con una fila por jugador.
- `probability_sum` y `categories` se quedan en `eventos`; `categories` como texto JSON.
- `interception_like_probability` y `pressure_like_probability` tienen nulo legítimo y no se imputan.
- Debe salir de `data/interim/eventos.parquet` y no de los crudos, para traer solo los `match_id` de `partidos` (C18).

Decisiones que la afectan:

| # | decisión | default vigente | quién decide | fecha límite |
|---|---|---|---|---|
| C7 | `defensive_responsibility.categories` | Texto JSON en `eventos`; no se explota | Lee | vigente por defecto; confirmar antes del lun 19 |
| C18 | Partidos que no pasan los filtros de calidad (plan 7.1) | Se excluyen y se reportan en `data/interim/partidos_excluidos.csv`; ya no detienen la corrida. Los filtros son `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. Todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga` traen solo los `match_id` de `partidos`. Las 4 tablas de `02_auxiliares.py` (`related_events`, `tactics_lineup`, `defensive_responsibility` y `shot_freeze_frame`) deben salir de `data/interim/eventos.parquet`, y no de los crudos, para traer solo los `match_id` de `partidos` | RESUELTA (Yordi) | resuelta |

## Columnas (6)

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `index` | Int64 | Índice del evento. | `index` | Llave junto con match_id. |
| `player_id` | Int64 | Jugador con responsabilidad defensiva. | `defensive_responsibility.players[].player_id` | explode de la lista JSON. |
| `probability` | float64 | Probabilidad de responsabilidad defensiva del jugador. | `defensive_responsibility.players[].probability` | Sin cambios. |
| `interception_like_probability` | float64 | Probabilidad de acción tipo intercepción. | `defensive_responsibility.players[].interception_like_probability` | Nulo legítimo; no imputar. |
| `pressure_like_probability` | float64 | Probabilidad de acción tipo presión. | `defensive_responsibility.players[].pressure_like_probability` | Nulo legítimo; no imputar. |
