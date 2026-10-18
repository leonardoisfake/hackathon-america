[Volver al índice](README.md)

# `frames_360`

## Resumen general

Una fila por jugador visible en cada frame 360. Sirve para dibujar dónde estaban compañeros y rivales cuando ocurrió el evento.

- Grano y llave: Un jugador visible por frame. Llave: (`match_id`, `event_uuid`, `jugador_idx`).
- Quién la produce: 02_limpieza.py (Yordi)
- Columnas: 9
- Filas: 3,848,340 en los parquet crudos
- Fuente: Endpoint `frames_360` (`data/raw/parquet/frames_360.parquet`), columna `freeze_frame` (texto JSON).

Reglas principales:

- `freeze_frame` se explota con un contador `jugador_idx` desde 0; el freeze frame no trae ids de jugador.
- Solo aparecen los jugadores que ve la cámara.
- `x` e `y` quedan en la perspectiva del equipo que ejecuta el evento; `es_equipo_analizado` dice si el jugador visible es del equipo analizado y queda nulo si el evento no está en `eventos`.
- `event_uuid` se une con `eventos.id`.

Decisiones que la afectan:

| # | decisión | default vigente | quién decide | fecha límite |
|---|---|---|---|---|
| C1 | Unidad de distancia | Yardas (nativas de StatsBomb; 1 yarda = 0.9144 m) | RESUELTA (usuario) | resuelta |
| C3 | 360 en dos tablas | `frames_360` (jugador visible) y `frames_360_evento` (área y conteos) | RESUELTA (usuario) | resuelta |
| C14 | Eventos sin ubicación (0.9%) | `x` e `y` nulos; se excluyen de los mapas, sin imputar | Pablo | vigente por defecto; confirmar antes del lun 19 |
| C15 | Perspectiva en `frames_360` | Solo `es_equipo_analizado`; `x` e `y` quedan en la perspectiva del equipo del evento (sin `x_eq`/`y_eq`) | Pablo | vigente por defecto; confirmar antes del lun 19 |
| C18 | Partidos que no pasan los filtros de calidad (plan 7.1) | Se excluyen y se reportan en `data/interim/partidos_excluidos.csv`; ya no detienen la corrida. Los filtros son `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. Todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga` traen solo los `match_id` de `partidos`. Las 4 tablas de `02_auxiliares.py` (`related_events`, `tactics_lineup`, `defensive_responsibility` y `shot_freeze_frame`) deben salir de `data/interim/eventos.parquet`, y no de los crudos, para traer solo los `match_id` de `partidos` | RESUELTA (usuario) | resuelta |

## Columnas (9)

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `event_uuid` | string | Evento al que pertenece el frame; se une con `eventos.id`. | `event_uuid` | strip. Llave junto con jugador_idx. |
| `jugador_idx` | Int64 | Orden del jugador dentro del freeze frame. | posición en la lista `freeze_frame` | explode con contador desde 0; el freeze frame no trae ids de jugador. |
| `teammate` | boolean | El jugador visible es compañero de quien ejecuta el evento. | `freeze_frame[].teammate` | Sin cambios. |
| `actor` | boolean | El jugador visible es quien ejecuta el evento. | `freeze_frame[].actor` | Sin cambios. |
| `keeper` | boolean | El jugador visible es portero. | `freeze_frame[].keeper` | Sin cambios. |
| `x` | float64 | Coordenada x del jugador visible (yardas, perspectiva del equipo que ejecuta el evento). | `freeze_frame[].location` | Se separa [x, y]. |
| `y` | float64 | Coordenada y del jugador visible (yardas, perspectiva del equipo que ejecuta el evento). | `freeze_frame[].location` | Se separa [x, y]. |
| `es_equipo_analizado` | boolean | El jugador visible pertenece al equipo analizado. | `freeze_frame[].teammate`, `eventos.team_id`, `partidos.equipo_id` | Si el equipo del evento es el analizado: teammate; si no: not teammate. Nulo si el evento no está en `eventos`. |
