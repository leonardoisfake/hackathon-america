[Volver al índice](README.md)

# `frames_360_evento`

## Resumen general

Una fila por evento con frame 360. Guarda el área visible, cuántos jugadores se ven de cada equipo y las métricas 360 que StatsBomb calcula a nivel evento.

- Grano y llave: Un evento con frame por fila. Llave: (`match_id`, `event_uuid`).
- Quién la produce: 02_limpieza.py (Yordi)
- Columnas: 12
- Filas: 283,700 en los parquet crudos
- Fuente: Endpoint `frames_360` (`data/raw/parquet/frames_360.parquet`), columnas de nivel evento.

Reglas principales:

- `visible_area` queda como texto JSON y `visible_area_yd2` es su área en yardas cuadradas (fórmula del polígono).
- `n_visibles_equipo` y `n_visibles_rival` salen de `visible_player_counts`, según el `team_id` del evento. "Equipo" es el equipo del evento (el actor), no el equipo analizado; `n_visibles_rival` vale 0 si solo aparece ese equipo.
- Si `visible_player_counts` viene vacío (2,253 frames, 0.8%), los dos conteos quedan nulos. El nulo quiere decir que no hay conteo y no equivale a cero (C21).
- El umbral de jugadores visibles no se fija en esta tabla. Cada métrica aplica su propio filtro con `n_visibles_equipo` y `n_visibles_rival`, y Lee lo define en la especificación de métricas. Su valor provisional es actor visible y al menos 10 jugadores visibles, por calibrar con la distribución real (C19).
- `line_breaking_pass` y `ball_receipt_in_space` ausentes valen False; el resto de las métricas conserva el nulo.

Decisiones que la afectan:

| # | decisión | default vigente | quién decide | fecha límite |
|---|---|---|---|---|
| C1 | Unidad de distancia | Yardas (nativas de StatsBomb; 1 yarda = 0.9144 m) | RESUELTA (usuario) | resuelta |
| C3 | 360 en dos tablas | `frames_360` (jugador visible) y `frames_360_evento` (área y conteos) | RESUELTA (usuario) | resuelta |
| C18 | Partidos que no pasan los filtros de calidad (plan 7.1) | Se excluyen y se reportan en `data/interim/partidos_excluidos.csv`; ya no detienen la corrida. Los filtros son `play_status` = Normal, `match_status` = available, `collection_status` = Complete y `match_status_360` = available. Todas las tablas de `02_limpieza.py` salvo `team_match_stats_liga` traen solo los `match_id` de `partidos`. Las 4 tablas de `02_auxiliares.py` (`related_events`, `tactics_lineup`, `defensive_responsibility` y `shot_freeze_frame`) deben salir de `data/interim/eventos.parquet`, y no de los crudos, para traer solo los `match_id` de `partidos` | RESUELTA (usuario) | resuelta |
| C19 | Umbral de jugadores visibles del 360 | No se fija en la tabla limpia: `frames_360_evento` entrega `n_visibles_equipo` y `n_visibles_rival`, y cada métrica aplica su propio filtro. Lee define el umbral en la especificación de métricas; su valor provisional es actor visible y al menos 10 jugadores visibles, por calibrar con la distribución real de `visible_player_counts`. Esta decisión reemplaza el punto 7 de la sección 11 del plan | RESUELTA (usuario) | resuelta |
| C21 | Conteos 360 sin `visible_player_counts` | `n_visibles_equipo` y `n_visibles_rival` quedan nulos cuando `visible_player_counts` viene vacío (2,253 frames, 0.8%). El nulo quiere decir que no hay conteo y no equivale a cero | RESUELTA (usuario) | resuelta |

## Columnas (12)

| columna | tipo | descripción | origen | regla de limpieza |
|---|---|---|---|---|
| `match_id` | Int64 | Partido. | match_id | Llave. |
| `event_uuid` | string | Evento (unión con `eventos.id`). Llave junto con match_id. | `event_uuid` | strip. |
| `visible_area` | string | Polígono de la cancha que alcanzaba a ver la cámara de la transmisión en ese momento. | `visible_area` | Polígono [x1, y1, x2, y2, ...] guardado como texto JSON. |
| `visible_area_yd2` | float64 | Área del polígono visible en yardas cuadradas. | `visible_area` | Fórmula del polígono (shoelace) sobre los puntos. |
| `n_visibles_equipo` | Int64 | Jugadores visibles del equipo que ejecuta el evento. | `visible_player_counts[].count` | count del team_id igual al `eventos.team_id` del evento. Es el equipo del evento (el actor), no el equipo analizado. Nulo si `visible_player_counts` viene vacío (2,253 frames, 0.8%) o si el evento no está en `eventos`: significa sin conteo, no cero. |
| `n_visibles_rival` | Int64 | Jugadores visibles del equipo rival. | `visible_player_counts[].count` | count del team_id distinto al del evento; vale 0 si solo aparece el equipo del evento. Nulo si `visible_player_counts` viene vacío (2,253 frames, 0.8%) o si el evento no está en `eventos`: significa sin conteo, no cero. |
| `line_breaking_pass` | boolean | Verdadero si fue un pase que rompió una línea de defensas (pase filtrado entre líneas) y avanzó bien hacia el centro de la portería. | `line_breaking_pass` | Ausente = False. |
| `ball_receipt_in_space` | boolean | Verdadero si recibió el balón con espacio libre de rivales (radio de al menos 2 yardas). | `ball_receipt_in_space` | Ausente = False. |
| `num_defenders_on_goal_side_of_actor` | float64 | Cuántos rivales visibles están entre el que juega el balón y la portería (más cerca del arco que él). | `num_defenders_on_goal_side_of_actor` | Nulo legítimo; no imputar. |
| `distance_to_nearest_defender` | float64 | Distancia del jugador con balón al rival visible más cercano (en unidades de cancha de 120 x 80). | `distance_to_nearest_defender` | Nulo legítimo; filtrar por `n_visibles_rival` antes de usarlo. |
| `ball_receipt_exceeds_distance` | float64 | Qué tan grande era el espacio libre al recibir: 2, 5 o 10 yardas de radio sin rivales. | `ball_receipt_exceeds_distance` | Nulo legítimo; no imputar. |
| `distances_from_edge_of_visible_area` | string | Lista con la distancia de cada jugador al borde de lo que ve la cámara (indica qué tan confiable es su posición). | `distances_from_edge_of_visible_area` | Lista de {point_id, distance} guardada como texto JSON. |
