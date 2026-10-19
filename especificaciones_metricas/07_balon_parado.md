[Volver al índice](README.md)

# 9. Balón parado

## Resumen general

Dos fichas sobre jugadas de balón parado: el tipo y la fase de cada una (P1) y la zona de remate y el xG frente al juego abierto (P2).

## P1. set_piece_type y set_piece_phase

- **Qué mide.** El tipo de jugada a balón parado, quién la tiene y en qué fase está.
- **Entrada.** `events`: `play_pattern.id`, `pass.type.name` (`Corner`, `Free Kick`, `Throw-in`), `shot.type.name`, `set_piece_phase`, `possession`, `possession_team.id`, `team.id`.
- **Cálculo.** `set_piece_type` por posesión según `play_pattern.id` del primer evento: 2 = `Corner`, 3 = `Free Kick`, 4 = `Throw In`. El saque en sí es el primer `Pass` con `pass.type.name` `Corner`, `Free Kick` o `Throw-in`. Tiro libre directo = `Shot` con `shot.type.name = Free Kick`; indirecto = el que se juega con pase. `set_piece_phase` se reporta tal cual (1 o 2; solo viene en parte de los eventos y el diccionario no dice qué fase es cada una). A favor = `possession_team.id = EQ`; en contra = R. Por tipo: conteo, % que termina en tiro, xG y goles.
- **Unidad y nivel.** Conteo por partido; porcentaje y xG.
- **Umbrales.** Ninguno (usa el catálogo de valores).
- **No se considera.** Saques de meta (`play_pattern` 7), reanudaciones del portero (8), saque inicial (9), penales (`shot.type.name = Penalty`) y `period` = 5.
- **Validación.** Los corners, tiros libres y saques de banda del EQ deben coincidir con `team_match_corners`, `team_match_free_kicks` y `team_match_throw_ins`; los tiros que salen de cada uno, con `team_match_shots_from_corners`, `shots_from_free_kicks` y `shots_from_throw_ins`.

## P2. Zona de remate y xG de balón parado contra juego abierto

- **Qué mide.** Dónde se remata en balón parado, qué tan peligrosos son esos remates y cómo se comparan con el juego abierto.
- **Entrada.** `events`: `Shot` (`location`, `shot.statsbomb_xg`, `shot.type.name`, `shot.body_part.name`, `shot.first_time`, `play_pattern.id`), `possession_team.id`.
- **Cálculo.** Los tiros del EQ y de R se clasifican por origen (balón parado o juego abierto) con la misma regla que [V1](06_ocasiones_y_valor.md#v1-xg-y-uplift-de-ejecución). Zona de remate: área chica (x ≥ 114 y 30 ≤ y ≤ 50), área grande sin el área chica (x ≥ 102 y 18 ≤ y ≤ 62) y fuera del área; también la celda de `cell_6x5`. Se reporta por tipo (corner, tiro libre, saque de banda): tiros, xG, xG por tiro y zona de remate. En defensa, lo mismo con los tiros de R (zonas vulnerables).
- **Unidad y nivel.** xG, conteos y zona; por partido y por tipo.
- **Umbrales.** Área grande de 18 yardas de profundidad y área chica de 6, en una cancha de 120 × 80.
- **No se considera.** Penales, tiros sin `location` y `period` = 5.
- **Validación.** El xG por tipo debe coincidir con `team_match_corner_xg`, `team_match_free_kick_xg` y `team_match_throw_in_xg`, y el total con `sp_xg` y `op_xg` de [V1](06_ocasiones_y_valor.md#v1-xg-y-uplift-de-ejecución).
