# Spec 03: tabla analítica (scripts/03_tabla_analitica.py)

Estado: v0.2, 20-oct-2026 (correcciones de la revisión doble: lo que Lee solo calcula para el América queda nulo en el rival, nulos de 360 y de OBV, cuadres por equipo y validaciones de Pato y del pivote). Dueño: Yordi. Referencia: plan de trabajo, sección 14 ("Yordi, datos: ensamblado final de la tabla analítica"); nombres y columnas aprobados por el usuario el 20-oct (este documento es la referencia); salidas de `03_contexto.py` (`docs/spec_03_contexto.md`), `03_ataque.py` (Lee), `03_defensa.py` (Pablo) y `03_jugadores.py` (Pato).

## Problema

Cada integrante dejó sus métricas de la fase 3 en tablas propias, con llaves y niveles distintos: Lee por evento y por posesión, Pablo por posesión de balón parado y por partido, Pato por periodo, por momento de cambio y por partido. Para la fase 4 y para las gráficas hace falta una sola tabla por posesión y una sola por partido, con el contexto de la fase 3 y las métricas de todos, sin que nadie tenga que repetir los cruces. `03_tabla_analitica.py` junta esas tablas, suma por posesión y por partido las que vienen por evento, y valida que todo cuadre (llaves, partidos, huérfanos, contexto repetido igual al nuestro, cuadres entre niveles). No recalcula ninguna métrica: solo cuenta, suma, pivota y pega.

## Salidas (nombres aprobados por el usuario el 20-oct, en constantes al inicio del script)

- `data/processed/analitica_posesiones.parquet`: una fila por posesión de `contexto_posesiones` (19,053), llave (`match_id`, `possession`), 48 columnas.
- `data/processed/analitica_partidos.parquet`: una fila por partido de `contexto_partidos` (91), llave `match_id`, 119 columnas.

Base de eventos entre niveles: por posesión cuenta solo lo que hizo el equipo con el balón (eventos cuyo `team_id` es el `possession_team_id`); por partido cuenta todo lo que hizo cada equipo (`team_id` del evento, periodos 1 a 4, posesiones administrativas incluidas). La diferencia entre los dos niveles son los eventos de cada equipo sin el balón, y el script la cuadra columna por columna.

`analitica_posesiones`, en este orden:

| Columnas | De dónde | Regla |
| :--- | :--- | :--- |
| Todas las de `contexto_posesiones` (26) | Yordi | Sin cambios. |
| `is_home` | `contexto_partidos` | Por `match_id`. |
| `possession_start_type` | `ataque_posesiones` (Lee) | Sin cambios; existe para los dos equipos. |
| `build_up_chain`, `xg_chain`, `xg_buildup` | `ataque_posesiones` (Lee) | Sin cambios en el América; nulos en las posesiones del rival (`es_eq` False), porque Lee solo los calcula para el América. |
| `n_pases_progresivos`, `n_conducciones_progresivas`, `n_deep_progressions`, `n_deep_completions` | `ataque_eventos` (Lee) | Conteo de `progressive_pass`, `carry_progress`, `deep_progression` y `deep_completion` en True, en los eventos del equipo con el balón (periodos 1 a 4). Int64. Nulos en las posesiones del rival, porque Lee solo los calcula para el América. |
| `n_pases_rompe_lineas`, `n_recepciones_espacio` | `ataque_eventos` (Lee) | Conteo de `line_breaking_pass` (True solo en `Pass`) y `ball_receipt_in_space` (True solo en `Ball Receipt*`), igual que arriba, para los dos equipos. Int64. Son banderas del 360: un evento sin frame trae nulo y no cuenta. Si el equipo tuvo en la posesión eventos del tipo que aplica y ninguno trae valor, el conteo queda nulo (contrato C21: un conteo 360 vacío es nulo, no cero). Si no tuvo eventos de ese tipo, vale 0. |
| `xa` | `ataque_eventos` (Lee) | Suma de `xa` en los eventos del equipo con el balón. float64. Un `xa` nulo quiere decir "no es pase que termina en tiro", así que la suma con 0 es correcta. |
| `obv_neto` | `ataque_eventos` (Lee) | Suma de `obv_net`, igual que arriba, con al menos un valor: nula si ningún evento del equipo en la posesión trae `obv_net`. float64. |
| `set_piece_type`, `con_saque`, `es_directo`, `x_saque`, `y_saque`, `set_piece_phase_max` | `balon_parado_posesiones` (Pablo) | Sin cambios, left join; nulos si la posesión no es de balón parado. |
| `tiros_bp`, `xg_bp`, `goles_bp` | `balon_parado_posesiones` (Pablo) | Su `tiros`, `xg` y `goles` (solo lo que nace del saque). Llevan `_bp` porque chocan con `n_tiros` y `xg` de la posesión. Int64, float64 e Int64, fijados antes del left join. |

En las columnas que salen de `ataque_eventos`, una posesión sin eventos propios vale 0 en los conteos y en `xa`, y nulo en `obv_neto`.

`analitica_partidos`, en este orden:

| Columnas | De dónde | Regla |
| :--- | :--- | :--- |
| Todas las de `contexto_partidos` (18) | Yordi | Sin cambios. |
| `match_date`, `resultado` y las 48 métricas de `defensa_partidos` (`COLS_DEFENSA`) | Pablo | Sin cambios. Su contexto repetido (`torneo`, `fase`, `es_final`, `rival_id`, `rival_nombre`, `es_local`, `is_home`, `stage`, `rival_strength_tercil`) se valida y no se copia. |
| `{medida}_{tipo}_{lado}` (30) | `balon_parado_partidos` (Pablo) | Pivote de `saques`, `tiros`, `xg` y `goles`; `tipo`: `Corner` → `corner`, `Free Kick` → `tiro_libre`, `Throw In` → `banda`, `Juego abierto` → `juego_abierto`; `lado`: `a_favor` → `favor`, `en_contra` → `contra`. Conserva los tipos de origen (Int64 y float64). Sin `saques_juego_abierto_*` (ver desviaciones). |
| `pases_progresivos_eq`, `conducciones_progresivas_eq`, `deep_progressions_eq`, `deep_completions_eq` | `ataque_eventos` (Lee) | Eventos del América (por `team_id`, periodos 1 a 4) con la bandera en True. Int64. |
| `cadenas_construccion_eq` | `ataque_posesiones` (Lee) | Posesiones del América (`possession_team_id`), sin administrativas, con `build_up_chain` True. Int64. |
| `pases_rompe_lineas_{eq,rival}`, `recepciones_espacio_{eq,rival}` | `ataque_eventos` (Lee) | Conteo por `team_id` del evento, periodos 1 a 4, con la misma regla de 360: nulo solo si el equipo tuvo eventos del tipo y ninguno trae valor. Int64. |
| `xa_{eq,rival}` | `ataque_eventos` (Lee) | Suma por `team_id` del evento. float64. |
| `obv_neto_{eq,rival}` | `ataque_eventos` (Lee) | Suma por `team_id` del evento, nula si ningún evento del equipo trae `obv_net`. float64. |
| `xg_chain_eq` | `ataque_posesiones` (Lee) | Suma de `xg_chain` de las posesiones del América (`possession_team_id`), sin administrativas. float64. No hay `xg_chain_rival` (ver desviaciones). |
| `formacion_1t`, `formacion_2t` | `formacion_por_periodo` (Pato) | La táctica predominante (la de más minutos) de cada mitad, según Pato; periodos 1 y 2. El tiempo extra no tiene columna. Entero en origen; queda Int64. |
| `cambia_formacion` | `formacion_por_periodo` (Pato) | `formacion_1t` distinta de `formacion_2t`. boolean. |
| `n_cambios`, `n_momentos_cambio`, `minuto_primer_cambio` | `momentos_de_cambio` (Pato) | Suma de `n_cambios`, número de filas y mínimo de `minute` por partido. Los dos primeros valen 0 en un partido sin cambios y el tercero queda nulo. Int64. Supuesto: `momentos_de_cambio` es solo del América (así lo describe la propuesta y no trae equipo). |
| `cambios_vs_previo` | `onces_iniciales` (Pato) | Sin cambios (float64 como en origen); nulo en el primer partido. |

## Insumos

| Tabla | Ruta | La produce |
| :--- | :--- | :--- |
| `contexto_posesiones`, `contexto_partidos` | `data/processed/` | `03_contexto.py` (Yordi) |
| `eventos` (solo `match_id`, `index`, `team_id`, `possession`, `period`, `type_name`) | `data/interim/` | `02_limpieza.py` (Yordi) |
| `ataque_posesiones`, `ataque_eventos` | `data/processed/` | `03_ataque.py` (Lee) |
| `balon_parado_posesiones`, `defensa_partidos`, `balon_parado_partidos` | `data/processed/` | `03_defensa.py` (Pablo) |
| `formacion_por_periodo`, `momentos_de_cambio`, `onces_iniciales` | `data/processed/jugadores/` | `03_jugadores.py` (Pato) |

Cada insumo se lee solo con las columnas que usa; las de `defensa_partidos` están listadas en `COLS_DEFENSA` y `QUITAR_DEFENSA`. Si falta el archivo o una columna, la corrida falla diciendo qué script lo produce y de quién es.

## Criterios de aceptación

- AC1: `python scripts/03_tabla_analitica.py` termina con código 0 y escribe las dos tablas; `--sin-escribir` termina con código 0 y no cambia nada en `data/processed/`.
- AC2: `analitica_posesiones` tiene 19,053 filas y exactamente las 48 columnas de arriba en ese orden; `analitica_partidos` tiene 91 filas y exactamente las 119 columnas de arriba en ese orden. La lista esperada se arma con las constantes del script y cualquier diferencia (columna de más, de menos u otro orden) es falla dura. Llave única; las filas y el orden de la base no cambian.
- AC3: si falta un insumo o una de sus columnas (incluidas las 50 de `COLS_DEFENSA`), la corrida falla con código 1 y un mensaje con la ruta, el script que la produce y su autor.
- AC4: la llave de cada insumo es única y sin nulos: `ataque_posesiones`, `balon_parado_posesiones` (`match_id`, `possession`); `ataque_eventos`, `eventos` (`match_id`, `index`); `defensa_partidos`, `onces_iniciales` (`match_id`); `balon_parado_partidos` (`match_id`, `lado`, `set_piece_type`); `formacion_por_periodo` (`match_id`, `period`); `momentos_de_cambio` (`match_id`, `idx_evento`). Si no, falla con el conteo.
- AC5: los insumos por partido (`defensa_partidos`, `balon_parado_partidos`, `formacion_por_periodo`, `onces_iniciales`) traen exactamente los 91 `match_id` de `contexto_partidos`; `momentos_de_cambio` puede traer menos pero ninguno de fuera. `balon_parado_partidos` trae las 8 combinaciones de lado y tipo en cada partido. `formacion_por_periodo` trae los periodos 1 y 2 de cada partido. `formacion` y `minute` de Pato son enteros. Si no, falla.
- AC6: ningún huérfano por la llave completa: `ataque_eventos` y `eventos` tienen las mismas llaves; `ataque_posesiones`, `balon_parado_posesiones` y la posesión de cada evento de los periodos 1 a 4 existen en `contexto_posesiones`; los `match_id` de los insumos por partido existen en `contexto_partidos`. Si no, falla con el conteo y ejemplos.
- AC7: el contexto repetido coincide con el nuestro, o la corrida falla: en `defensa_partidos`, `torneo`, `es_final`, `rival_id`, `rival_nombre`, `is_home`, `stage`, `rival_strength_tercil`, `es_local` contra `is_home` y `fase` contra `stage` (`regular` ↔ `regular`, `liguilla` ↔ `fase final`); en `balon_parado_posesiones`, `team_id` contra `possession_team_id`, `lado` contra `es_eq`, `period`, `score_state`, `minute_bin`, `rival_strength_tercil`, `stage` y `numerical_state_cat` contra el signo de `numerical_state`; en `balon_parado_partidos`, `team_id` (1229 a favor, `rival_id` en contra), `torneo`, `es_final` y `fase`; en Pato, `es_local`, `torneo` y `fase` de `momentos_de_cambio`, y `torneo`, `fase` y `match_date` de `onces_iniciales` (la fecha contra la de `defensa_partidos`).
- AC8: lo que Lee solo calcula para el América no trae valores del rival, o la corrida falla en lugar de borrarlos en silencio: ningún True del rival en `progressive_pass`, `carry_progress`, `deep_progression`, `deep_completion` ni `build_up_chain`, y ninguna posesión del rival con `xg_chain` o `xg_buildup` > 0 fuera de las excepciones conocidas (`EXCEPCIONES_CADENA_RIVAL`, hoy (3889699, 25), que se anula y se avisa). Todas esas columnas quedan nulas en las posesiones del rival.
- AC9: cuadres que se imprimen como `[OK]` o fallan:
  - Pases progresivos contra el insumo sin tocar: los `progressive_pass` True del América en todo `ataque_eventos`, menos los del periodo 5, menos los que caen en posesiones del rival, es la suma de `n_pases_progresivos`; sin restar los del rival, es la suma de `pases_progresivos_eq`.
  - Por cada columna de los dos equipos (`pases_rompe_lineas`, `recepciones_espacio`, `xa`, `obv_neto`) y cada equipo: la suma en las posesiones del equipo más los eventos del equipo sin el balón es igual al total por partido. El script imprime las tres cifras, entre ellas la diferencia de `obv_neto`.
  - `xg_chain_eq` por partido es igual a la suma de `xg_chain` de las posesiones del América en la salida y en `ataque_posesiones`.
- AC10: los tipos de las dos salidas están en Int64, float64, boolean, string, category o datetime64; si no, falla.
- AC11: el script imprime cuántos eventos del periodo 5 descarta, cuántos eventos del equipo sin el balón no cuentan para la posesión, cuántos eventos de cada tipo vienen sin 360 y cuántas posesiones y partidos quedan con nulo por 360 o por OBV.
- AC12: con los mismos insumos, dos corridas dan tablas idénticas.
- AC13: la escritura sigue el esquema de `03_contexto.py`, con carpeta temporal `data/processed/.tmp_tabla_analitica_*`: si falla una validación no se escribe nada, se revisa que ningún destino esté bloqueado y se reemplaza archivo por archivo.
- AC14: `saques_juego_abierto_favor` y `saques_juego_abierto_contra` no van en la salida; si alguna trae un valor en `balon_parado_partidos`, la corrida falla.
- Cuadres informativos (no fallan, imprimen `[OK]` o `AVISO`): las posesiones de balón parado de Pablo contra `es_balon_parado` y `resultado` de Pablo contra `goles_eq` y `goles_rival`.

## Fuera de alcance

- Recalcular o corregir métricas de Lee, Pablo o Pato — el script confía en sus tablas; si algo no cuadra, falla y lo dice. Los hallazgos van a su autor.
- Tocar `03_ataque.py`, `03_defensa.py`, `03_jugadores.py`, `04_contexto.py` o nada de `Local/`.
- Decidir qué métricas entran a `METRICAS` de `04_contexto.py` — se acuerda después, con estas dos tablas como fuente.
- Tablas por evento, pérdida, transición, fase de presión, jugador o cambio — se quedan como están y se cruzan con su contexto por la llave cuando haga falta.
- Contexto del grupo de contraste — todos los insumos son del América con Jardine.

## Plan de pruebas

No hay tests ni linter: se verifica corriendo el script y leyendo las salidas. Para forzar fallas, el módulo se carga con `importlib` (su nombre empieza con un dígito) y se envuelve su función `leer` para alterar un insumo en memoria, o se cambia `INSUMOS`:

```python
import importlib.util, sys

spec = importlib.util.spec_from_file_location("ta", "scripts/03_tabla_analitica.py")
ta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ta)
original = ta.leer
ta.leer = lambda n: original(n).iloc[1:] if n == "onces_iniciales" else original(n)
sys.argv = ["03_tabla_analitica.py"]
ta.main()  # debe devolver 1 sin escribir
```

- AC1 → manual: corrida completa y `--sin-escribir` con `data/processed/` listado antes y después.
- AC2, AC10 → automáticos en el script; manual: `pd.read_parquet(...)`, `shape`, `dtypes` y llave única.
- AC3 → manual: ruta de un insumo de Lee que no existe; una columna de más en `balon_parado_partidos` y en `defensa_partidos`.
- AC4 → manual: insumo con filas repetidas.
- AC5 → manual: un partido de menos en `onces_iniciales`; a un partido le falta el periodo 2 en `formacion_por_periodo`; `formacion` como float.
- AC6 → manual: una posesión o un partido que no existe en la base; un evento sin su par.
- AC7 → manual: `rival_id` cambiado en `defensa_partidos`; `period` cambiado en `balon_parado_posesiones`.
- AC8 → manual: un `progressive_pass` True y un `build_up_chain` True en el rival; `xg_chain` > 0 en otra posesión del rival.
- AC9, AC11 → manual: leer la salida de consola.
- AC12 → manual: dos corridas y `assert_frame_equal`.
- AC13 → manual: un destino de solo lectura da código 1 sin reemplazar nada.
- AC14 → manual: un `saques` con valor en una fila de juego abierto.
- Contraste → manual: recalcular con pandas, por separado, los conteos y sumas por posesión (con la regla de 360 y de OBV), los totales por partido, el pivote y las columnas de Pato.

## Desviaciones y decisiones fuera del brief

- Lo que Lee solo calcula para el América queda nulo en el rival (regla aprobada en la propuesta): los cuatro conteos de progresión, `build_up_chain`, `xg_chain` y `xg_buildup`. Por eso no hay `xg_chain_rival`: saldría vacía. `possession_start_type` sí existe para los dos equipos y no cambia.
- Banderas del 360 (`line_breaking_pass`, `ball_receipt_in_space`): Lee les pone valor (False si no aplica) en todos los eventos con frame y nulo en los que no tienen; True solo aparece en `Pass` y en `Ball Receipt*`. Un evento nulo no cuenta, y el conteo queda nulo solo cuando el equipo tuvo eventos de ese tipo y ninguno trae valor (contrato C21). Si no hubo eventos de ese tipo, el conteo es 0 de verdad. La misma regla vale por partido.
- `obv_neto` se suma con al menos un valor (nula si ningún evento del equipo trae `obv_net`), por posesión y por partido. `xa` se suma con 0 porque su nulo quiere decir "no es pase que termina en tiro".
- `saques_juego_abierto_favor` y `saques_juego_abierto_contra` se omiten siempre (en juego abierto no hay saque y hoy vienen nulas en todas las filas); si alguna trae un valor, la corrida falla. Quedan 30 columnas del pivote.
- `formacion_1t` y `formacion_2t` quedan Int64 y no int64: int64 no está entre los tipos permitidos de la salida. Int64 es el mismo entero con nulos. `cambios_vs_previo` se queda float64, como en origen.
- El contexto repetido de Pato (`momentos_de_cambio` y `onces_iniciales`) también se valida, igual que el de Pablo.
- `cadenas_construccion_eq` y `xg_chain_eq` van por `possession_team_id` y dejan fuera las posesiones administrativas. Hoy no cambia nada: las 269 administrativas tienen `build_up_chain` nulo y `xg_chain` 0.
- `resultado` de Pablo contra los goles y las posesiones de balón parado contra `es_balon_parado` son cuadres informativos, no fallas.
- Las columnas de `balon_parado_posesiones` que no se copian (`index`, `period`, `t`, `team_id`, `lado`, `n_saques`, `termina_en_tiro`, `tiros_posesion` y su contexto) siguen en su tabla. `index` es el evento del saque, no el primero de la posesión.

## Hallazgo para Lee

1. `xg_chain`, `xg_buildup` y `build_up_chain` solo existen para el América: en el rival `build_up_chain` viene nulo y `xg_chain`/`xg_buildup` en 0. De 9,414 posesiones del rival solo una trae `xg_chain` > 0: (3889699, 25), con 0.007098 y sin xG propio. El script la anula como al resto del rival y la avisa; si aparece otra, falla.
2. `xg_buildup` es una copia de `xg_chain`: son iguales en las 19,053 posesiones (149.611 en el América).
3. `xg_chain` incluye penales, a diferencia del `xg` de la posesión de la fase 3: en las 15 posesiones del América con penal, `xg_chain` − `xg` es exactamente el xG del penal (0.7835 cada uno).

## Resultado de la corrida (20-oct, v0.2)

Código 0, menos de 1 s (`--sin-escribir` igual, sin cambios en `data/processed/`). Dos corridas dan tablas idénticas (`assert_frame_equal`).

- `analitica_posesiones`: 19,053 filas y 48 columnas (26 + 22). `analitica_partidos`: 91 filas y 119 columnas (18 + 101: `match_date`, `resultado`, 48 de defensa, 30 del pivote, 14 de Lee y 7 de Pato).
- Insumos: llave única y sin nulos en los 11; los 91 partidos en los insumos por partido y en `momentos_de_cambio`; reticula completa de balón parado; periodos 1 y 2 de formación en cada partido; ningún huérfano; contexto repetido igual al nuestro en las cinco tablas que lo traen.
- Eventos: 317,825 de los periodos 1 a 4 y 24 del periodo 5 descartados; 45,714 eventos son del equipo sin el balón. Sin 360 en su tipo: 11,354 `Pass` y 7,219 `Ball Receipt*`.
- Nulos: 1,405 posesiones con `n_pases_rompe_lineas` nulo y 705 con `n_recepciones_espacio` nulo (sin 360); 397 con `obv_neto` nulo. Ningún partido con nulo en las columnas de Lee.
- Cuadres:
  - Pases progresivos: 12,829 True del América en `ataque_eventos`, 0 en la tanda, 0 en posesiones del rival; 12,829 en posesiones y 12,829 por partido.
  - `pases_rompe_lineas`: América 7,902 en posesiones + 302 sin el balón = 8,204; rival 7,037 + 276 = 7,313.
  - `recepciones_espacio`: América 36,009 + 220 = 36,229; rival 28,827 + 197 = 29,024.
  - `xa`: América 102.89 + 0 = 102.89; rival 57.88 + 0 = 57.88.
  - `obv_neto`: América 185.25 en posesiones − 5.28 sin el balón = 179.98 por partido; rival 126.71 − 8.62 = 118.10.
  - `xg_chain_eq`: 149.611 en las tres fuentes.
  - Informativos: las 7,381 posesiones de balón parado de Pablo son las de `es_balon_parado`; `resultado` cuadra con los goles en los 91 partidos.
- Contraste independiente con pandas: conteos y sumas por posesión (con las reglas de 360 y OBV), nulos del rival, balón parado por posesión, totales por partido, 1,193 cadenas, 40 filas del pivote y las columnas de Pato (24 cambios de formación, 417 sustituciones, 1 `cambios_vs_previo` nulo) cuadran con un recálculo aparte.
- Fallas forzadas, todas con código 1, un mensaje sin traceback y las salidas sin cambios: insumo faltante, columna faltante en `balon_parado_partidos` y en `defensa_partidos`, llave repetida, posesión huérfana, partido huérfano, partido faltante, periodo 2 faltante en formación, `formacion` como float, `rival_id` y `period` cambiados, True del rival en `progressive_pass` y en `build_up_chain`, `xg_chain` > 0 en otra posesión del rival, `saques` con valor en juego abierto, un evento sin su par y un destino de solo lectura.

### Cumplimiento

- AC1 a AC14: cumplidos (ver arriba).
- Fuera de alcance: respetado. No se tocaron scripts de otros, `04_contexto.py` ni `Local/`.

## Alternativas descartadas

- Copiar el contexto de cada autor y dejar que choquen los nombres — duplicaría columnas que hoy coinciden al 100% y cualquier diferencia futura quedaría escondida; se valida y se toma el nuestro.
- Anular en silencio cualquier valor del rival en las métricas del América — si Lee algún día las calcula para el rival, se perderían sin aviso; la corrida falla y lo dice (salvo la excepción conocida, que se avisa).
- Pegar los eventos sin filtrar por el equipo con el balón — mezclaría en la posesión los toques del rival (por ejemplo, su `obv_net`).
- Contar los nulos del 360 como False (conteo 0) — diría "no rompió líneas" donde no se sabe; el contrato (C21) pide nulo.
- Dejar `xg_chain_rival` en 0 — se leería como "el rival no generó xG en cadena" cuando la métrica no existe para él.
- Omitir cualquier columna del pivote que venga toda nula — escondería un problema de Pablo; solo se omiten `saques_juego_abierto_*`, que no pueden existir.
