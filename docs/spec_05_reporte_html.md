# Spec 05: reporte HTML (scripts/05_reporte_html.py)

Estado: v0.3, 22-oct-2026 (decisiones del usuario del día de la entrega: logos en la barra, foto y autores en la portada, `--recursos`, fuera Créditos y toda atribución, una sola nota de penales, Glosario plegado al final, Contexto por hallazgo con figuras de cancha). La v0.2, del 21-oct, trajo Contexto más corto, filas tipo talón, visor de figuras, pestañas sincronizadas, `--textos`, Pillow obligatorio y revisión de nombres crudos por conteo. Dueño: Yordi. Referencia: plan de trabajo, tarea 14.7 de la fase 5; nombres del script, de los argumentos, de la carpeta del HTML, de las anclas y de los códigos de figura aprobados por el usuario el 21-oct (este documento es la referencia); dirección visual «Puertas y sectores» aprobada el 21-oct, con su contrato fuera del repo en `Local/ARCHIVOS_YORDI/diseno_html/`.

## Problema

El equipo entrega el jueves 22 un reporte en HTML que el jurado abre desde el correo. Las cifras salen de las tablas de las fases 2 a 4, y esas tablas todavía pueden cambiar el jueves si alguien vuelve a correr su script. Si el HTML se escribe a mano, cada cambio obliga a buscar y corregir números en el texto, y un número viejo se cuela fácil. `05_reporte_html.py` arma el reporte completo desde las tablas: cada cifra se calcula al generar, así que basta volver a correrlo para que coincida con las tablas. El resultado es un solo archivo HTML que abre con doble clic, sin servidor: CSS y JS en línea, figuras, logos y foto incrustados como WebP en data URI y la figura de tamaños de efecto dibujada en SVG por el propio script. Los títulos usan Big Shoulders Display de Google Fonts, con respaldo de condensadas del sistema para leerse igual sin internet. Los textos del equipo entran como md cuando existen; si no, el espacio se omite y la consola lo avisa. El HTML no dice quién hizo qué: los nombres del equipo solo aparecen en la línea de autores de la portada. Antes de escribir, el script revisa el HTML que armó: que no traiga datos crudos ni credenciales, que no cargue recursos externos (salvo Google Fonts), que no nombre al equipo fuera de los autores, cuánto pesa y qué falta.

## Uso

```
python scripts/05_reporte_html.py --sin-escribir --figuras "../Local/ARCHIVOS_YORDI/figuras_pablo"            # arma y verifica
python scripts/05_reporte_html.py --figuras "../Local/ARCHIVOS_YORDI/figuras_pablo"                           # escribe el HTML
python scripts/05_reporte_html.py --estricto --figuras "../Local/ARCHIVOS_YORDI/figuras_pablo"                # corrida final
```

| Argumento | Por defecto | Qué hace |
| :--- | :--- | :--- |
| `--salida` | `reporte/reporte_jardine_america.html` | Dónde escribe el HTML. |
| `--figuras` | `figuras/` | Carpeta con una subcarpeta por torneo (`Apertura 2023` o `Apertura_2023`) con los PNG de Pablo, y en la raíz las tres figuras de cancha de contexto. Tiene que existir; un PNG que falta se omite (sin su pestaña, o la figura entera si no hay ninguno) con un `AVISO`. |
| `--recursos` | `../Local/ARCHIVOS_YORDI/LOGOS/web` | Carpeta con `america.png`, `unam.png`, `isac.png` y `jardine.webp`, que deja `Local/ARCHIVOS_YORDI/preparar_recursos.py`. Si falta uno, se omite con un `AVISO`. |
| `--framework` | `../Local/ARCHIVOS_PATO/framework` | Carpeta con `05_metricas_finales.md` de Pato (obligatorio) y, opcionales, `01_definiciones_y_supuestos.md` y `04_jugadores.md`. |
| `--textos` | `docs/reporte_textos/` | Carpeta con un md por espacio de texto (ver «Textos del equipo»). Puede no existir. |
| `--sin-escribir` | apagado | Arma y verifica, sin escribir. |
| `--estricto` | apagado | Un texto, una figura o un recurso que falta cuenta como falla. |

Las rutas relativas se leen desde la raíz del repo, así que los valores por defecto funcionan aunque se corra desde otra carpeta.

Códigos de salida: 0 si todo pasó (y se escribió, cuando se pidió); 1 si falta Pillow con WebP o la carpeta de figuras, si falta una tabla, una columna o un archivo del framework (el mensaje dice qué falta, qué script lo produce y de quién es), si la verificación encuentra algo prohibido, si el archivo pasa del límite duro de peso, si falla la escritura o, con `--estricto`, si falta un texto, una figura o un recurso. Si falla la verificación no se escribe nada.

Dependencias: `pillow==12.3.0` está en `requirements.txt`. Sin Pillow con WebP las figuras irían en PNG (unos 19 MB) y el HTML no cabría en el correo, así que el script sale con 1 al inicio y dice la causa (Pillow no está, o está sin WebP) y el remedio (`pip install -r requirements.txt`, o reinstalar Pillow desde las ruedas oficiales).

`reporte/` está en `.gitignore`: el HTML pesa varios MB y cambia en cada corrida, así que se comparte por el Drive, como los datos.

## Entradas

| Insumo | Columnas o partes que usa | Lo produce |
| :--- | :--- | :--- |
| `data/processed/analitica_partidos.parquet` | `match_id`, `torneo`, `stage`, `es_final`, `resultado`, `goles_eq`, `goles_rival`, `presiones`, `presiones_altas_40m`, `ppda_juego_abierto`, `perdidas`, `perdidas_regain_5s`, `{tiros,goles,xg}_{juego_abierto,corner,tiro_libre,banda}_{favor,contra}`, `formacion_1t`, `xg_chain_eq` | `03_tabla_analitica.py` (Yordi), con columnas de Pablo, Pato y Lee |
| `data/processed/analitica_posesiones.parquet` | `match_id`, `es_eq`, `es_administrativa`, `is_valid_possession`, `xg`; las demás solo para saber qué columnas quedan nulas en el rival | `03_tabla_analitica.py` (Yordi) |
| `data/processed/contexto_eventos.parquet` | solo el número de filas (de los metadatos del parquet) | `03_contexto.py` (Yordi) |
| `data/processed/celdas_contexto.parquet` | todas | `04_contexto.py` (Yordi) |
| `data/processed/comparaciones_contexto.parquet` | todas | `04_contexto.py` (Yordi) |
| `scripts/04_contexto.py` | `REPLICAS`, `SEMILLA`, `EFECTO_MIN`, `MIN_PARTIDOS`, `MIN_OBS`, `MIN_PARTIDOS_IC`, `PERCENTILES` y `NIVELES`, leídos con `importlib` | Yordi |
| `data/interim/cobertura_360_por_partido.csv` | `eventos`, `eventos_con_frame`, `pct_con_frame` | `02_limpieza.py` (Yordi) |
| `data/interim/eventos.parquet` | solo `type_name`, `shot_type_name`, `es_equipo_analizado`, `period`, `shot_statsbomb_xg` y `shot_outcome_name`, con `period` < 5 (sin la tanda); para los penales y los autogoles | `02_limpieza.py` (Yordi) |
| `<framework>/05_metricas_finales.md` | las tablas «Definiciones» y «Dónde se calculan» | Pato |
| `<figuras>/<torneo>/*.png` | las 13 figuras por torneo de la lista `FIGURAS` | Pablo (`scripts/graficas.py` de `C/visualizacion`) |
| `<figuras>/contexto_cancha_{marcador,localia,rival}.png` | las tres figuras de cancha de la puerta 5, una imagen cada una con los 91 partidos | Pablo (`scripts/graficas.py`) |
| `<recursos>/{america,unam,isac}.png`, `<recursos>/jardine.webp` | logos de la barra, escudo y foto de la portada | `Local/ARCHIVOS_YORDI/preparar_recursos.py` (fuera del repo) |
| `<textos>/<clave>.md` | opcional: el texto de un espacio | Lee o Pato |
| `.env` y el entorno | solo los valores de `SB_USER` y `SB_PASS`, para buscarlos en el HTML; nunca se imprimen | cada quien |

Los md se leen con `utf-8-sig` (un BOM de Windows no estorba) y de forma genérica: encabezados, párrafos, listas con `- `, tablas, `código` a `<code>`, `**negrita**` a `<strong>` y los enlaces a texto plano. Si falta un archivo del framework, una sección `## n.` con tabla o una de las dos tablas de `05_metricas_finales.md`, la corrida sale con 1 y dice qué falta. Un error al leer un parquet (incluidos los de pyarrow) o al cargar `04_contexto.py` sale como mensaje, sin traceback.

## Cifras (todas calculadas al generar)

| Cifra | Cálculo | Hoy |
| :--- | :--- | :--- |
| Partidos, fase regular, liguilla, finales | filas de `analitica_partidos`; `stage`; `es_final` | 91; 66; 25; 8 |
| G, E, P | signo de `goles_eq` − `goles_rival`; se cuadra G + E + P contra los partidos y contra la columna `resultado` (`AVISO` si no coincide) | 50, 26, 15 |
| Goles a favor y en contra | suma de `goles_eq` y `goles_rival` | 161 y 75 |
| xG a favor y en contra (sin penales) | suma de `analitica_posesiones.xg` por `es_eq` | 137.9 y 79.0 |
| xG por origen | suma de `xg_{origen}_{lado}` de `analitica_partidos` | 110.4 + 17.4 + 8.9 + 1.2 a favor |
| Penales del América y del rival | de `eventos`: `type_name` = Shot y `shot_type_name` = Penalty; tiros, goles (`shot_outcome_name` = Goal) y xG | a favor 15 tiros, 12 goles y 11.8 xG; en contra 5, 5 y 3.9 |
| Autogoles | `type_name` = Own Goal For, separados por `es_equipo_analizado` (True, a favor del América) | 2 a favor y 0 en contra |
| Cuadre de goles | goles por origen + goles de penal + autogoles contra los goles del partido, a favor y en contra; `AVISO` si no cuadra | 147 + 12 + 2 = 161 y 70 + 5 + 0 = 75 |
| Cuadre de xG | suma por origen contra el xG de las posesiones, a favor y en contra; `AVISO` si difieren en más de 0.5 | 0.0 |
| Posesiones sin administrativas | `es_administrativa` False | 18,784 |
| Posesiones válidas del América | `es_eq`, `is_valid_possession` y no administrativa | 3,388 de 9,503 |
| Presiones en los últimos 40 m | suma de `presiones_altas_40m` entre suma de `presiones` | 26.9% |
| Pérdidas recuperadas en 5 s | suma de `perdidas_regain_5s` entre suma de `perdidas` | 6.2% de 3,923 |
| PPDA en juego abierto | media y mediana de `ppda_juego_abierto` | 12.7 y 10.8, n = 91 |
| Eventos | filas de `contexto_eventos`; `AVISO` si no cuadra con la suma de `eventos` de la cobertura | 317,849 |
| Eventos con frame 360 | suma de `eventos_con_frame` entre suma de `eventos` | 89.3% |
| Comparaciones con lectura «diferencia» | `lectura` = `diferencia` y `ajuste` = `simple`, entre todas las `simple` | 24 de 332 (más 1 `indicio`) |
| Formación inicial más usada | moda de `formacion_1t`, con su conteo | 4-2-3-1, 41 de 91 |
| Nivel del IC | `PERCENTILES` de `04_contexto.py` (97.5 − 2.5) | 95% |

Toda división protege el 0 y todo conteo nulo se muestra como «n. d.», para que una tabla vacía no termine en traceback. Los torneos se ordenan por fecha (año y, dentro del año, Clausura antes que Apertura).

## Estructura del HTML

Diez secciones con estas anclas, en el orden del guion del video: `inicio` (portada como boleto), `pregunta`, `marco`, `ofensiva`, `defensa`, `contexto`, `jugadores`, `decisiones`, `limitaciones`, `glosario`. Las puertas 1 a 9 de la barra son las nueve secciones después de la portada. Las secciones no llevan enlace a la siguiente puerta: se navega con la barra.

| Puerta | Cifra grande | Lo demás |
| :--- | :--- | :--- |
| Portada | 91 partidos en el talón | Título en tres líneas, periodo, pregunta del reto, foto recortada de Jardine sobre un disco amarillo; en el talón, el escudo del América junto a los 91 partidos, marcador G-E-P, goles y xG totales y xG por partido; la nota única de penales; al pie del talón, los nombres completos de los autores con «Facultad de Ingeniería, UNAM», sin línea de emisor ni nombre de equipo. En escritorio (desde 1,240 px de ancho) la tipografía grande y los espacios bajan con la altura de la ventana para que la portada completa quepa en la primera vista, y la tarjeta llena esa vista con el mismo aire arriba y abajo (entre 16 y 28 px, con tope de 900 px de alto); se probó a 1280×600, 1366×657, 1536×747 y 1920×950. Debajo de la facultad va el enlace al repo (`URL_REPO`); en el PDF también «Versión interactiva», con el HTML en GitHub Pages (`URL_HTML`), y la foto y los autores van un poco más grandes. |
| 1 | 8 partidos de final, en 4 torneos | T1.1 por torneo. Texto `pato_introduccion`. |
| 2 | (ninguna) | Marco de análisis, en los cuatro bloques de la convocatoria y en ese orden. Definición de objetos: las 8 tarjetas de «Definiciones» de `05_metricas_finales.md`; los 6 contextos con sus niveles (`NIVELES` de `04_contexto.py`, la referencia primero); contrapresión de `01_definiciones_y_supuestos.md` y los objetos de jugadores de `04_jugadores.md`; un enlace a los términos del glosario. Supuestos explícitos: 11 líneas con cifra, todas de constantes, del framework, de `p04` o de las tablas. Coherencia interna: un párrafo y la matriz objeto → figuras, tablas y puertas (plegada, armada de las trazas). Alcance y límites: qué captura y qué queda fuera, con enlace a la puerta 8. |
| 3 | 1.51 xG por partido | Filas tipo talón (goles, posesiones válidas), T3.1, F3.1 a F3.6. Texto `lee_ofensiva`. |
| 4 | 0.87 xG en contra por partido | Filas tipo talón (goles en contra, PPDA, presiones en los últimos 40 m, pérdidas recuperadas en 5 s), T4.1, F4.1 a F4.5. Texto `lee_defensa`. |
| 5 | 24 de 332 | Una tarjeta por contexto (F5.1 a F5.3, las figuras de cancha, en las de marcador, localía y rival); plegadas al final, la figura de tamaños de efecto (F5.4) y T5.1. |
| 6 | 4-2-3-1 | F6.1 y F6.2. Texto `pato_jugadores`. |
| 7 | (ninguna) | Texto `lee_decisiones`. |
| 8 | 10.7% de eventos sin 360 | Limitaciones armadas desde las tablas. Textos `lee_limitaciones` y `pato_cierre`. |
| 9 | (ninguna) | «Glosario y referencias», abierto (sin plegable): T9.1, los términos del reporte (con `id="term-…"`, destino de las líneas «Se basa en»), y «Referencias de las imágenes» (`#referencias`, de `REFERENCIAS_IMAGENES`): foto de Jardine, escudos del América y de la UNAM y logo de ISAC, con su enlace. |

Figuras y tablas llevan código `F{puerta}.{n}` y `T{puerta}.{n}`, numerados en el orden en que aparecen y con un `id` (`f3-1`, `t5-1`). Los códigos de las figuras de Pablo se asignan una sola vez, desde la lista `FIGURAS`.

Contexto (puerta 5):

- Arriba, la cifra grande cuenta solo las comparaciones de ajuste simple (hoy 24 «diferencia» de 332; además 72 pequeñas, 1 indicio y 235 sin diferencia clara). Las 38 de `mitad_x_tercil` repiten comparaciones del marcador, así que no entran en la cifra (lo dice el texto) y siguen en T5.1. La aclaración de que «sin diferencia clara» no prueba que no haya cambio va una sola vez, ahí.
- Una tarjeta por contexto, en el orden de `CONTEXTOS`. Regla del hallazgo principal, fija para que se sostenga si cambian los datos: entre las comparaciones simples del contexto con lectura «diferencia», la de mayor |efecto|; si no hay ninguna, el «indicio» de mayor |efecto|; si tampoco, la tarjeta dice que no hay diferencias claras. El titular sale de `FRASE_METRICA` (una frase de fútbol por métrica, para cuando sube y cuando baja; el PPDA más alto es «presiona menos»): «Perdiendo, el América tiene más el balón». Debajo, la métrica en cada nivel del contexto con su n (nivel del hallazgo en marino, referencia marcada) y la lectura con la diferencia y su IC. Si hay otra «diferencia» de otra métrica en el contexto, va una línea «también» con la de mayor |efecto|. Cierra con el conteo de lecturas del contexto.
- Hoy los hallazgos son: marcador, perdiendo tiene más el balón (65.1% contra 53.8% empatando); localía, de local presiona más alto (59.1 yd contra 55.6; también suma más puntos, 2.27 contra 1.61); rival, contra rivales fuertes anota menos (1.30 goles contra 2.17); minuto, en el añadido del segundo tiempo da menos pases por posesión (3.50 contra 5.39); fase, en liguilla presiona menos (PPDA 15.3 contra 11.6); superioridad, hace más pases progresivos (1.73 contra 1.32).
- Las tarjetas de marcador, localía y rival llevan su figura de cancha (F5.1 a F5.3), una sola imagen de la raíz de `--figuras`, sin pestañas. La primera lleva el pie completo (incluida la aclaración de que su altura de recuperación no es la altura de la presión de la tarjeta de localía); las otras dos remiten a ella.
- Al final, plegadas: F5.4, tamaño de efecto con su IC de cada comparación «diferencia» o «indicio» (ajuste simple), con una banda para |efecto| menor que `EFECTO_MIN` y la n del nivel y de la referencia; y T5.1, la tabla completa (370 filas, con las ajustadas) con filtros por contexto y lectura.

Figuras: cada PNG se reduce a un ancho máximo de 1,400 px y se convierte a WebP con calidad 80, sin recortar. Cada `<img>` lleva `alt`, `width` y `height`, dentro de un marco común (paspartú blanco con filete marino). Las pestañas por torneo siguen el patrón tablist (flechas, Inicio y Fin) y están sincronizadas: elegir un torneo en una figura lo cambia en las 13. A 600 px o menos, tocar una figura abre una vista ampliada a resolución completa, con scroll y un botón «Cerrar»; Escape también cierra y el foco vuelve a la figura. Sin JS se ven todos los torneos.

Tablas: cifras tabulares y la n en su propia columna. En pantallas angostas las tablas se desplazan dentro de su caja y una sombra en el borde avisa que hay más columnas.

Tipografía: títulos en Big Shoulders Display de Google Fonts, con respaldo «Bahnschrift Condensed», «Avenir Next Condensed», «Helvetica Neue Condensed Bold», «Arial Narrow» y «Roboto Condensed». La fuente no se incrusta: así lo pidió el usuario.

### Textos del equipo (`--textos`)

Cada espacio de texto tiene una clave. Si existe `<textos>/<clave>.md`, se muestra en su lugar; si no, el espacio se omite en silencio y la consola imprime un `AVISO` (con `--estricto`, falla). `docs/reporte_textos/LEEME.md` explica el formato y no se publica.

| Clave | De quién | Puerta |
| :--- | :--- | :--- |
| `pato_introduccion` | Pato | 1 |
| `lee_ofensiva` | Lee | 3 |
| `lee_defensa` | Lee | 4 |
| `pato_jugadores` | Pato | 6 |
| `lee_decisiones` | Lee | 7 |
| `lee_limitaciones` | Lee | 8 |
| `pato_cierre` | Pato | 8 |

Los textos pasan por las mismas revisiones que el resto del HTML, incluida la de nombres. Las figuras y los recursos que faltan también se omiten y cuentan para `--estricto`.

## Verificación (dentro del script, después de armar el HTML)

| Revisión | Falla si |
| :--- | :--- |
| Peso | pasa de 18 MB (`AVISO` desde 8 MB). |
| Credenciales | aparece un valor de `SB_USER` o `SB_PASS` (de `.env`, sin comentarios al final de la línea, o del entorno), tal cual o escapado para HTML; aparecen los nombres `SB_USER` o `SB_PASS`; o aparece la palabra `password`. Los valores nunca se imprimen, y si no hay ninguno se avisa. |
| Datos crudos | `event_uuid`, `freeze_frame`, `visible_area`, `player_id`, `match_id` o `possession_team_id` aparecen en el HTML más veces que en los dos md del framework de Pato (lo único que los puede citar; los textos del equipo no tienen exención); una tabla pasa de 400 filas; T5.1 no tiene una fila por comparación de `comparaciones_contexto`. |
| Recursos externos | hay un `<script src>`, un `<img>` que no sea data URI, un `srcset`, un `<link>`, `@import` o `url()` a algo que no sea `fonts.googleapis.com` o `fonts.gstatic.com`, o un `iframe`, `object` o `embed`. |
| Atribución | «Yordi», «Pablo», «Pato» o «Lee» (con mayúscula, como palabra) aparecen fuera de la línea de autores (`<span class="autores">`), sin contar el CSS y el JS. «Lee» al inicio de oración y seguido de minúscula es el verbo y no cuenta. |
| Lo que falta | solo con `--estricto`: un texto, una figura o un recurso. |

Las revisiones de texto se hacen sobre el HTML sin el base64 de las imágenes, para que un valor corto no coincida por azar con los datos de una imagen.

La consola imprime: los cuadres (G-E-P, xG, eventos), las cifras clave, el peso por figura y total, las figuras incrustadas y faltantes (un `AVISO` por figura con los torneos que le faltan), el resultado de cada revisión, los textos del equipo usados, los logos y la foto incrustados y lo que falta.

## Criterios de aceptación

- AC1: `python scripts/05_reporte_html.py --sin-escribir --figuras "../Local/ARCHIVOS_YORDI/figuras_pablo"` termina con 0 y no crea ni cambia `reporte/`.
- AC2: sin `--sin-escribir`, escribe `reporte/reporte_jardine_america.html` (por un archivo temporal en la misma carpeta y `os.replace`), y el resumen dice el peso, las 55 figuras incrustadas (52 por torneo y 3 de cancha), los 4 recursos y lo que falta.
- AC3: el HTML contiene 137.9, 79.0, 161, 89.3 y los puntos de local y visitante (2.27 y 1.61), calculados desde las tablas.
- AC4: con `--estricto` y algo que falta (texto, figura o recurso), termina con 1, lo lista y no escribe.
- AC5: con `--figuras`, `--textos` y `--recursos` en una carpeta vacía, la corrida termina con 0, se imprime un `AVISO` por figura, texto y recurso, y el HTML no trae ningún bloque «Pendiente», figura ni nombre del equipo fuera de los autores.
- AC6: con `--framework` en una ruta que no existe, termina con 1 y un mensaje que dice qué falta y de quién es, sin traceback.
- AC7: si falta una tabla o una columna, termina con 1 y dice qué script la produce y de quién es cada columna.
- AC8: el HTML no trae recursos externos salvo Google Fonts, ni credenciales, ni nombres de columnas crudas más veces que en el framework, ni tablas de más de 400 filas, y T5.1 tiene una fila por comparación; si no, termina con 1 sin escribir.
- AC9: sin JS se ven todas las pestañas, todas las filas de T5.1 y la lista completa de puertas; con JS, la barra marca la puerta visible con la muesca, las pestañas responden a flechas, Inicio y Fin y están sincronizadas entre las 13 figuras, T5.1 se filtra por contexto y lectura, y a 600 px o menos cada figura abre la vista ampliada (Escape cierra y el foco vuelve).
- AC10: a 360 y 375 px no hay scroll horizontal de la página, la barra muestra la puerta actual y un botón con la lista de puertas, los controles miden al menos 44 px y `#contexto` mide menos de un tercio de los unos 9,800 px de la v0.1.
- AC11: cada par de colores de texto cumple AA (4.5:1, o 3:1 en texto grande) y el amarillo solo va sobre marino.
- AC12: el cuadre de xG por origen contra el xG de las posesiones se imprime y da `AVISO` si difiere en más de 0.5; el de G-E-P, si no suma los partidos o no coincide con `resultado`.
- AC13: con `--textos` en una carpeta con dos md de clave válida (uno con lista), esos dos espacios muestran el texto, con la lista en `<ul>`, y los otros 5 se omiten.
- AC14: con `--figuras` en una ruta que no existe, o sin Pillow con WebP, termina con 1 y un mensaje con la causa y el remedio.

## Fuera de alcance

- El contraste con Ortiz y Solari: no forma parte de esta versión; la sección de limitaciones lo dice.
- Escribir los textos de Lee, Pablo y Pato: el script solo los muestra si existen.
- Cambiar las figuras de Pablo: solo se reducen y se convierten a WebP para incrustarlas.
- Recalcular métricas: el script solo suma, cuenta y da formato a lo que ya está en las tablas.
- Escribir en `data/`, en el framework de Pato, en la carpeta de figuras o en la de textos: todo eso se lee y nada más.
- Incrustar la fuente de los títulos: el usuario pidió fuentes web con respaldo del sistema.

## Plan de pruebas

No hay tests ni linter: se verifica corriendo el script. Para forzar fallas, el módulo se carga con `importlib` (su nombre empieza con un dígito) y se llama a `cargar`, `armar` y `verificar` con insumos cambiados.

- AC1 → manual: `--sin-escribir`, código 0, `reporte/` sin cambios (fecha y tamaño).
- AC2 → manual: corrida real y salida completa del resumen.
- AC3 → manual: `grep` de las cinco cifras en el HTML.
- AC4 → manual: `--estricto`, código 1.
- AC5 → manual: `--figuras` en una carpeta vacía.
- AC6, AC14 → manual: `--framework` y `--figuras` en rutas que no existen.
- AC7 → con el módulo cargado, una ruta de tabla inexistente y columnas de más en `FUENTES`.
- AC8 → automático en el script; con el módulo cargado, insertar un `<script src>`, un `<img>` y un `<link>` externos, `match_id` y `event_uuid` una vez más que en el framework, `SB_PASS`, `Password`, una tabla de 401 filas y pedir a T5.1 una fila más.
- AC9, AC10 → Chrome sin interfaz, con la página dentro de un iframe de 390 px (Chrome sin interfaz no baja de unos 500 px) y una copia de prueba que mide el ancho, los controles chicos y el alto de cada sección, y que hace clic en las pestañas y el visor.
- AC11 → manual: verificador de contraste de antislop para cada par de colores.
- AC12 → automático en el script.
- AC13 → manual: `--textos` con una carpeta de prueba en el scratchpad.
- Detector de impeccable: `impeccable detect --json reporte/reporte_jardine_america.html`.

## Desviaciones y decisiones fuera del brief

- La cifra grande de la puerta 5 da 24 de 332, no 25. Con `lectura` = `diferencia` y `ajuste` = `simple` salen 24; el 25 del brief coincide con sumar el único `indicio` simple. El texto de la cifra lo dice aparte.
- Sin antetítulo encima del título (indicación del coordinador y regla del detector de impeccable): al pie del talón solo van los autores y la facultad. Los letreros de sección tampoco llevan etiquetas encima del h2, y los contenedores con fondo o borde tienen al menos 12 px de relleno horizontal, salvo las celdas de tabla en el celular (8 px, pedido en el lote de arreglos para que las tablas quepan).
- «Dónde se calculan» lleva su propio código, T2.2.
- Las cifras grandes van en la condensada de títulos, como en el boceto aprobado, aunque la skill `dataviz` pide la sans del texto; manda el contrato visual.
- F5.1 es una lista HTML con un SVG por fila (`preserveAspectRatio="none"` y trazos que no se deforman), no un solo SVG: así la etiqueta pasa arriba de la barra en el celular. Las filas usan un nombre corto de cada métrica (`ETIQUETA_CORTA`, con la etiqueta completa como respaldo y en el texto alternativo), y el filete entre filas es una sombra interior de 1 px, que el detector de impeccable no confunde con un borde sin relleno.
- En Minuto, las cinco comparaciones de cadena de construcción no salen como lectura: con la regla fija (primero «diferencia», después mayor |efecto| por métrica) quedan en tercer lugar, detrás de pases por posesión y recepciones en espacio. Siguen en F5.1 y en T5.1, y la regla junta los niveles de una métrica en una sola línea cuando le toca.
- T3.1 y T4.1 llevan, después del total, la fila «Penales (aparte)» (tiros, goles y xG, sin %), que no se suma al total. La nota dice cómo se llega a los goles del equipo (por origen, de penal y autogoles); si la suma no da, lo dice sin forzar el cuadre y la consola imprime `AVISO`. Los penales y autogoles se leen de `data/interim/eventos.parquet` porque los mapas y el xG de Pablo y de las posesiones no los traen.
- Las figuras de Pablo ya van sin penales; el pie de cada una explica cómo leerla. Las de cancha de contexto traen título y leyendas dentro de la imagen. Los umbrales (`REJILLA_FLUJO`, `UMBRALES_RED` y `MIN_MINUTOS_RADAR`) se copian de `scripts/graficas.py` de Pablo a constantes del script y los pies los toman de ahí; si Pablo los cambia, hay que actualizarlas.
- El detector de impeccable deja una nota (`repeating-stripes-gradient`): son las franjas de pasto del boleto, del contrato visual.
- Logos (decisión del usuario del 22-oct, contra el «sin escudos ni logos» del DESIGN.md de la v0.2): el escudo del América va a la izquierda de la barra como enlace a la portada, en lugar de una marca de texto, y a la derecha van los de la UNAM e ISAC. Los nombres de las puertas se ven desde 1,240 px; entre 860 y 1,239 px solo van los números. Bajo 860 px el escudo se queda en la barra, junto a la puerta actual y el botón, y los de la UNAM e ISAC van al pie del menú «Puertas» abierto.
- Foto de la portada: `preparar_recursos.py` quita el fondo casi blanco de `JARDINE_SIN_FONDO.png` (relleno desde los bordes y, en la orilla de unos 8 px, alfa por proyección del color sobre el del interior y sin el blanco mezclado), la reduce a 900 px de alto y la guarda en WebP con alfa; deja una vista previa sobre marino para revisar el halo. En la portada la foto se apoya en el borde inferior del boleto, sobre un disco amarillo (amarillo sobre marino), y el boleto se apila (talón abajo) desde 1,239 px para que el título no se apriete.
- Sin atribución: se quitaron la puerta Créditos, los bloques «Pendiente», la nota del xG en cadena y el origen de las figuras. El framework de Pato cita quién calcula cada cosa; al leerlo, `SIN_ATRIBUCION` quita esas menciones («03_defensa.py (Pablo)» queda «03_defensa.py», «Falta que Pato y Pablo lo confirmen» queda «Falta confirmarlo») sin tocar los archivos. Si aparece una forma nueva, la revisión de nombres falla y hay que agregarla.
- Penales: una sola nota, en el talón de la portada. Las demás menciones («xG sin penales» en etiquetas, notas y pies) se quitaron; la fila «Penales (aparte)» de T3.1 y T4.1 se queda.
- Ronda de UX del 22-oct: el texto de cada puerta va antes de su tabla y sus figuras (3 y 4). La cifra de la puerta 5 dice solo cuántas comparaciones muestran diferencia clara y enlaza a «Cómo comparamos por contexto» (`id="como-leer"`, que se abre al seguir el enlace). La tarjeta de rival define el nivel (tercio de su torneo por diferencia de xG por partido en fase regular, de `c4_rival_strength`). Los niveles de las tarjetas siguen el orden de las columnas de su figura y las figuras de cancha se amplían también en escritorio.
- T5.1 empieza por Métrica, Contexto, Nivel, Lectura, Diferencia e IC; ya no lleva «Se cuenta en». El filtro de lectura va de «diferencia» a «sin diferencia clara». `fmt_dif` y `fmt_efecto` agregan decimales cuando un extremo redondearía a 0 sin serlo (+0.003, no +0.0).
- Limitaciones: una sola lista, la del md, más lo que el md no cubre (hoy, la fase de presión); si el md falta, el script pone la lista completa. El Glosario (plegado) trae T9.1, T9.2 sin la columna de scripts y T9.3 con los términos. `SIN_MARCAS` quita del framework las marcas internas («Ver pendiente N», «Plan 7.x», nombres de funciones) y `verificar()` falla si reaparecen, si aparece un script del pipeline, una «ficha X1» o `is_valid_possession`.
- La puerta 1 cuenta finales, no partidos de final: 4 finales (8 partidos de ida y vuelta, 2 por torneo).
- Puerta 2 (22-oct, decisión del usuario): «Datos y método» pasa a «Marco de análisis» (`#marco`) con el framework a la vista. El plegable «Cómo comparamos por contexto» (`#como-leer`) va a la puerta 5, debajo de la cifra que lo enlaza; la limpieza y los partidos fuera de los 91 van al Glosario. Las tarjetas se agrupan con `GRUPOS_MARCO`; una métrica nueva del framework sin grupo sale en «Otras» con un `AVISO`. `verificar()` falla si un `href="#x"` no tiene destino. La puerta 8 suma de `02_restricciones_y_riesgos.md` lo que no cubría: que el xG y el OBV son modelos y que el 360 depende del área visible.
- Traza al marco (22-oct, convocatoria): cada figura (`BASE_FIGURA`) y cada tabla con código (`base=` en `tabla()`, y `base_contexto()` para F5.4 y T5.1) declara los objetos, supuestos o términos en que se basa, con los ids de la puerta 2 (`def-…`, `sup-…`) o del glosario (`term-…`). Bajo su pie va la línea «Se basa en» con enlaces, y la matriz de la puerta 2 sale de esas mismas trazas. `verificar()` falla si una figura o tabla con código no tiene objetos o si cita un id que no existe en el HTML.
- Supuesto del 360: el framework (`02_restricciones_y_riesgos.md`) dice que las métricas espaciales «solo usan frames con una cobertura mínima», pero el contrato (C19) dice que la regla provisional de jugadores visibles es solo informativa y que ninguna tabla se filtra con ella. El reporte dice lo que hacen las tablas: solo eventos con frame, sin filtro por jugadores visibles.
- Glosario solo con términos (22-oct, decisión del usuario): salen los plegables de decisiones de limpieza y de partidos fuera de los 91, y con ellos la lectura de `03_decisiones_de_limpieza.md`, `partidos_excluidos.csv` y del inventario de la descarga. Ninguna línea «Se basa en» apuntaba a ellos.
- Ritmo vertical: escala `--esp-1` a `--esp-6` (4, 8, 16, 24, 32 y 48 px) en `:root`. Texto ↔ tabla, figura, plegable o grupo de tarjetas: `--esp-4`. Pie, nota y «Se basa en» van pegados a su figura o tabla (`--esp-2`) y separados de lo que sigue (`--esp-3`). Los h3 llevan `--esp-6` arriba y `--esp-3` abajo, y los plegables `--esp-4` arriba y abajo. A 1440 px la página crece unos 800 px (de 39,299 a 40,108 con los plegables cerrados).
- Figuras de cancha con pestañas (22-oct, decisión del usuario): F5.1 a F5.3 llevan primero «91 partidos» (la imagen de la raíz de `--figuras`, la vista de las cifras de las tarjetas) y después una pestaña por torneo (`<figuras>/<torneo>/contexto_cancha_{marcador,localia,rival}.png`), con el mismo markup de pestañas y «Ver en grande». Elegir un torneo lo cambia en todas las figuras; «91 partidos» solo existe en estas 3, así que elegirlo mueve solo a ellas. Al cargar, las demás figuras abren en el primer torneo y estas 3 en «91 partidos» (`data-inicio`); el estado de la pestaña no se guarda. Si falta una imagen por torneo, la pestaña se omite con un `AVISO` (si faltan todas, queda solo la de 91 partidos) y `--estricto` falla. El pie completo de F5.1 explica la pestaña de 91 partidos, que por torneo hay menos datos y se lee con cautela, que la línea punteada (promedio de los 91 partidos) es la misma en todas y la regla de «pocos datos» (`MIN_PARTIDOS_CANCHA` = 5 partidos o `MIN_MINUTOS_CANCHA` = 90 minutos, la misma de `Cambio_Partidos.py`). Cada figura de cancha nombra en su pie los niveles que no se dibujan, calculados desde `analitica_partidos` (`is_home`, `rival_strength_tercil` y `minutos_*`): hoy, rival débil en Clausura 2025 (4 partidos, 416 min).
- Ronda antislop (22-oct): la puerta 8 se llama «Conclusiones y limitaciones» (ancla `limitaciones` sin cambio) y abre con `pato_cierre`, antes de la cifra del 360 y de la lista de límites. En las puertas 1 y 6 el texto del md va antes de la tabla o de las figuras, como en la 3 y la 4. `verificar()` falla si una línea «Se basa en» repite una etiqueta (`sup-rival` se llama «Rival por tercio de xG»). Las tablas de los md alinean a la derecha, con cifras tabulares, las celdas que empiezan con cifra o signo; su región accesible lleva el título de la sección (o la primera columna, si una sección trae dos tablas); y solo la columna de filas lleva `min-width:12ch`, con los encabezados en varias líneas, para que quepan a 1,440 px. F5.4 marca |efecto| = 0.2 con dos líneas punteadas. El glosario suma «360 (frame)» y «Tamaño de efecto» (con `EFECTO_MIN` de `04_contexto.py`).

## Reporte en PDF (`scripts/06_reporte_pdf.py`)

```
python scripts/05_reporte_html.py --figuras "../Local/ARCHIVOS_YORDI/figuras_pablo" --estricto
python scripts/06_reporte_pdf.py --entrega   # reporte/reporte_jardine_america.pdf y copia de los dos a entrega/
```

- Chrome sin interfaz imprime el HTML con `--headless=new --print-to-pdf --no-pdf-header-footer` y `--virtual-time-budget` para que carguen Big Shoulders Display e imágenes. En Windows se lanza con `Start-Process` de PowerShell, porque lanzado desde Python no escribe el PDF. Busca Chrome (o Edge) en las rutas habituales y acepta `--chrome`.
- Imprime una copia temporal del HTML: sin `loading="lazy"`, para que entren todas las imágenes, y con las figuras opacas en JPEG (calidad 82), porque Chrome guarda los WebP sin pérdida y el PDF pasaba de 35 MB. Logos y foto, con transparencia, se quedan igual. El HTML no cambia.
- Página de 1,280 × 1,810 px (`PAGINA_PDF`; ancho de escritorio con proporción A4) con márgenes de 48 px arriba y abajo (`MARGEN_PDF`), salvo la portada, que llena la página 1. Las media queries del celular y de tableta solo aplican en pantalla (`screen and (max-width:…)`), y el bloque de escritorio también aplica en impresión: el PDF se ve como el HTML a 1,280 px.
- En impresión: fuera la barra, las pestañas, los filtros y «Ver en grande»; todos los paneles uno debajo de otro con el nombre de su torneo o «91 partidos»; todos los plegables abiertos menos T5.1, que no va (en su lugar, una nota que solo se ve al imprimir dice que está en el HTML); cada puerta y cada figura por torneo empiezan página; las imágenes se acotan a 720 px de alto para que quepan dos paneles por página; tarjetas, paneles, cuadros y filas no se parten, y los encabezados de tabla se repiten. Los títulos llevan un relleno arriba para que la tilde de una mayúscula al inicio de página no caiga en la anterior.
- Revisa el resultado: cuenta las páginas, dice el peso y comprueba que el PDF traiga Big Shoulders Display. Hoy son 65 páginas y 9.9 MB. Con `--entrega` copia el HTML y el PDF a `entrega/`, que sí se versiona (`.gitignore` solo excluye `reporte/`).
