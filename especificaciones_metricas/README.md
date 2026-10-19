# Especificación de métricas - Hackathon ITAM + Club América

Versión del 18 de octubre de 2026. Fuentes: la tabla de variables nuevas (sección 8 del plan de trabajo), `K-Pumas/Framework.pdf` (definiciones y supuestos del equipo) y `diccionario_endpoints_1.xlsx`. Alcance: todas las métricas de la tabla más los objetos base que define `K-Pumas/Framework.pdf`. Las columnas que el diccionario marca como ambiguas se analizan en la [sección 13](11_columnas_ambiguas.md); cuando una ficha depende de alguna, se indica.

## Resumen general

Define cómo se calcula cada métrica del análisis táctico de Jardine con el Club América (91 partidos de Liga MX, datos StatsBomb). Lee escribió la especificación; esta carpeta la reparte en un archivo por tema. Aquí están las convenciones y los umbrales que comparten todas las fichas, y el [índice](#índice) lleva a cada una de las 34 fichas.

## 1. Cómo leer este documento

Cada ficha responde siete preguntas: qué mide, entrada (columnas y tabla de origen), cálculo, unidad y nivel, umbrales, qué no se considera y cómo se valida. Los nombres de columna son los del diccionario (con punto, por ejemplo `pass.end_location`); en código se usan los equivalentes de `sb_api.py`. Prefijos de las fichas: B = objeto base, C = contexto, E = espacio, I = inicio y construcción, D = presión y defensa, V = ocasiones y valor, P = balón parado, J = jugadores.

### Convenciones que aplican a todas las fichas

- **Equipos.** EQ es el equipo analizado: América (`team_id` 1229) en los 91 partidos de Jardine. R es el rival.
- **Unidad.** Yardas. La cancha mide 120 × 80, el centro es [60, 40] y la portería rival está en x = 120. Las coordenadas de cada evento vienen orientadas hacia el ataque de su equipo. Para comparar un evento del rival con uno del EQ se espeja: `x_espejo = 120 − x` y `y_espejo = 80 − y`.
- **Tercios (40 yardas cada uno):** propio x < 40, medio 40 ≤ x < 80, final x ≥ 80. Coinciden con `location_bucket` (`defensive_third`, `midfield_third`, `final_third`), que solo existe en juego abierto.
- **Llaves.** Evento = `(match_id, index)`. Posesión = `(match_id, possession)`. Siempre se ordena por `(match_id, index)`.
- **Tiempo.** `minute` no se reinicia en el segundo tiempo y `timestamp` sí. Las ventanas de segundos (5 s, 10 s) se calculan con `timestamp` convertido a segundos dentro del mismo `period`, no con `minute` y `second`.
- **Juego abierto y balón parado.** Balón parado = `play_pattern` 2 (From Corner), 3 (From Free Kick) o 4 (From Throw In). Juego abierto = `play_pattern` 1, 5, 6, 7 u 8. El 9 (From Kick Off) queda fuera de ambos.
- **Exclusiones globales.** `period` = 5 (tanda de penales); los eventos administrativos (`Half Start`, `Half End`, `Starting XI`, `Tactical Shift`, `Substitution`, `Player On`, `Player Off`, `Injury Stoppage`, `Referee Ball-Drop`, `Camera On`), salvo en las fichas que los usan; y los partidos que no pasan los filtros de calidad de la sección 7.1 del plan.
- **Banderas.** Las columnas booleanas que solo aparecen si son verdaderas (`under_pressure`, `counterpress`, `out`...) se leen como `False` cuando faltan. Un pase sin `pass.outcome` es un pase completo.
- **Reporte.** Toda comparación por contexto muestra su tamaño de muestra (n). xG y OBV son estimaciones de modelos de StatsBomb, no observaciones. Las métricas con 360 solo usan frames con cobertura mínima.

## 2. Umbrales

| Umbral | Valor | Fuente | Estado |
| :--- | :--- | :--- | :--- |
| Contrapresión | 5 s tras perder el balón en juego abierto | `K-Pumas/Framework.pdf` y glosario | Definido |
| Transición | 5 s tras perder (defensiva) o ganar (ofensiva) el balón | `K-Pumas/Framework.pdf` | Definido |
| Contragolpe | `play_pattern` 6; al menos 75% directa; avance de 18 yardas o más; nace fuera del último tercio propio | `K-Pumas/Framework.pdf` | Definido |
| Zona de presión alta | Últimos 40 yardas de la cancha rival | `K-Pumas/Framework.pdf` | Por confirmar |
| Fase de presión | 3 intentos de recuperación o presión en menos de 10 s | `K-Pumas/Framework.pdf` | Por confirmar |
| Posesión válida | 3 pases (o un tiro); no aplica a balón parado | `K-Pumas/Framework.pdf` | Por confirmar |
| Secuencia ofensiva | Cruza el tercio final (x ≥ 80) o termina en tiro | `K-Pumas/Framework.pdf` | Definido |
| Salto de líneas | Pase acertado que cruza uno de tres bloques (defensas, medios, delanteros) | `K-Pumas/Framework.pdf` | Falta la regla de los bloques |
| Cobertura mínima 360 | Sin valor. Provisional: actor visible y al menos 10 jugadores visibles | `K-Pumas/Framework.pdf` | Falta |
| Pase corto del portero | Provisional: menos de 30 yardas | Ninguna | Falta |
| Progresivo | Al menos 10% más cerca de la portería rival | Plan, sección 8 | Definido |
| Zona 14 | 80 ≤ x < 102 y 26.7 ≤ y ≤ 53.3 | Descripción del reporte StatsBomb MLS 360 | Propuesta |
| Ventanas de tiempo | 15 min para `minute_bin` y para antes y después de cambios | Plan, sección 8 | Propuesta |

## Índice

### Fichas

Cada ficha tiene siete campos: qué mide, entrada, cálculo, unidad y nivel, umbrales, qué no se considera y validación.

| Código | Métrica | Grupo | Archivo |
|---|---|---|---|
| [B1](01_objetos_base.md#b1-posesión-válida) | Posesión válida | Objetos base | [01_objetos_base.md](01_objetos_base.md) |
| [B2](01_objetos_base.md#b2-secuencia-ofensiva) | Secuencia ofensiva | Objetos base | [01_objetos_base.md](01_objetos_base.md) |
| [B3](01_objetos_base.md#b3-fase-de-inicio) | Fase de inicio | Objetos base | [01_objetos_base.md](01_objetos_base.md) |
| [B4](01_objetos_base.md#b4-fase-de-construcción) | Fase de construcción | Objetos base | [01_objetos_base.md](01_objetos_base.md) |
| [B5](01_objetos_base.md#b5-fase-de-presión) | Fase de presión | Objetos base | [01_objetos_base.md](01_objetos_base.md) |
| [B6](01_objetos_base.md#b6-contragolpe) | Contragolpe | Objetos base | [01_objetos_base.md](01_objetos_base.md) |
| [C1](02_contexto.md#c1-match_clock-y-minute_bin) | `match_clock` y `minute_bin` | Contexto | [02_contexto.md](02_contexto.md) |
| [C2](02_contexto.md#c2-score_state) | `score_state` | Contexto | [02_contexto.md](02_contexto.md) |
| [C3](02_contexto.md#c3-is_home-rival_id-stage-match_week) | `is_home`, `rival_id`, `stage`, `match_week` | Contexto | [02_contexto.md](02_contexto.md) |
| [C4](02_contexto.md#c4-rival_strength) | `rival_strength` | Contexto | [02_contexto.md](02_contexto.md) |
| [C5](02_contexto.md#c5-numerical_state) | `numerical_state` | Contexto | [02_contexto.md](02_contexto.md) |
| [E1](03_espacio.md#e1-x-y-end_x-end_y-third-cell_6x5-zona-14) | `x`, `y`, `end_x`, `end_y`, `third`, `cell_6x5`, zona 14 | Espacio | [03_espacio.md](03_espacio.md) |
| [E2](03_espacio.md#e2-distancia-y-ángulo-a-portería) | Distancia y ángulo a portería | Espacio | [03_espacio.md](03_espacio.md) |
| [I1](04_inicio_y_construccion.md#i1-possession_start_type) | `possession_start_type` | Inicio y construcción | [04_inicio_y_construccion.md](04_inicio_y_construccion.md) |
| [I2](04_inicio_y_construccion.md#i2-gk_distribution) | `gk_distribution` | Inicio y construcción | [04_inicio_y_construccion.md](04_inicio_y_construccion.md) |
| [I3](04_inicio_y_construccion.md#i3-line_breaking_pass-statsbomb-360) | `line_breaking_pass` (StatsBomb 360) | Inicio y construcción | [04_inicio_y_construccion.md](04_inicio_y_construccion.md) |
| [I4](04_inicio_y_construccion.md#i4-salto_de_lineas-definición-del-equipo) | `salto_de_lineas` (definición del equipo) | Inicio y construcción | [04_inicio_y_construccion.md](04_inicio_y_construccion.md) |
| [I5](04_inicio_y_construccion.md#i5-ball_receipt_in_space-360) | `ball_receipt_in_space` (360) | Inicio y construcción | [04_inicio_y_construccion.md](04_inicio_y_construccion.md) |
| [I6](04_inicio_y_construccion.md#i6-progressive_pass-y-carry_progress) | `progressive_pass` y `carry_progress` | Inicio y construcción | [04_inicio_y_construccion.md](04_inicio_y_construccion.md) |
| [I7](04_inicio_y_construccion.md#i7-build_up_chain) | `build_up_chain` | Inicio y construcción | [04_inicio_y_construccion.md](04_inicio_y_construccion.md) |
| [D1](05_presion_y_defensa.md#d1-press_height-y-high_press) | `press_height` y `high_press` | Presión y defensa | [05_presion_y_defensa.md](05_presion_y_defensa.md) |
| [D2](05_presion_y_defensa.md#d2-ppda) | PPDA | Presión y defensa | [05_presion_y_defensa.md](05_presion_y_defensa.md) |
| [D3](05_presion_y_defensa.md#d3-counterpress-y-regain_5s) | `counterpress` y `regain_5s` | Presión y defensa | [05_presion_y_defensa.md](05_presion_y_defensa.md) |
| [D4](05_presion_y_defensa.md#d4-defensive_line_height) | `defensive_line_height` | Presión y defensa | [05_presion_y_defensa.md](05_presion_y_defensa.md) |
| [D5](05_presion_y_defensa.md#d5-transition) | `transition` | Presión y defensa | [05_presion_y_defensa.md](05_presion_y_defensa.md) |
| [V1](06_ocasiones_y_valor.md#v1-xg-y-uplift-de-ejecución) | xG y uplift de ejecución | Ocasiones y valor | [06_ocasiones_y_valor.md](06_ocasiones_y_valor.md) |
| [V2](06_ocasiones_y_valor.md#v2-xa) | xA | Ocasiones y valor | [06_ocasiones_y_valor.md](06_ocasiones_y_valor.md) |
| [V3](06_ocasiones_y_valor.md#v3-obv-neto) | OBV neto | Ocasiones y valor | [06_ocasiones_y_valor.md](06_ocasiones_y_valor.md) |
| [V4](06_ocasiones_y_valor.md#v4-deep_progressions-y-deep_completions) | `deep_progressions` y `deep_completions` | Ocasiones y valor | [06_ocasiones_y_valor.md](06_ocasiones_y_valor.md) |
| [V5](06_ocasiones_y_valor.md#v5-xgchain-y-xgbuildup) | `xGChain` y `xGBuildup` | Ocasiones y valor | [06_ocasiones_y_valor.md](06_ocasiones_y_valor.md) |
| [P1](07_balon_parado.md#p1-set_piece_type-y-set_piece_phase) | `set_piece_type` y `set_piece_phase` | Balón parado | [07_balon_parado.md](07_balon_parado.md) |
| [P2](07_balon_parado.md#p2-zona-de-remate-y-xg-de-balón-parado-contra-juego-abierto) | Zona de remate y xG de balón parado contra juego abierto | Balón parado | [07_balon_parado.md](07_balon_parado.md) |
| [J1](08_jugadores.md#j1-role_group-y-minutos) | `role_group` y minutos | Jugadores | [08_jugadores.md](08_jugadores.md) |
| [J2](08_jugadores.md#j2-formación-por-periodo-e-impacto-de-los-cambios) | Formación por periodo e impacto de los cambios | Jugadores | [08_jugadores.md](08_jugadores.md) |

### Otras secciones

| Sección | Qué contiene | Archivo |
|---|---|---|
| 11. Puntos por confirmar con el equipo | Los 10 puntos abiertos sobre umbrales y supuestos | [09_puntos_por_confirmar.md](09_puntos_por_confirmar.md) |
| 12. Validaciones cruzadas contra StatsBomb | Tabla de 17 métricas y la columna con que se compara cada una | [10_validaciones_cruzadas.md](10_validaciones_cruzadas.md) |
| 13. Columnas ambiguas del diccionario: aclaración y decisión | Las 45 columnas marcadas `[ambiguo]`, su decisión y cómo confirmarla con datos | [11_columnas_ambiguas.md](11_columnas_ambiguas.md) |
