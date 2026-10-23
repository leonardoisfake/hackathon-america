# Textos del reporte HTML

Aquí van los textos de Lee y Pato para el reporte. Cada espacio de texto del HTML tiene una clave; si en esta carpeta existe `<clave>.md`, `scripts/05_reporte_html.py` lo pone en su lugar y, si no existe, el espacio se omite y la consola lo avisa (con `--estricto`, la corrida falla).

| Clave | De quién | Dónde aparece | Qué falta |
| :--- | :--- | :--- | :--- |
| `pato_introduccion` | Pato | Puerta 1, La pregunta y el entrenador | Introducción: el reto, quién es Jardine en el América y cómo leer el reporte, con las palabras del video. |
| `lee_ofensiva` | Lee | Puerta 3, Ofensiva | Resultados de ataque y patrones o clusters de las posesiones. |
| `lee_defensa` | Lee | Puerta 4, Defensa | Resultados de defensa. |
| `pato_jugadores` | Pato | Puerta 6, Jugadores | Rotación, formaciones y cambios. |
| `lee_decisiones` | Lee | Puerta 7, Qué se puede decidir con esto | Indicadores clave con su n, tabla de métricas y recomendaciones. |
| `lee_limitaciones` | Lee | Puerta 8, Limitaciones y cierre | Limitaciones de las métricas de ataque y defensa. |
| `pato_cierre` | Pato | Puerta 8, Limitaciones y cierre | Cierre: respuesta corta a la pregunta del reto. |

Cómo se escribe: Markdown simple. Se aceptan encabezados (`#` sale como subtítulo de la puerta), párrafos, listas con `- `, tablas, `código` y **negrita**; los enlaces quedan como texto. Las cifras se escriben con su n. El texto pasa por las mismas revisiones que el resto del HTML, así que no puede llevar nombres de columnas crudas como `match_id`, credenciales ni nombres del equipo (el HTML no dice quién hizo qué; los autores van solo en la portada).

Después de agregar o cambiar un md, se vuelve a correr `python scripts/05_reporte_html.py --figuras <carpeta de figuras>`. Este LEEME no se publica en el reporte.
