[Volver al índice](README.md)

# 3. Decisiones de limpieza

## Resumen general

Cada decisión que toma `scripts/02_limpieza.py` al pasar los datos crudos a `data/interim/`, en una tabla con variable, problema, acción y justificación. Las secciones van de los filtros de partidos al contrato de datos. Esta tabla se convierte en la sección de metodología del HTML. El detalle columna por columna está en el contrato de datos (`docs/contrato/`).

## 1. Partidos

| Variable | Problema | Acción | Justificación |
| :--- | :--- | :--- | :--- |
| `play_status` | Partidos con juego no normal | Solo pasan los Normal. Los demás se excluyen, se imprimen y se guardan en `partidos_excluidos.csv` (`limpiar_partidos`) | Métricas de estilo |
| `match_status` | Partido no disponible | Solo pasan los available | Sin datos completos no hay análisis |
| `collection_status` | Errores de video (NoVidError, IncVidError, PoorVidError) | Solo pasan los Complete. Esos errores son valores de este campo, así que quedan fuera | El plan decía «marcar o descartar»; el código descarta |
| `match_status_360` | Partido sin 360 | Solo pasan los available | Todo el análisis espacial depende del 360 |
| Cualquiera de los 4 campos | Valor nulo | Un nulo cuenta como «no cumple» y excluye el partido | No se asume calidad por falta de dato |
| `match_id` | Repetido tras filtrar | La corrida se detiene con error | Un partido duplicado inflaría todos los conteos |

## 2. Tiempo y orden

| Variable | Problema | Acción | Justificación |
| :--- | :--- | :--- | :--- |
| `match_id`, `index` | Orden de eventos | La tabla de eventos se ordena siempre por ambos (`limpiar_eventos`) | Es la llave única; el orden define las secuencias |
| `minute`, `second` | `minute` no se reinicia en el 2.º tiempo | Se crea `match_second = minute × 60 + second` | Un solo reloj numérico por partido. Ver pendiente 1 |
| Eventos administrativos | No son juego | Se marcan con `es_administrativo = True` y no se borran. La lista cerrada (C5) es: Half Start, Half End, Starting XI, Tactical Shift, Substitution, Player On, Player Off, Injury Stoppage, Referee Ball-Drop y Camera On | Las métricas tácticas filtran `es_administrativo == False`. Formaciones y cambios se leen de estas mismas filas |
| Periodo 5 (penales) | Los penales no son juego abierto | **Sin tratamiento en este script.** Ver pendiente 2 | Plan 7.3.18 |

## 3. Banderas, resultados vacíos y nulos

| Variable | Problema | Acción | Justificación |
| :--- | :--- | :--- | :--- |
| Banderas (`under_pressure`, `counterpress`, `out`, `off_camera`, ventajas) | Solo aparecen cuando son verdaderas | Se rellenan con False solo las columnas del contrato con relleno = False. Esa regla solo se permite en columnas boolean, y `contrato.validar()` falla si queda algún nulo en ellas | Ausente significa «no aplica» |
| `pass.outcome.name` | Vacío significa pase completo | `pass_completed = True` si está vacío, solo en eventos tipo Pass; en otros tipos queda nulo | En StatsBomb, resultado vacío = éxito |
| `ball_receipt.outcome.name` | Vacío significa recepción buena | `receipt_ok`, mismo criterio, solo en `Ball Receipt*` | Igual que arriba |
| xG, campos de pase, OBV, `control_degree`, etc. | Existen solo en ciertos eventos | **No se imputan.** Los nulos se conservan | Nulo legítimo: se analiza cada subconjunto por separado |
| Columna cruda ausente | Una columna del contrato no viene en el crudo | Se crea vacía solo si el contrato dice `puede_faltar`; si no, la corrida se detiene. Las creadas vacías se listan en `calidad_limpieza.csv` | Evita que una columna faltante pase desapercibida |
| `pass_completed`, `receipt_ok` | Deben ser nulos fuera de pases y recepciones | Sin relleno. El código los deja nulos en eventos que no son del tipo | Un False aquí contaría como pase fallido a cualquier evento que no sea pase |

## 4. Tipos y texto

| Variable | Problema | Acción | Justificación |
| :--- | :--- | :--- | :--- |
| Ids con vacíos (`player.id`, `position.id`, etc.) | Llegan como decimales | Se convierten al tipo del contrato (p. ej. Int64). Si un valor no se puede convertir, la corrida se detiene (`_cast`) | No se fuerzan valores en silencio |
| Booleanos | Una columna booleana donde se espera número | Error, no se convierte | Evita mezclar True/False con 1/0 |
| Texto (string, category) | Espacios o tabuladores | strip a todo el texto, incluidos los `event_uuid` | Homologar nombres y llaves |
| Fechas | Pueden llegar como número o con zona horaria | Solo se acepta texto ISO 8601 sin zona horaria, guardado como `datetime64[us]` | Un número se leería como epoch sin avisar |
| Columnas vacías o no documentadas (`attendance`, `account_id`, etc.) | Ruido | Solo entran las columnas del contrato; el resto se descarta | Plan 7.3.5 (verificar en contrato) |
| Tipos | Dtypes inconsistentes | Solo hay seis tipos válidos: Int64, float64, boolean, string, category y datetime64[us]. Cualquier otro detiene la carga del contrato | Un tipo por columna, el mismo en todas las tablas |
| Columnas no contempladas | Ruido, vacías o sin documentar | El contrato es una **lista blanca**: lo que no está se descarta, y `validar()` marca como «sobrante» cualquier columna extra | Cubre el descarte de `attendance`, `account_id` y similares |
| `puede_faltar` | Columna cruda ausente | Debe ser True o False en todas las filas del CSV. Si es True, la columna se crea vacía y se reporta; si es False y falta, la corrida se detiene | Ninguna columna falta sin que quede registrado |

## 5. Coordenadas

| Variable | Problema | Acción | Justificación |
| :--- | :--- | :--- | :--- |
| `location` | Viene como lista [x, y] en texto | Se separa en `x` y `y`. Si falta, queda NaN y **no se imputa** | Cerca del 1% no trae ubicación; se excluye de los mapas |
| `pass/carry/shot/goalkeeper.end_location` | Cuatro columnas de destino | Se unifican en `end_x`, `end_y`. `end_z` sale solo del tiro. Si un evento trae más de un destino, la corrida se detiene | El contrato admite un solo destino por evento |
| `x_eq`, `y_eq`, `end_x_eq`, `end_y_eq` | Los eventos del rival vienen orientados hacia su propio ataque | Los eventos del rival se voltean (120 − x, 80 − y). Los del equipo analizado quedan igual. Si no hay equipo, NaN | Todo se ve desde el equipo analizado. **No está en el plan** |
| Unidad | Yardas o metros | Todo en **yardas** (cancha de 120 × 80; `visible_area_yd2`) | Unidad nativa de StatsBomb. Falta declararla en el framework |

## 6. Estructuras anidadas y 360

| Variable | Problema | Acción | Justificación |
| :--- | :--- | :--- | :--- |
| `freeze_frame` | Lista anidada | Se expande a `frames_360`: una fila por jugador visible (`jugador_idx`, `teammate`, `actor`, `keeper`, `x`, `y`) | Plan 7.3.7. No trae ids de jugador |
| `es_equipo_analizado` (en frames) | Saber de qué equipo es cada jugador visible | Es del equipo analizado si el evento lo es y el jugador es compañero, o si ninguno de los dos lo es. Nulo si falta algo | Se deduce sin ids de jugador |
| `visible_player_counts` | Lista anidada | `n_visibles_equipo` y `n_visibles_rival` (`frames_360_evento`). El «equipo» es **quien hace el evento**, no el analizado | Sirve para filtrar por cobertura. Ver pendiente 4 |
| `visible_area` | Polígono | `visible_area_yd2` (área en yd², fórmula del polígono). NaN si tiene menos de 3 puntos | Mide cuánta cancha ve la cámara |
| `lineup` (alineaciones) | JSON anidado | `alineaciones`: una fila por jugador (datos, goles, asistencias, rating HOPS) | Plan 7.3.7 |
| `lineup.positions` | Varias posiciones por jugador | `posiciones`: una fila por tramo (`posicion_idx`, posición, from, to, motivo de entrada y de salida) | Base para minutos y roles |
| `positions.to` | Vacío en ~55% de los casos | **Se deja tal cual.** No se rellena aquí | Ver pendiente 3 |
| Stats de lineups | Pueden venir vacías | Se copian tal cual | Plan 7.3.15: se calculan desde eventos |

## 7. Equipo analizado, torneo y línea base

| Variable | Problema | Acción | Justificación |
| :--- | :--- | :--- | :--- |
| `team.id` vs `possession_team` | El actor puede ser distinto de quien tiene la posesión | `es_equipo_analizado` = `team.id` igual a `equipo_id`. **No usa `possession_team`** | Plan 7.3.8: las acciones se atribuyen con team |
| `torneo`, `fase`, `es_play_in`, `es_final` | Etiquetas de ronda poco confiables; `season_id` junta Apertura y Clausura | Se copian de partidos a cada evento. **La regla que los deriva no está en este script** | Plan 7.3.16 y 7.3.17. Falta confirmar dónde se calculan |
| `team_match_stats_liga` | Línea base de la liga | Se limpia sin filtrar por los partidos del equipo | Sirve para `rival_strength` |

## 8. Controles de calidad y escritura

| Control | Qué hace |
| :--- | :--- |
| Contrato | `contrato.validar()` revisa columnas faltantes, sobrantes, tipos y nulos en columnas con relleno |
| Cobertura por partido | Exige eventos, ambas tablas 360, `player_match_stats`, ids de equipo no nulos, exactamente local y visitante en alineaciones y `team_match_stats`, y eventos con `es_equipo_analizado` no nulo. **Un hueco detiene toda la corrida; no excluye el partido** |
| Llaves y huérfanos | Cualquier llave duplicada o fila sin padre detiene la corrida |
| Escritura | Si todo pasa, escribe en una carpeta temporal y reemplaza archivo por archivo. Si algo falla, no se escribe nada |
| Reportes | `calidad_limpieza.csv`, `cobertura_360_por_partido.csv` y `partidos_excluidos.csv` |
| Cobertura 360 | Cuenta eventos con frame y frames sin conteo. La regla provisional de Lee (actor visible y al menos 10 jugadores visibles) es **solo informativa, no filtra nada** |

## 9. Contrato de datos (v0.2)

| Elemento | Regla |
| :--- | :--- |
| Archivo | `docs/contrato/contrato_datos.csv`, con las columnas tabla, columna, tipo, origen, regla, relleno y puede_faltar |
| origen | Nombre de la columna cruda. Si no existe, se prueba con el nombre de la columna limpia |
| regla | Referencia a una decisión numerada (C2, C5, C18, C19). El CSV las documenta |
| relleno | Vacío o False, y solo en columnas boolean |
| Validación | `validar()` revisa faltantes, sobrantes, tipo incorrecto y nulos en columnas con relleno. Un fallo detiene la corrida sin escribir nada |
| Fechas | Se comparan exactas: sin zona horaria y con resolución de microsegundos |
| Texto | string y category se limpian con strip; las categorías deben ser texto |
