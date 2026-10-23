[Volver al índice](README.md)

# 4. Contexto

## Resumen general

Las variables que sitúan cada evento en su partido: el reloj, el marcador, la localía y el rival, la fuerza del rival y la superioridad numérica por expulsiones. Se usan para segmentar las demás métricas.

## C1. match_clock y minute_bin

- **Qué mide.** El momento del partido en que ocurre cada evento.
- **Entrada.** `events`: `period`, `minute`, `second`, `timestamp`.
- **Cálculo.** `match_second = minute * 60 + second`. `match_clock = match_second / 60`, en minutos. `minute_bin` en ventanas de 15 minutos por periodo: periodo 1: `0-15`, `15-30`, `30-45` y `45+` (tiempo agregado); periodo 2: `45-60`, `60-75`, `75-90` y `90+`. Si aparecen periodos 3 o 4, van en un bin `ET`.
- **Unidad y nivel.** Minutos y categoría; una fila por evento.
- **Umbrales.** Ventana de 15 minutos (propuesta).
- **No se considera.** `period` = 5.
- **Validación.** `df.groupby('period').timestamp.min()` debe ser cero en cada periodo. El máximo de `minute` por periodo debe cuadrar con la duración del partido y ningún bin debe quedar vacío.

## C2. score_state

- **Qué mide.** Si el EQ va ganando, empatando o perdiendo cuando ocurre el evento.
- **Entrada.** `events`: `type.name` (`Shot`, `Own Goal For`), `shot.outcome.name`, `team.id`, `index`, `period`. `matches`: `home_score`, `away_score`.
- **Cálculo.** Gol del EQ = `Shot` del EQ con `shot.outcome.name = Goal`, más eventos `Own Goal For` con `team.id = EQ`. Gol de R, lo mismo con R. Se acumula en orden de `(match_id, index)` y se desplaza una posición para que el estado sea el de antes del evento. `goal_diff = goles EQ - goles R`. `score_state` = ganando (> 0), empatando (= 0) o perdiendo (< 0). Versión agrupada: `goal_diff` recortado a ±2.
- **Unidad y nivel.** Entero y categoría; una fila por evento.
- **Umbrales.** Ninguno.
- **No se considera.** La tanda de penales (`period` = 5).
- **Validación.** Al final de cada partido, los goles acumulados deben coincidir con `home_score` y `away_score` de `matches` (los 91 partidos). Si no coinciden, se invierte el criterio de autogoles.

## C3. is_home, rival_id, stage, match_week

- **Qué mide.** El contexto del partido: localía, rival, fase y jornada.
- **Entrada.** `matches`: `home_team.home_team_id`, `away_team.away_team_id`, `match_week`, `competition_stage.id`, `match_date`, `season.season_id`.
- **Cálculo.** `is_home = (home_team_id == 1229)`. `rival_id` = el id del otro equipo. `match_week` tal cual. `stage` = `regular` si `competition_stage.id` está en {1, 42, 44}; `fase final` en cualquier otro caso (las etiquetas de ronda no son confiables). Torneo derivado de `match_date`: julio a diciembre es Apertura y enero a junio es Clausura, junto con `season_id`.
- **Unidad y nivel.** Booleano, ids, entero y categoría; una fila por partido (se copia a cada evento).
- **Umbrales.** Ninguno.
- **No se considera.** Los nombres de ronda de `competition_stage.name` (`Final`, `Semi-finals`) para distinguir rondas.
- **Validación.** Deben salir 91 partidos. La jornada no debe tener huecos dentro de cada torneo y los partidos de fase final deben ser 25.

## C4. rival_strength

- **Qué mide.** El nivel del rival en ese torneo.
- **Entrada.** `team_match_stats` de los 1,364 partidos de la liga (`team_match_np_xgd`, `team_match_goals`, `team_match_goals_conceded`); `matches` (`match_date`, `competition_stage.id`).
- **Cálculo.** Para cada rival y torneo (derivado de `match_date`): promedio por partido de `np_xgd` en sus partidos de fase regular del mismo torneo, excluyendo el partido contra el EQ. `rival_strength` = ese promedio. Versión categórica: tercil (débil, medio, fuerte) entre los equipos del torneo. Segunda versión: puntos por partido (3, 1, 0 según los marcadores). Se usa `team_match_stats` y no `team_season_stats` porque este último junta Apertura y Clausura.
- **Unidad y nivel.** Goles esperados por partido; categoría; una fila por rival y torneo.
- **Umbrales.** Terciles.
- **No se considera.** Partidos de fase final y el partido contra el EQ.
- **Validación.** Todos los rivales deben tener valor en cada torneo. El orden por `rival_strength` debe parecerse al de la tabla de posiciones: los mejores equipos arriba.

## C5. numerical_state

- **Qué mide.** Si el EQ juega con más, igual o menos jugadores que el rival por tarjetas rojas.
- **Entrada.** `events`: `type.name` (`Foul Committed`, `Bad Behaviour`), `foul_committed.card.name`, `bad_behaviour.card.name`, `team.id`, `period`, `timestamp`. `lineups`: `end_reason`.
- **Cálculo.** Se marca cada expulsión (tarjeta `Red Card` o `Second Yellow`) con su equipo y su `match_second`. `numerical_state = expulsiones de R acumuladas - expulsiones del EQ acumuladas`, vigente desde el evento de la tarjeta. Categorías: igualdad (0), superioridad (> 0) e inferioridad (< 0).
- **Unidad y nivel.** Entero entre −2 y +2 y categoría; una fila por evento.
- **Umbrales.** Ninguno.
- **No se considera.** Tarjetas amarillas simples y `period` = 5.
- **Validación.** El número de expulsiones por partido debe coincidir con `team_match_red_cards` + `team_match_second_yellow_cards` y con los `end_reason` `Red Card` y `Second Yellow Card` de `lineups`.
