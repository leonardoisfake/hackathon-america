[Volver al índice](README.md)

# 10. Jugadores

## Resumen general

Dos fichas a nivel jugador y alineación: el grupo de rol con los minutos jugados (J1) y la formación por periodo con el impacto de los cambios (J2).

## J1. role_group y minutos

- **Qué mide.** El rol del jugador en el sistema y cuántos minutos jugó.
- **Entrada.** `lineups`: `lineup[].positions[]` (`position_id`, `from`, `to`, `from_period`, `to_period`, `start_reason`, `end_reason`). `events`: `position.id`, `player.id`.
- **Cálculo.** `role_group` según `position_id`: portero 1; defensa 2 a 8; medio 9 a 16; extremo o mediapunta 17 a 21; delantero 22 a 25. Minutos = suma, por tramo de posición, de `(to - from)` en el reloj de `lineups` (el ejemplo del diccionario sugiere un reloj corrido del partido; ver [sección 13](11_columnas_ambiguas.md)). Si `to` viene vacío se toma el cierre del partido (columna ambigua; ver [sección 13](11_columnas_ambiguas.md)). Un jugador con varios tramos suma todos.
- **Unidad y nivel.** Minutos y categoría; por jugador y partido.
- **Umbrales.** Ninguno.
- **No se considera.** `period` = 5.
- **Validación.** Los minutos por jugador deben coincidir con `minutes` de `player_match_stats`. La suma de minutos de los jugadores del EQ debe ser cerca de 11 veces la duración del partido (menos las expulsiones).

## J2. Formación por periodo e impacto de los cambios

- **Qué mide.** Qué formación usa el EQ en cada periodo y cómo cambia su rendimiento antes y después de una sustitución.
- **Entrada.** `events`: `type.name` (`Starting XI`, `Tactical Shift`, `Substitution`), `tactics.formation`, `tactics.lineup[]`, `substitution.replacement.id`, `player.id`, `period`, `timestamp`, `team.id`. `lineups`: `start_reason`.
- **Cálculo.** Formación = `tactics.formation` del `Starting XI` y de cada `Tactical Shift`, vigente desde ese evento hasta el siguiente; por periodo se toma la predominante (la de más minutos). Impacto de cambios: para cada `Substitution` del EQ en `match_second` t, ventana previa [t − 15 min, t) y posterior [t, t + 15 min). En cada ventana, por 15 minutos: `np_xg` a favor y en contra, posesión aproximada (proporción de eventos con `possession_team.id = EQ`), PPDA y presiones altas. Impacto = posterior − previa. Se segmenta por tipo de cambio con `start_reason` de `lineups` (táctico o lesión).
- **Unidad y nivel.** Formación como entero (por ejemplo 442); diferencias en las unidades de cada métrica; n de cambios.
- **Umbrales.** Ventana de 15 minutos (propuesta).
- **No se considera.** Los cambios por lesión en el análisis táctico (se reportan aparte), los cambios con una ventana posterior de menos de 15 minutos o con una expulsión dentro de la ventana, y `period` = 5.
- **Validación.** El número de `Substitution` del EQ debe coincidir con el de jugadores cuyo `start_reason` empieza en `Substitution - On` en `lineups`. Los dígitos de cada formación deben sumar 10 (más el portero).
