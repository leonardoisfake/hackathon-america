[Volver al índice](README.md)

# 4. Jugadores

## Resumen general

Tres fichas sobre los jugadores del EQ (América con Jardine, `team_id` 1229): el rol y los minutos de cada jugador (J1), la formación por periodo y la rotación del once inicial (J2a) y el impacto de las sustituciones (J2b). Las calcula `scripts/03_jugadores.py`, en el que cada métrica es una función que recibe DataFrames y devuelve otro. Las fichas usan los siete campos de las de Lee: qué mide, entrada, cálculo, unidad y nivel, umbrales, qué no se considera y validación. Corresponden a sus fichas J1 y J2 de `especificaciones_metricas/08_jugadores.md`.

## Cómo se corre

```
python scripts/03_jugadores.py --solo-partido 3995374   # lee data/interim/muestra/, escribe en data/processed/jugadores/muestra/
python scripts/03_jugadores.py                          # lee data/interim/, escribe en data/processed/jugadores/
python scripts/03_jugadores.py --ver                    # además imprime los resúmenes de rendimiento y de cambios
```

Lee `partidos`, `eventos` y `posiciones` de `data/interim/`, y `contexto_eventos` de `data/processed/` para el marcador y la superioridad numérica. `tactics_lineup` (de `02_auxiliares.py`) es opcional: si falta o no trae las columnas esperadas, los onces iniciales salen de `posiciones`. Al final imprime un resumen de lo que generó.

## J1. `role_group` y minutos jugados

- **Qué mide.** El rol de cada jugador del EQ y cuántos minutos juega en cada partido.
- **Entrada.** `posiciones`: `match_id`, `team_id`, `player_id`, `posicion_idx`, `position_id`, `from`, `to`, `from_period`, `to_period`. `eventos`: el `timestamp` del `Half End` de cada periodo. `partidos`: `equipo_id`.
- **Cálculo.**
  1. Cada `position_id` se asigna a un `role_group`:

     | `position_id` | `role_group` |
     | :--- | :--- |
     | 1 | portero |
     | 2 a 8 | defensa |
     | 9 a 16 | medio |
     | 17 a 21 | extremo_mediapunta |
     | 22 a 25 | delantero |

  2. La duración de cada periodo es el `timestamp` de su `Half End`.
  3. `posiciones.from` y `to` vienen en reloj corrido: el 2.º tiempo empieza en 00:45:00. Cada tramo de posición se recorta a cada periodo y los minutos se suman por periodo; nunca se resta `to − from` directo. Un `to` vacío quiere decir que el jugador siguió hasta el silbatazo final.
  4. Por jugador y partido se suman los minutos de sus tramos. Su rol principal es el grupo donde jugó más minutos.
  5. Se reporta qué porcentaje de minutos cae en las posiciones ambiguas 7, 8, 12 y 16 (carrileros y volantes por banda), para declararlo como límite.
- **Unidad y nivel.** Minutos; por jugador y partido, y por tramo de posición.
- **Umbrales.** Los rangos de `position_id` de la tabla. Inicio de periodo en 0 s (1.º) y 2,700 s (2.º).
- **No se considera.** Tiempo extra (periodos 3 y 4) y penales (5). Jugadores del rival.
- **Validación.** Cada fila de `minutos_jugados` trae `tramos_sin_minutos`. La versión del 20 de octubre ya no lee `player_match_stats`, así que no compara contra `player_match_minutes`.
- **Salidas.** `minutos_jugados`, `tramos_posicion` y `peso_posiciones`.

## J2a. Formación por periodo y onces iniciales

- **Qué mide.** Con qué formación juega el EQ en cada periodo y cuánto rota su once inicial de un partido a otro.
- **Entrada.** `eventos`: `Starting XI` y `Tactical Shift` del EQ (`tactics_formation`, `period`, `timestamp`) y el `Half End`. `partidos`: `match_date`, `fase`, `torneo`. Para los titulares, `tactics_lineup` o, si no sirve, `posiciones` (`posicion_idx`, `start_reason`).
- **Cálculo.**
  1. Cada formación está vigente desde su `Starting XI` o `Tactical Shift` hasta el siguiente cambio.
  2. La formación predominante de un periodo es la que estuvo más minutos vigente. También se guardan la secuencia de formaciones del periodo y cuántas hubo.
  3. Los titulares de cada partido salen del `Starting XI` del EQ en `tactics_lineup`; si esa tabla no sirve, del primer tramo de `posiciones` cuyo `start_reason` dice «Starting».
  4. En orden de fecha, cada partido cuenta cuántos titulares son nuevos frente al partido anterior. Por jugador se cuentan sus partidos como titular y el porcentaje que representan.
- **Unidad y nivel.** Formación y minutos por partido y periodo; titulares por partido; titularidades por jugador.
- **Umbrales.** Ninguno.
- **No se considera.** Tiempo extra y penales. Formaciones del rival.
- **Validación.** Avisa si los dígitos de una formación no suman 10 y si un partido no tiene 11 titulares.
- **Salidas.** `formacion_por_periodo`, `onces_iniciales` y `titularidades`.

## J2b. Impacto de las sustituciones

- **Qué mide.** Cuándo cambia Jardine y cómo se mueve el rendimiento del equipo en los 15 minutos antes y después de cada cambio.
- **Entrada.** `eventos`: `Substitution` (`player_id`, `position_id`, `substitution_replacement_id`, `substitution_outcome_name`, `minute`, `timestamp`), tiros (`shot_statsbomb_xg`, `shot_type_name`, `shot_outcome_name`), `Own Goal For`, `obv_total_net`, `possession_team_id` y tarjetas (`foul_committed_card_name`, `bad_behaviour_card_name`). `posiciones` para el rol de quien entra. `partidos`: `es_local`, `fase`, `torneo`.
- **Cálculo.**
  1. Antes de cada evento se calculan el marcador (goles de tiros y `Own Goal For`, sin la tanda de penales) y la superioridad numérica (rojas: `Red Card` y `Second Yellow`).
  2. Una fila por sustitución del EQ, con el rol de quien sale (`position_id` del evento), el de quien entra (su primer tramo en `posiciones`) y el tipo: lesión si `substitution_outcome_name` lo dice, táctico si no.
  3. Los cambios del mismo partido, periodo y minuto forman un solo momento de cambio.
  4. Para cada momento se toman los 15 minutos antes y después con `timestamp`, que cuenta desde el inicio del periodo, así que las ventanas nunca cruzan el descanso. En cada ventana: xG a favor, en contra y diferencia (sin penales); OBV del equipo, del rival y neto; y posesión como proporción de los eventos no administrativos en los que el balón es del EQ. El xG y el OBV se escalan a 15 minutos cuando la ventana es más corta.
  5. El resumen da la media de cada diferencia (después menos antes) con un intervalo de 95% por bootstrap (5,000 remuestreos, semilla 0). Solo se separa por marcador si la celda tiene al menos 15 momentos.
  6. Un segundo resumen cuenta cuándo cambia Jardine según marcador, localía, fase y superioridad (momentos, cambios y minuto mediano, p25 y p75), con una matriz de qué roles salen y cuáles entran.
- **Unidad y nivel.** xG y OBV por 15 minutos, posesión como proporción; por momento de cambio y resumido por estado del marcador.
- **Umbrales.** Ventana de 15 minutos (plan, sección 8, y ficha J2). Mínimo de 8 minutos por lado y 15 momentos por celda, ambos propuestos por Pato.
- **No se considera.** Momentos en tiempo extra, sin `Half End`, por lesión, con alguna ventana de menos de 8 minutos o con una roja dentro de la ventana. Penales en el xG.
- **Validación.** Avisa si las sustituciones de `eventos` no coinciden con las entradas por sustitución en `posiciones` de cada partido. No es un efecto causal: los cambios responden al estado del partido.
- **Salidas.** `cambios_individuales`, `momentos_de_cambio`, `cambio_en_rendimiento`, `resumen_rendimiento`, `resumen_cambios` y `matriz_roles_cambios`.

## Salidas

Las 12 tablas van a `data/processed/jugadores/` (o a `muestra/` con `--solo-partido`).

| Tabla | Una fila por | Ficha |
| :--- | :--- | :--- |
| `minutos_jugados` | Jugador del EQ y partido | J1 |
| `tramos_posicion` | Tramo de posición | J1 |
| `peso_posiciones` | `position_id` | J1 |
| `formacion_por_periodo` | Partido y periodo | J2a |
| `onces_iniciales` | Partido | J2a |
| `titularidades` | Jugador | J2a |
| `cambios_individuales` | Sustitución del EQ | J2b |
| `momentos_de_cambio` | Partido, periodo y minuto | J2b |
| `cambio_en_rendimiento` | Momento de cambio | J2b |
| `resumen_rendimiento` | Estado del marcador y métrica | J2b |
| `resumen_cambios` | Dimensión y categoría | J2b |
| `matriz_roles_cambios` | Rol que sale, con una columna por rol que entra | J2b |

## Decisiones por confirmar

Todas son propuesta hasta que Lee las confirme:

1. El equipo analizado es `partidos.equipo_id` y todo se atribuye con `team_id` (plan 7.3.8).
2. Solo cuentan los periodos 1 y 2. El tiempo extra y los penales quedan fuera porque el inicio de los periodos 3 y 4 no está verificado (C9).
3. Resuelto el 20 de octubre: el marcador y la superioridad numérica salen de `contexto_eventos` (`score_state` y `numerical_state_cat`), así que el equipo tiene una sola definición. Solo si no encuentra esa tabla los calcula desde `eventos`.
4. No incluye PPDA ni presiones altas: los calcula `03_defensa.py` (Pablo), y las [métricas finales](05_metricas_finales.md) fijan la presión alta en los últimos 40 metros.
5. El mínimo de 8 minutos por ventana y el de 15 momentos por celda.

El script marcaba cuatro puntos para verificar con los datos. Los tres primeros se revisaron con los datos limpios el 20 de octubre y se cumplen:

- Las tarjetas rojas se llaman `Red Card` y `Second Yellow` (la otra es `Yellow Card`).
- La columna de minutos de `player_match_stats` es `player_match_minutes`.
- Los titulares tienen `start_reason` = `Starting XI`.
- Falta confirmar que el `position_id` del evento `Substitution` es el del jugador que sale.
