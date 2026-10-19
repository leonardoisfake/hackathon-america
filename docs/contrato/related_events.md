[Volver al índice](README.md)

# `related_events`

## Resumen general

Una fila por cada relación entre dos eventos, por ejemplo un pase y su recepción.

- Grano y llave: Una relación por fila. Llave: (`match_id`, `index`, `related_id`).
- Quién la produce: 02_auxiliares.py (Lee)
- Columnas: 5
- Filas: 606,902 en los parquet crudos
- Fuente: Endpoint `events`, columna `related_events` (lista JSON de UUID).

Reglas principales:

- La lista se explota con una fila por relación.
- `related_index` sale de unir `related_id` contra `id` dentro del partido; queda nulo si no se encuentra.
- Debe salir de `data/interim/eventos.parquet` y no de los crudos, para traer solo los `match_id` de `partidos` (C18).

Decisiones que la afectan:

| # | decisión | default vigente | quién decide | fecha límite |
|---|---|---|---|---|
| C18 | Partidos que no pasan los filtros de calidad (plan 7.1) | Se excluyen y se reportan en `data/interim/partidos_excluidos.csv`; ya no detienen la corrida. Los filtros son `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. Todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga` traen solo los `match_id` de `partidos`. Las 4 tablas de `02_auxiliares.py` (`related_events`, `tactics_lineup`, `defensive_responsibility` y `shot_freeze_frame`) deben salir de `data/interim/eventos.parquet`, y no de los crudos, para traer solo los `match_id` de `partidos` | RESUELTA (Yordi) | resuelta |

## Columnas (5)

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `index` | Int64 | Índice del evento que declara la relación. | `index` del evento | Llave junto con match_id. |
| `id` | string | UUID del evento que declara la relación. | `id` | strip. |
| `related_id` | string | UUID del evento relacionado. | `related_events` | explode de la lista JSON; una fila por relación. |
| `related_index` | Int64 | Índice del evento relacionado en el mismo partido. | `related_events` + `id` | Join de related_id contra id dentro del partido; nulo si no se encuentra. |
