[Volver al índice](README.md)

# `alineaciones`

## Resumen general

La cédula de cada partido: titulares y banca de cada equipo, con los datos del jugador (nacimiento, estatura, peso, dorsal, país) y su rating HOPS.

- Grano y llave: Un jugador por equipo y partido. Llave: (`match_id`, `team_id`, `player_id`).
- Quién la produce: 02_limpieza.py (Yordi)
- Columnas: 21
- Filas: 3,820 en los parquet crudos
- Fuente: Endpoint `lineups` (`data/raw/parquet/lineups.parquet`), columna `lineup` (texto JSON con la lista de jugadores).

Reglas principales:

- `lineup` se explota con una fila por jugador.
- Las columnas `stats_*` vienen vacías en 26.2% de las filas, así que los goles y asistencias se recalculan desde `eventos`.
- Tienen nulos que no se imputan: `player_nickname` (4.2%), `skills_hops_*` (7.7%), `player_weight` (2.3%) y `player_height` (0.1%).
- 1,003 de los 3,820 jugadores de la cédula no tienen tramos en `posiciones` ni fila en `player_match_stats`: son la banca que no entró.

Decisiones que la afectan:

| # | decisión | default vigente | quién decide | fecha límite |
|---|---|---|---|---|
| C12 | `category` o `string` en nombres | Los `*_name` de equipos y catálogos, más `rival_nombre`, son category; las personas (`referee_name`, `player_name`, `pass_recipient_name`, `substitution_replacement_name`, `counterpart_name`, `entrenador_rival` y `player_nickname`) son string aunque terminen en `_name` | RESUELTA (Yordi) | resuelta |
| C18 | Partidos que no pasan los filtros de calidad (plan 7.1) | Se excluyen y se reportan en `data/interim/partidos_excluidos.csv`; ya no detienen la corrida. Los filtros son `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. Todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga` traen solo los `match_id` de `partidos`. Las 4 tablas de `02_auxiliares.py` (`related_events`, `tactics_lineup`, `defensive_responsibility` y `shot_freeze_frame`) salen de los eventos crudos (`data/raw/parquet/events__*.parquet`) porque `data/interim/eventos.parquet` no trae sus listas; se filtran a los `match_id` de `data/interim/partidos.parquet` y se unen a `eventos` por (`match_id`, `index`) | RESUELTA (Yordi) | resuelta |

## Columnas (21)

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `team_id` | Int64 | Equipo. | `team_id` | Llave junto con player_id. |
| `team_name` | category | Nombre del equipo. | `team_name` | strip. |
| `player_id` | Int64 | Id del jugador. | `lineup[].player_id` | explode de `lineup`. |
| `player_name` | string | Nombre del jugador. | `lineup[].player_name` | strip. |
| `player_nickname` | string | Apodo o nombre corto del jugador. | `lineup[].player_nickname` | strip; nulo en 4.2% de las filas. |
| `birth_date` | datetime64[us] | Fecha de nacimiento. | `lineup[].birth_date` | Texto -> fecha. |
| `player_gender` | category | Género del jugador. | `lineup[].player_gender` | Sin cambios. |
| `player_height` | float64 | Estatura en centímetros. | `lineup[].player_height` | Sin cambios (cm); nulo en 0.1% de las filas, no se imputa. |
| `player_weight` | float64 | Peso en kilos. | `lineup[].player_weight` | Sin cambios (kg); nulo en 2.3% de las filas, no se imputa. |
| `jersey_number` | Int64 | Número de camiseta en ese partido. | `lineup[].jersey_number` | Int64. |
| `country_id` | Int64 | Id del país del jugador (nacionalidad). | `lineup[].country.id` | Int64. |
| `country_name` | category | Nacionalidad del jugador. | `lineup[].country.name` | strip. |
| `stats_goals` | Int64 | Goles del jugador en el partido. | `lineup[].stats.goals` | Vacío en 26.2% de las filas; se recalcula desde eventos, no se usa como fuente. |
| `stats_assists` | Int64 | Asistencias. | `lineup[].stats.assists` | Ídem (vacío en 26.2%). |
| `stats_own_goals` | Int64 | Autogoles. | `lineup[].stats.own_goals` | Ídem (vacío en 26.2%). |
| `stats_penalties_scored` | Int64 | Penales anotados. | `lineup[].stats.penalties_scored` | Ídem (vacío en 26.2%). |
| `stats_penalties_missed` | Int64 | Penales fallados. | `lineup[].stats.penalties_missed` | Ídem (vacío en 26.2%). |
| `stats_penalties_saved` | Int64 | Penales atajados (portero). | `lineup[].stats.penalties_saved` | Ídem (vacío en 26.2%). |
| `skills_hops_rating` | float64 | Calificación del jugador normalizada entre 0 y 1 (más cerca de 1 = mejor). | `lineup[].skills.HOPS.rating` | Nulo legítimo (7.7%); no imputar. |
| `skills_hops_raw_rating` | float64 | Calificación cruda del modelo, sin normalizar. | `lineup[].skills.HOPS.raw_rating` | Nulo legítimo (7.7%); no imputar. |
