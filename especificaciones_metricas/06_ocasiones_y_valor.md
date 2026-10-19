[Volver al índice](README.md)

# 8. Ocasiones y valor

## Resumen general

Las métricas de valor esperado: xG y uplift de ejecución, xA, OBV neto, progresiones y terminaciones profundas, y xGChain y xGBuildup. Casi todas se validan contra las columnas de StatsBomb que resume la [sección 12](10_validaciones_cruzadas.md).

## V1. xG y uplift de ejecución

- **Qué mide.** El peligro de cada tiro (xG) y cuánto mejor o peor fue su ejecución.
- **Entrada.** `events`: `type.name = Shot`, `shot.statsbomb_xg`, `shot.shot_execution_xg`, `shot.shot_execution_xg_uplift`, `shot.type.name`, `shot.outcome.name`, `play_pattern.id`, `team.id`.
- **Cálculo.** Por tiro, y por equipo y partido. `np_xg` = suma de `shot.statsbomb_xg` sin los tiros con `shot.type.name = Penalty`. `op_xg` = juego abierto y `sp_xg` = balón parado. Regla A: por `shot.type.name` (`Open Play` contra `Corner` y `Free Kick`). Regla B: por `play_pattern.id` del tiro (2, 3 y 4 son balón parado). Se usa la regla que mejor coincida con StatsBomb. `uplift` = suma de `shot.shot_execution_xg_uplift`.
- **Unidad y nivel.** Goles esperados; entre 0 y 1 por tiro.
- **Umbrales.** Ninguno.
- **No se considera.** Penales en `np_xg`, tiros sin xG y `period` = 5.
- **Validación.** `np_xg`, `op_xg` y `sp_xg` deben coincidir con `team_match_np_xg`, `team_match_op_xg` y `team_match_sp_xg`, salvo redondeo.

## V2. xA

- **Qué mide.** El xG asistido: la suma del xG de los tiros que nacen de los pases de un jugador.
- **Entrada.** `events`: `Shot` (`shot.key_pass_id`, `shot.statsbomb_xg`, `shot.type.name`) y `Pass` (`id`, `player.id`, `pass.assisted_shot_id`, `pass.shot_assist`, `pass.goal_assist`).
- **Cálculo.** Se une `Shot.shot.key_pass_id = Pass.id`. xA del jugador = suma de `shot.statsbomb_xg` de los tiros cuyo pase clave es de ese jugador. Se cruza también con `pass.assisted_shot_id` para confirmar que ambos vínculos coinciden. `op_xa` = solo tiros de juego abierto; `sp_xa` = solo balón parado. xA del equipo = suma de los jugadores.
- **Unidad y nivel.** Goles esperados; por jugador y partido, y por 90 minutos (con los minutos de [J1](08_jugadores.md#j1-role_group-y-minutos)).
- **Umbrales.** Ninguno.
- **No se considera.** Penales, tiros sin pase previo (rebotes, tiros tras conducción) y `period` = 5.
- **Validación.** En 3 partidos, `xA`, `op_xa` y `sp_xa` por jugador deben coincidir con `xa`, `op_xa` y `sp_xa` de `player_match_stats`.

## V3. OBV neto

- **Qué mide.** Cuánto aporta cada acción con balón al cambio en la probabilidad de anotar menos la de recibir gol (en las siguientes 2 cadenas de posesión).
- **Entrada.** `events`: `obv_total_net`, `obv_for_net`, `obv_against_net`, `type.name`, `player.id`, `location`, `possession`, `team.id`.
- **Cálculo.** Suma de `obv_total_net` de los eventos del EQ por partido. Se desglosa por tipo de evento (`Pass`, `Carry`, `Dribble`, `Shot`, acciones defensivas y `Goal Keeper`), por tercio y por fase ([B1](01_objetos_base.md#b1-posesión-válida) a [B6](01_objetos_base.md#b6-contragolpe)). Se normaliza por 90 minutos o por posesión.
- **Unidad y nivel.** Goles esperados (diferencia); por evento, jugador y partido.
- **Umbrales.** Ninguno.
- **No se considera.** Los eventos sin OBV (solo 10 tipos de evento lo traen, cerca del 57% de las filas): el nulo significa que no aplica y no se imputa como cero. `period` = 5.
- **Validación.** La suma por partido debe coincidir con `team_match_obv`, y por tipo con `team_match_obv_pass`, `obv_shot`, `obv_defensive_action`, `obv_dribble_carry` y `obv_gk`.

## V4. deep_progressions y deep_completions

- **Qué mide.** Cuántas veces el EQ lleva el balón al tercio final y cuántos pases completos llegan cerca de la portería rival.
- **Entrada.** `events`: `type.name` (`Pass`, `Carry`), `location`, `pass.end_location`, `carry.end_location`, `pass.outcome.name`, `team.id`.
- **Cálculo.** `deep_progression` = pase completo o conducción del EQ que empieza en x < 80 y termina en x ≥ 80 (el glosario las define como las que llevan el balón al último tercio). Los regates no traen punto final, así que se cuentan a través de la conducción que los sigue. `deep_completion` = pase completo del EQ cuyo `pass.end_location` queda a menos de 20 yardas del centro de la portería [120, 40].
- **Unidad y nivel.** Conteo por partido y por 90 minutos.
- **Umbrales.** x ≥ 80 y 20 yardas. El glosario dice 20 metros para `deep_completions`; se prueba también 20 m (21.9 yardas) y se usa la que cuadre con StatsBomb.
- **No se considera.** `period` = 5. Se prueba con y sin balón parado y se usa la variante que cuadre.
- **Validación.** Debe coincidir con `team_match_deep_progressions` y `team_match_deep_completions`.

## V5. xGChain y xGBuildup

- **Qué mide.** El xG del tiro final atribuido a quienes participaron en la posesión (`xGChain`), y lo mismo sin contar al tirador ni a quien dio el pase del tiro (`xGBuildup`).
- **Entrada.** `events`: `possession`, `team.id`, `player.id`, `type.name`, `shot.statsbomb_xg`, `shot.key_pass_id`, `id`.
- **Cálculo.** Por posesión del EQ con al menos un tiro: `xG_pos` = suma de `shot.statsbomb_xg` de sus tiros, sin penales. Participantes = jugadores del EQ con al menos un evento `Pass`, `Carry`, `Dribble` o `Shot` en esa posesión. `xGChain` (jugador) = `xG_pos` por cada posesión en la que participa. `xGBuildup` (jugador) = lo mismo, excluyendo al tirador y al autor del pase cuyo `id` es `shot.key_pass_id`. Del equipo: `xGChain` = suma de `xG_pos` (cada posesión una sola vez). El glosario dice que el xG se «reparte», así que se prueban dos variantes: valor completo para cada participante o dividido entre participantes. Versión `op`: solo posesiones de juego abierto.
- **Unidad y nivel.** Goles esperados; por jugador y partido; por posesión.
- **Umbrales.** Ninguno.
- **No se considera.** Penales, posesiones sin tiro y `period` = 5.
- **Validación.** En 3 partidos, comparar por jugador con `xgchain`, `op_xgchain`, `xgbuildup` y `op_xgbuildup` de `player_match_stats`; se usa la variante que coincida.
