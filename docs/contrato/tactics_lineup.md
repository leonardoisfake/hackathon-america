[Volver al índice](README.md)

# `tactics_lineup`

## Resumen general

Los jugadores de cada evento Starting XI y Tactical Shift, con su posición y dorsal. De aquí salen las formaciones en juego.

- Grano y llave: Un jugador por evento táctico. Llave: (`match_id`, `index`, `player_id`).
- Quién la produce: 02_auxiliares.py (Lee)
- Columnas: 9
- Filas: 5,714 en los parquet crudos
- Fuente: Endpoint `events`, columna `tactics.lineup` (lista JSON).

Reglas principales:

- La lista se explota con una fila por jugador.
- `tactics_formation` es entero (por ejemplo 4231).
- Las formaciones se leen de `tactics_formation`; no hay tabla aparte.
- Sale de los eventos crudos (`data/raw/parquet/events__*.parquet`) filtrados a los `match_id` de `data/interim/partidos.parquet`, como pide C18, y se une a `eventos` por (`match_id`, `index`).

Decisiones que la afectan:

| # | decisión | default vigente | quién decide | fecha límite |
|---|---|---|---|---|
| C8 | Tarjetas y formaciones de lineups | Se cierra sin tablas nuevas: las formaciones salen de `tactics_formation` (eventos Starting XI y Tactical Shift) y las tarjetas de `foul_committed_card_*` y `bad_behaviour_card_*`, que ya están en `eventos` | RESUELTA (Yordi) | resuelta |
| C18 | Partidos que no pasan los filtros de calidad (plan 7.1) | Se excluyen y se reportan en `data/interim/partidos_excluidos.csv`; ya no detienen la corrida. Los filtros son `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. Todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga` traen solo los `match_id` de `partidos`. Las 4 tablas de `02_auxiliares.py` (`related_events`, `tactics_lineup`, `defensive_responsibility` y `shot_freeze_frame`) salen de los eventos crudos (`data/raw/parquet/events__*.parquet`) porque `data/interim/eventos.parquet` no trae sus listas; se filtran a los `match_id` de `data/interim/partidos.parquet` y se unen a `eventos` por (`match_id`, `index`) | RESUELTA (Yordi) | resuelta |

## Columnas (9)

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `index` | Int64 | Índice del evento Starting XI o Tactical Shift. | `index` | Llave junto con match_id. |
| `team_id` | Int64 | Equipo del evento táctico. | `team.id` | Int64. |
| `tactics_formation` | Int64 | Formación (por ejemplo 4231). | `tactics.formation` | Float por los vacíos -> Int64. |
| `jersey_number` | Int64 | Dorsal. | `tactics.lineup[].jersey_number` | explode de la lista JSON. |
| `player_id` | Int64 | Jugador. | `tactics.lineup[].player.id` | explode. |
| `player_name` | string | Nombre del jugador. | `tactics.lineup[].player.name` | strip. |
| `position_id` | Int64 | Posición (1 a 25). | `tactics.lineup[].position.id` | Int64. |
| `position_name` | category | Nombre de la posición. | `tactics.lineup[].position.name` | strip. |
