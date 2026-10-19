[Volver al índice](README.md)

# `partidos`

## Resumen general

Una fila por partido de América con Jardine. Junta fecha, torneo, fase, rival, marcador y entrenadores, y es la tabla a la que se unen todas las demás por `match_id`.

- Grano y llave: Un partido por fila. Llave: `match_id`.
- Quién la produce: 02_limpieza.py (Yordi)
- Columnas: 60
- Filas: 91 en los parquet crudos, antes de excluir partidos
- Fuente: Endpoint `matches` (`data/raw/parquet/partidos.parquet`) más las columnas derivadas que agrega `01_descarga.py`.

Reglas principales:

- Se descartan `attendance`, `home_team_group` y `away_team_group` (0% de datos). Las listas de managers no se explotan: quedan resumidas en `entrenador_id`, `entrenador_rival`, `entrenador_rival_id`, `rival_coentrenador` y `coentrenador` (C20).
- `torneo` sale de `match_date` (julio a diciembre = Apertura, enero a junio = Clausura). `fase` vale `regular` o `liguilla`; `es_play_in` marca el stage id 2 y `es_final` los dos partidos de la final.
- Los partidos que no pasan los filtros de calidad (plan 7.1) se excluyen y no detienen la corrida, así que la tabla limpia puede tener menos de 91 filas. La limpieza los anota en `data/interim/partidos_excluidos.csv` (con `--solo-partido`, en `data/interim/muestra/`), con las columnas `match_id`, `campo` y `valor` y una fila por partido y por filtro que falla. Los filtros son `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available.
- Los errores de video (NoVidError, IncVidError y PoorVidError) son valores de `collection_status`, así que el filtro `collection_status = Complete` ya los deja fuera.

Decisiones que la afectan:

| # | decisión | default vigente | quién decide | fecha límite |
|---|---|---|---|---|
| C12 | `category` o `string` en nombres | Los `*_name` de equipos y catálogos, más `rival_nombre`, son category; las personas (`referee_name`, `player_name`, `pass_recipient_name`, `substitution_replacement_name`, `counterpart_name`, `entrenador_rival` y `player_nickname`) son string aunque terminen en `_name` | RESUELTA (Yordi) | resuelta |
| C18 | Partidos que no pasan los filtros de calidad (plan 7.1) | Se excluyen y se reportan en `data/interim/partidos_excluidos.csv`; ya no detienen la corrida. Los filtros son `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. Todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga` traen solo los `match_id` de `partidos`. Las 4 tablas de `02_auxiliares.py` (`related_events`, `tactics_lineup`, `defensive_responsibility` y `shot_freeze_frame`) deben salir de `data/interim/eventos.parquet`, y no de los crudos, para traer solo los `match_id` de `partidos` | RESUELTA (Yordi) | resuelta |
| C20 | Listas de managers | `managers` no se explota: queda resumido en `entrenador_id`, `entrenador_rival`, `entrenador_rival_id`, `rival_coentrenador` y `coentrenador` de `partidos` | Lee | vigente por defecto; confirmar antes del lun 19 |

## Columnas (60)

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Número único del partido. | `match_id` | Sin cambios. |
| `match_date` | datetime64[us] | Fecha en que se juega el partido (formato año-mes-día). | `match_date` | Texto -> fecha. |
| `kick_off` | string | Hora del silbatazo inicial. | `kick_off` | Sin cambios. |
| `home_score` | Int64 | Goles finales del local. | `home_score` | Sin cambios. |
| `away_score` | Int64 | Goles finales del visitante. | `away_score` | Sin cambios. |
| `behind_closed_doors` | boolean | Verdadero si el partido fue a puerta cerrada, sin público. | `behind_closed_doors` | Sin cambios. |
| `neutral_ground` | boolean | Verdadero si se jugó en cancha neutral (ninguno de los dos es local de verdad). | `neutral_ground` | Sin cambios. |
| `collection_status` | category | Avance de la captura de datos de este partido: 'Complete' significa terminado; los demás indican proceso, validación o problema (ver valores). | `collection_status` | Sin cambios. |
| `play_status` | category | Si el partido se jugó o se jugará normal, o si fue pospuesto, cancelado, suspendido o dado por perdido. | `play_status` | Sin cambios. |
| `match_status` | category | Indica si ya hay datos de EVENTOS descargables. | `match_status` | Sin cambios. |
| `match_status_360` | category | Indica si hay datos 360 de ese partido. | `match_status_360` | Sin cambios. |
| `last_updated` | datetime64[us] | Última vez que se modificó la información del partido. | `last_updated` | Texto ISO -> fecha y hora. |
| `last_updated_360` | datetime64[us] | Última actualización de los datos 360. | `last_updated_360` | Texto ISO -> fecha y hora. |
| `match_week` | Int64 | Número de jornada/semana del torneo en que cae el partido. | `match_week` | Sin cambios. |
| `competition_id` | Int64 | Id de la competencia (ej. Liga MX). | `competition.competition_id` | Sin cambios. |
| `competition_country_name` | category | País de la competencia. | `competition.country_name` | Sin cambios. |
| `competition_name` | category | Nombre de la competencia. | `competition.competition_name` | Sin cambios. |
| `season_id` | Int64 | Id de la temporada. | `season.season_id` | Sin cambios. |
| `season_name` | category | Nombre de la temporada (ej. '2017/2018'). | `season.season_name` | Sin cambios. |
| `home_team_id` | Int64 | Id del equipo local. | `home_team.home_team_id` | Sin cambios. |
| `home_team_name` | category | Nombre del equipo local. | `home_team.home_team_name` | Sin cambios. |
| `home_team_gender` | category | Si el equipo local es varonil o femenil. | `home_team.home_team_gender` | Sin cambios. |
| `home_team_youth` | boolean | Verdadero si el equipo local es de categoría juvenil. | `home_team.home_team_youth` | Sin cambios. |
| `home_team_country_id` | Int64 | Id del país del equipo local. | `home_team.country.id` | Sin cambios. |
| `home_team_country_name` | category | Nombre del país del equipo local. | `home_team.country.name` | Sin cambios. |
| `away_team_id` | Int64 | Id del equipo visitante. | `away_team.away_team_id` | Sin cambios. |
| `away_team_name` | category | Nombre del equipo visitante. | `away_team.away_team_name` | Sin cambios. |
| `away_team_gender` | category | Si el equipo visitante es varonil o femenil. | `away_team.away_team_gender` | Sin cambios. |
| `away_team_youth` | boolean | Verdadero si el equipo visitante es de categoría juvenil. | `away_team.away_team_youth` | Sin cambios. |
| `away_team_country_id` | Int64 | Id del país del equipo visitante. | `away_team.country.id` | Sin cambios. |
| `away_team_country_name` | category | Nombre del país del equipo visitante. | `away_team.country.name` | Sin cambios. |
| `metadata_data_version` | category | Versión del método de captura de los eventos (ej. 1.1.0). | `metadata.data_version` | Sin cambios. |
| `metadata_shot_fidelity_version` | category | Versión de fidelidad con la que se capturaron los tiros. | `metadata.shot_fidelity_version` | Sin cambios. |
| `metadata_xy_fidelity_version` | category | Versión de fidelidad con la que se capturaron las coordenadas (sin documentar en el PDF). | `metadata.xy_fidelity_version` | Sin cambios. |
| `competition_stage_id` | Int64 | Id de la fase del torneo (1 = temporada regular; ver tabla de valores). | `competition_stage.id` | Sin cambios. |
| `competition_stage_name` | category | Nombre de la fase: temporada regular, liguilla (Play-offs), final, etc. | `competition_stage.name` | Sin cambios. |
| `stadium_id` | Int64 | Id del estadio. | `stadium.id` | Sin cambios. |
| `stadium_name` | category | Nombre del estadio (ej. Estadio Azteca). | `stadium.name` | Sin cambios. |
| `stadium_country_id` | Int64 | Id del país donde está el estadio. | `stadium.country.id` | Sin cambios. |
| `stadium_country_name` | category | País donde está el estadio. | `stadium.country.name` | Sin cambios. |
| `referee_id` | Int64 | Id del árbitro central. | `referee.id` | Sin cambios. |
| `referee_name` | string | Nombre del árbitro central. | `referee.name` | Sin cambios. |
| `referee_country_id` | Int64 | Id del país del árbitro. | `referee.country.id` | Sin cambios. |
| `referee_country_name` | category | País de origen del árbitro. | `referee.country.name` | Sin cambios. |
| `torneo` | category | Torneo del partido, derivado de la fecha (por ejemplo 'Apertura 2023'). | `partidos.parquet` (derivada) | Derivada de match_date: julio a diciembre = Apertura, enero a junio = Clausura. |
| `fase` | category | regular o liguilla. | `partidos.parquet` (derivada) | regular si competition_stage.id en {1, 42, 44}; liguilla en otro caso. |
| `es_play_in` | boolean | El partido es de la ronda Play-In. | `partidos.parquet` (derivada) | competition_stage.id = 2. |
| `es_final` | boolean | Uno de los dos partidos de la final del torneo. | `partidos.parquet` (derivada) | Dos últimos partidos de eliminación directa del torneo entre el mismo par de equipos (calculado sobre toda la liga). |
| `entrenador_id` | Int64 | manager_id del entrenador analizado. | `partidos.parquet` (derivada) | Agregada en la descarga con --manager-id. |
| `equipo_id` | Int64 | team_id del equipo analizado. | `partidos.parquet` (derivada) | Agregada en la descarga con --team-id. |
| `es_local` | boolean | El equipo analizado juega de local. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `rival_id` | Int64 | team_id del rival. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `rival_nombre` | category | Nombre del rival. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `entrenador_rival` | string | Entrenador(es) del rival, separados por ' / '. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `entrenador_rival_id` | Int64 | manager_id del primer entrenador del rival. | `partidos.parquet` (derivada) | Derivada en la descarga; Int64. |
| `rival_coentrenador` | boolean | El rival tuvo más de un manager en el partido. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `goles_favor` | Int64 | Goles del equipo analizado. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `goles_contra` | Int64 | Goles del rival. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `resultado` | category | G, E o P para el equipo analizado. | `partidos.parquet` (derivada) | Derivada en la descarga. |
| `coentrenador` | boolean | El equipo analizado tuvo más de un manager en el partido. | `partidos.parquet` (derivada) | Derivada en la descarga. |
