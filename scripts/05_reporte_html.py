"""Reporte HTML (fase 5, tarea 14.7): arma el reporte del equipo en un solo archivo HTML desde las tablas.

Uso:
    python scripts/05_reporte_html.py --sin-escribir --figuras "../Local/ARCHIVOS_YORDI/figuras_pablo"
    python scripts/05_reporte_html.py --figuras "../Local/ARCHIVOS_YORDI/figuras_pablo"
    python scripts/05_reporte_html.py --estricto --figuras "../Local/ARCHIVOS_YORDI/figuras_pablo"   # corrida final

Lee las cifras de data/processed/ (analitica_*, contexto_eventos, celdas_ y comparaciones_contexto), la
cobertura 360 y los penales de data/interim/, el framework de Pato (--framework), las figuras de Pablo
(--figuras: una subcarpeta por torneo y las de contexto en la raiz), los logos y la foto de la portada
(--recursos, de Local/ARCHIVOS_YORDI/preparar_recursos.py) y los textos del equipo que ya existan (--textos, un md
por espacio). Ninguna cifra se escribe a mano: al volver a correrlo, cada numero del HTML coincide con las tablas.
El HTML abre con doble clic, sin servidor: CSS y JS en linea, imagenes como WebP en data URI (necesita Pillow con
WebP, que esta en requirements.txt). El HTML no dice quien hizo que: los autores van en una sola linea de la
portada, y un texto, figura o logo que falte se omite con un AVISO en la consola.

Antes de escribir revisa el HTML armado: peso (meta 8 MB, limite 18 MB), credenciales, nombres de columnas crudas
(solo se aceptan las que cita el framework de Pato, y no mas veces que ahi), tablas de mas de 400 filas (T5.1 debe
tener una fila por comparacion), recursos externos (solo Google Fonts), nombres del equipo fuera de la linea de
autores y lo que falta. Las rutas relativas se leen desde la raiz del repo. Detalle en docs/spec_05_reporte_html.md.

Codigos de salida: 0 si todo paso (y se escribio, cuando se pidio); 1 si falta Pillow con WebP, la carpeta de
figuras, una tabla, una columna o un archivo del framework, si la verificacion encuentra algo prohibido, si el
archivo pasa del limite de peso, si fallo la escritura o, con --estricto, si falta un texto, una figura o un
recurso. Si falla la verificacion no se escribe nada.
"""
import argparse
import base64
import html
import importlib.util
import io
import os
import re
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

try:  # Pillow con WebP: sin el no se pueden reducir las figuras y el HTML no cabe en un correo
    from PIL import Image, features
    PILLOW, WEBP = True, bool(features.check("webp"))
except ImportError:
    Image, PILLOW, WEBP = None, False, False

ROOT = Path(__file__).resolve().parents[1]
# nombres aprobados por el usuario el 21-oct; ver docs/spec_05_reporte_html.md
SALIDA = "reporte/reporte_jardine_america.html"
FIGURAS_DIR = "figuras/"
RECURSOS_DIR = "../Local/ARCHIVOS_YORDI/LOGOS/web"
FRAMEWORK_DIR = "../Local/ARCHIVOS_PATO/framework"
TEXTOS_DIR = "docs/reporte_textos/"
PREFIJO_TMP = ".tmp_05_reporte_"

# figuras: ancho maximo y calidad WebP; peso del HTML
ANCHO_MAX = 1400
CALIDAD_WEBP = 80
META_MB = 8
LIMITE_MB = 18
MAX_FILAS_TABLA = 400
ID_T51 = "t5-1-tabla"  # T5.1 tiene una fila por comparacion; se compara contra len(comps), no contra el limite
NUM = ' class="num"'  # celda numerica: alineada a la derecha y con cifras tabulares
TOL_CUADRE_XG = 0.5

CRUDOS = ["event_uuid", "freeze_frame", "visible_area", "player_id", "match_id", "possession_team_id"]
CREDENCIALES = ["SB_USER", "SB_PASS"]
HOSTS_PERMITIDOS = {"fonts.googleapis.com", "fonts.gstatic.com"}


@dataclass(frozen=True)
class Fuente:
    ruta: str  # relativa a la raiz del repo
    script: str  # quien la produce
    dueno: str
    columnas: tuple = ()


FUENTES = {
    "partidos": Fuente("data/processed/analitica_partidos.parquet", "03_tabla_analitica.py", "Yordi", (
        "match_id", "torneo", "stage", "es_final", "resultado", "goles_eq", "goles_rival", "presiones",
        "presiones_altas_40m", "ppda_juego_abierto", "perdidas", "perdidas_regain_5s", "formacion_1t",
        "xg_chain_eq", "is_home", "rival_strength_tercil", "minutos_ganando", "minutos_empatando",
        "minutos_perdiendo") + tuple(f"{m}_{o}_{lado}" for m in ("tiros", "goles", "xg")
                               for o in ("juego_abierto", "corner", "tiro_libre", "banda")
                               for lado in ("favor", "contra"))),
    "posesiones": Fuente("data/processed/analitica_posesiones.parquet", "03_tabla_analitica.py", "Yordi", (
        "match_id", "es_eq", "es_administrativa", "is_valid_possession", "xg")),
    "eventos": Fuente("data/processed/contexto_eventos.parquet", "03_contexto.py", "Yordi"),
    "celdas": Fuente("data/processed/celdas_contexto.parquet", "04_contexto.py", "Yordi", (
        "metrica", "etiqueta_metrica", "unidad", "agregacion", "nivel_dato", "contexto", "nivel", "es_referencia",
        "valor", "ic_inf", "ic_sup", "n_obs", "n_partidos", "inestable")),
    "comparaciones": Fuente("data/processed/comparaciones_contexto.parquet", "04_contexto.py", "Yordi", (
        "metrica", "contexto", "nivel", "referencia", "ajuste", "diferencia", "dif_ic_inf", "dif_ic_sup",
        "tipo_efecto", "efecto", "efecto_ic_inf", "efecto_ic_sup", "n_obs_nivel", "n_obs_ref", "n_partidos_nivel",
        "n_partidos_ref", "inestable", "lectura")),
    "cobertura": Fuente("data/interim/cobertura_360_por_partido.csv", "02_limpieza.py", "Yordi", (
        "eventos", "eventos_con_frame", "pct_con_frame")),
    "penales": Fuente("data/interim/eventos.parquet", "02_limpieza.py", "Yordi", (
        "type_name", "shot_type_name", "es_equipo_analizado", "period", "shot_statsbomb_xg", "shot_outcome_name")),
}
# columnas de analitica_partidos que vienen de otra persona (para decir de quien es lo que falta)
ORIGEN_COLUMNA = [
    (re.compile(r"^(presiones|ppda|perdidas|tiros_|goles_(juego|corner|tiro|banda)|xg_(juego|corner|tiro|banda))"),
     "03_defensa.py (Pablo)"),
    (re.compile(r"^formacion_"), "03_jugadores.py (Pato)"),
    (re.compile(r"^xg_chain"), "03_ataque.py (Lee)"),
]
FRAMEWORK_METRICAS = "05_metricas_finales.md"
FRAMEWORK_DEFS = "01_definiciones_y_supuestos.md"  # opcional: definiciones que no estan entre las 8 finales
FRAMEWORK_JUGADORES = "04_jugadores.md"  # opcional: objetos de la puerta de jugadores
OBJETOS_01 = ("Contrapresión",)  # de FRAMEWORK_DEFS, las que el reporte usa
JUGADORES_MARCO = {"J1": "Rol y minutos jugados", "J2a": "Formación y once inicial", "J2b": "Momento de cambio"}
PARAMETROS_04 = ("REPLICAS", "SEMILLA", "EFECTO_MIN", "MIN_PARTIDOS", "MIN_OBS", "MIN_PARTIDOS_IC", "PERCENTILES",
                 "NIVELES")

# puertas de la barra: ancla, numero, etiqueta corta, titulo del letrero y que contiene
PUERTAS = [
    ("pregunta", 1, "Pregunta", "La pregunta y el entrenador",
     "Qué pide el reto, quién es Jardine en el América y qué partidos entran."),
    ("marco", 2, "Marco", "Marco de análisis",
     "Cómo leemos el juego: las fases y los umbrales que usa todo el reporte."),
    ("ofensiva", 3, "Ofensiva", "Ofensiva",
     "Cuánto genera el América, de qué origen salen sus tiros y cómo mueve el balón."),
    ("defensa", 4, "Defensa", "Defensa",
     "Cuánto concede, dónde defiende y cómo presiona después de perder el balón."),
    ("contexto", 5, "Contexto", "Contexto",
     "Qué cambia según el marcador, la localía, el rival, el minuto, la fase y la superioridad numérica."),
    ("jugadores", 6, "Jugadores", "Jugadores",
     "Formación inicial, zonas y perfil de los jugadores con más minutos."),
    ("decisiones", 7, "Decisiones", "Qué se puede decidir con esto",
     "Indicadores, métricas y recomendaciones para el cuerpo técnico."),
    ("limitaciones", 8, "Conclusiones", "Conclusiones y limitaciones",
     "Qué respondemos al reto y hasta dónde llegan los datos."),
    ("glosario", 9, "Glosario", "Glosario y referencias",
     "Los términos que usa el reporte y de dónde salen las imágenes."),
]

PREGUNTA_RETO = ("¿Qué principios definen al equipo en ofensiva y en defensa, cómo se mantienen a lo largo del "
                 "tiempo y cómo ajusta Jardine según el rival, el marcador, la localía o el minuto?")
# unico lugar del HTML con nombres del equipo: nombres completos y facultad (decision del usuario del 22-oct)
AUTORES = ("Leonardo Alan Lee Robles", "Patricio Alfaro Domínguez", "Pablo Abad Gonzalez", "Yordi Josue Jiménez Ayala")
FACULTAD = "Facultad de Ingeniería, UNAM"
NOMBRES_EQUIPO = ("Yordi", "Lee", "Pablo", "Pato", "Leonardo", "Patricio")
NOTA_PENALES = ("Ningún tiro ni xG de este reporte incluye penales. Los penales se cuentan aparte, en su propia fila "
                "de las tablas de xG por origen.")

# espacios de texto: clave (nombre del md en --textos) y que falta; si el md no existe, el espacio se omite
PENDIENTES = {
    "pato_introduccion": ("Pato", "Introducción: el reto, quién es Jardine en el América y cómo leer este reporte, "
                                  "con las mismas palabras del video."),
    "lee_ofensiva": ("Lee", "Resultados de ataque y patrones o clusters de las posesiones."),
    "lee_defensa": ("Lee", "Resultados de defensa."),
    "pato_jugadores": ("Pato", "Rotación, formaciones y cambios: quién juega, cuándo cambia el dibujo y qué pasa "
                               "después de cada cambio."),
    "lee_decisiones": ("Lee", "Indicadores clave con su n, tabla de métricas y recomendaciones para el cuerpo técnico."),
    "lee_limitaciones": ("Lee", "Limitaciones de las métricas de ataque y defensa."),
    "pato_cierre": ("Pato", "Cierre: respuesta corta a la pregunta del reto, con las palabras del video."),
}


@dataclass(frozen=True)
class Recurso:
    archivo: str  # en --recursos
    alt: str


# logos y foto de la portada, de Local/ARCHIVOS_YORDI/preparar_recursos.py
RECURSOS = {
    "america": Recurso("america.png", "Escudo del Club América"),
    "unam": Recurso("unam.png", "Escudo de la UNAM"),
    "isac": Recurso("isac.png", "Logo de ISAC"),
    "jardine": Recurso("jardine.webp", "André Jardine con la ropa de entrenamiento del América, de brazos cruzados"),
}
# imagenes tomadas de internet: que es, texto del enlace y direccion completa (puerta 9, «Referencias de las imagenes»)
REFERENCIAS_IMAGENES = [
    ("Fotografía de André Jardine, recortada y sin fondo",
     "img.asmedia.epimg.net/resizer/v2/JDEKGIPHDNF7HE6SDAIWUY442A.jpg",
     "https://img.asmedia.epimg.net/resizer/v2/JDEKGIPHDNF7HE6SDAIWUY442A.jpg?auth=5151c6670a60c1a9ea62ce2a2efae6e7fe4fe8c"
     "7364cb9188b559a85150d0bb6&width=1200&height=675&focal=1296%2C918"),
    ("Escudo del Club América", "1000marcas.net/club-america-logo", "https://1000marcas.net/club-america-logo/"),
    ("Escudo de la UNAM", "cch-oriente.unam.mx/secretarias/general/imprenta/logos.html",
     "https://www.cch-oriente.unam.mx/secretarias/general/imprenta/logos.html"),
    ("Logo de ISAC, sin el fondo verde", "luma.com/e3thtn3j", "https://luma.com/e3thtn3j"),
]
# el escudo del America va a la izquierda de la barra como enlace a la portada; a la derecha, UNAM e ISAC
LOGOS_BARRA = ("unam", "isac")

# el framework cita quien calcula cada cosa; en el HTML no va ninguna atribucion, asi que se quita al leerlo
SIN_ATRIBUCION = [
    (re.compile(r"\s*\((?:Yordi|Lee|Pablo|Pato)\)"), ""),
    (re.compile(r"\s+de (?:Yordi|Lee|Pablo|Pato)\b"), ""),
    (re.compile(r"\bque había tomado (?:Yordi|Lee|Pablo|Pato)\b"), "que se había tomado"),
    (re.compile(r"\b(?:Yordi|Lee|Pablo|Pato) agrupa\b"), "Se agrupan"),
    (re.compile(r"\bsus fases\b"), "las fases"),
    (re.compile(r"\bFalta que (?:Yordi|Lee|Pablo|Pato)(?:,? (?:y )?(?:Yordi|Lee|Pablo|Pato))* lo confirmen\b"),
     "El reporte usa 10 s como tiempo máximo entre un intento y el siguiente"),
]
# marcas de trabajo interno del framework (pendientes, numeros del plan, scripts y columnas) que no van al HTML
SIN_MARCAS = [
    (re.compile(r"\s*Ver pendiente \d+\.?"), ""),
    (re.compile(r"Plan 7(?:\.\d+)+(?:\s+y\s+7(?:\.\d+)+)?(?:\s*\([^)]*\))?[.:]?\s*"), ""),
    (re.compile(r"\s*\(`_?[a-z_]+`\)"), ""),  # nombres de funciones
]
# lo que no puede verse en el HTML: marcas internas, scripts del pipeline, fichas y columnas del glosario
PROHIBIDO_VISIBLE = [
    (re.compile(r"Ver pendiente \d"), "«Ver pendiente N»"), (re.compile(r"\bPlan 7\.\d"), "«Plan 7.x»"),
    (re.compile(r"El plan decía"), "«El plan decía»"), (re.compile(r"Falta confirmarlo"), "«Falta confirmarlo»"),
    (re.compile(r"\b\d\d_[a-z_]+\.py\b"), "nombre de un script"), (re.compile(r"\bficha [A-Z]\d"), "«ficha X1»"),
    (re.compile(r"\bis_valid_possession\b"), "is_valid_possession"),
]


# parametros de scripts/graficas.py de Pablo: bins=(8, 6) en flujo_pases, red_pases(min_pases_jugador=100,
# min_pases_enlace=15) y radar_posiciones(min_minutos_escala=300)
REJILLA_FLUJO = (8, 6)
UMBRALES_RED = (100, 15)  # pases por jugador y por conexion
MIN_MINUTOS_RADAR = 300
ZONAS_FLUJO = REJILLA_FLUJO[0] * REJILLA_FLUJO[1]
PCT_ZONA = f"{100 / ZONAS_FLUJO:.1f}%"


@dataclass(frozen=True)
class Figura:
    archivo: str  # {torneo} se reemplaza por el torneo con guion bajo
    puerta: int
    titulo: str
    pie: str  # descriptivo y neutral; los umbrales de Pablo salen de las constantes de arriba
    alt: str  # que se ve, para lectores de pantalla
    contexto: str = ""  # figura de una sola imagen en la raiz de --figuras, en la tarjeta de ese contexto


FIGURAS = [
    Figura("2_flujo_pases.png", 3, "Hacia dónde circula el balón",
           "Dirección promedio de los pases completados del América que salen de cada zona. Cuanto más oscuro el "
           f"marino, más pases salen de ahí; si se repartieran parejo entre las {ZONAS_FLUJO} zonas, a cada una le "
           f"tocaría {PCT_ZONA}. La escala es la misma en los cuatro torneos y el América ataca de izquierda a "
           "derecha.",
           "Cancha dividida en zonas, cada una con una flecha que indica la dirección promedio de los pases; el "
           "marino es más oscuro donde salen más pases"),
    Figura("5_red_pases.png", 3, "Red de pases",
           "Posición promedio de cada jugador en el torneo y sus conexiones de pase. El tamaño del punto sigue los "
           "pases completados del jugador, y el grosor de la línea, los pases entre los dos. Solo entran los "
           f"jugadores con al menos {UMBRALES_RED[0]} pases completados y las conexiones de al menos "
           f"{UMBRALES_RED[1]} pases.",
           "Red de nodos sobre la cancha: cada nodo es un jugador en su posición promedio y cada línea, una "
           "conexión de pases"),
    Figura("3_tiros_ataque.png", 3, "Tiros a favor",
           "Tiros del América en el torneo. El tamaño del círculo es el xG del tiro. Los goles van en "
           "marino con borde amarillo y los tiros sin gol, huecos. Arriba de la cancha están los tiros, los goles "
           "y el xG del torneo.",
           "Media cancha de ataque con un círculo por tiro, más grande cuanto mayor es su xG; los goles van en "
           "marino con borde amarillo"),
    Figura("2_balon_parado_a_favor.png", 3, "Balón parado a favor",
           "Tiros que nacen de un córner o de un tiro libre del América. La línea va del lugar del saque al del "
           "tiro y se ve más fuerte cuando acabó en gol; el tamaño del círculo es el xG. El rombo marca un tiro "
           "libre directo, sin pase previo.",
           "Dos medias canchas, córners y tiros libres, con líneas del saque al tiro"),
    Figura("1_corners_mapa_calor.png", 3, "Córners: a qué zona van",
           "Zona del área a la que llegan los córners del América, por lado de cobro. Cada número es la parte de los "
           "córners de ese lado, sin los jugados en corto, que cae en esa zona. Arriba de cada área están cuántos se "
           "cobraron sin jugar en corto, quién los cobra y cuántos van abiertos o cerrados.",
           "Dos áreas, izquierda y derecha, con el porcentaje de córners que cae en cada zona"),
    Figura("4_saques_banda_a_favor.png", 3, "Saques de banda a favor",
           "Cada flecha va de donde el América sacó la banda a donde cayó el balón. Las grises son saques "
           "perdidos. Las que terminan en un círculo acabaron en tiro, y si el círculo está relleno, en gol. El "
           "América ataca de izquierda a derecha.",
           "Cancha completa con flechas desde las bandas; las grises son saques perdidos"),
    Figura("3_mapa_calor_defensivo.png", 4, "Dónde defiende",
           "Porcentaje de las acciones defensivas del América en cada zona: recuperaciones, duelos, "
           "intercepciones, despejes y bloqueos. La escala es la misma en los cuatro torneos.",
           "Cancha en zonas con el porcentaje de acciones defensivas en cada una"),
    Figura("1_actividad_defensiva.png", 4, "Actividad defensiva contra el rival",
           "Por zona, el porcentaje de acciones defensivas del América menos el del rival, en puntos "
           "porcentuales. Los dos equipos aparecen con la portería que defienden a la izquierda. El color va de más "
           "peso en la defensa del rival a más peso en la defensa del América. Cuentan presiones, faltas, "
           "intercepciones, bloqueos y entradas.",
           "Cancha en zonas, con la portería defendida a la izquierda; el color de cada zona dice si pesa más en la "
           "defensa del América o en la del rival"),
    Figura("4_tiros_defensa.png", 4, "Tiros en contra",
           "Tiros de los rivales contra el América en el torneo. El tamaño es el xG; los goles van en "
           "gris relleno y los tiros sin gol, huecos.",
           "Media cancha defensiva con un círculo por tiro del rival, más grande cuanto mayor es su xG"),
    Figura("3_balon_parado_en_contra.png", 4, "Balón parado en contra",
           "Tiros del rival que nacen de un córner o de un tiro libre. Siguen el mismo código que los de a favor, "
           "en gris.",
           "Dos medias canchas con los tiros del rival tras córner y tiro libre"),
    Figura("5_saques_banda_en_contra.png", 4, "Saques de banda en contra",
           "Saques de banda del rival. Cada flecha va del saque a donde cayó el balón, con el mismo código que los "
           "saques a favor, en gris.",
           "Cancha completa con las flechas de los saques de banda del rival"),
    Figura("mapa_calor_jugadores_{torneo}.png", 6, "Mapa de calor por jugador",
           "Zonas donde estuvo cada uno de los jugadores con más minutos del torneo, con sus acciones con y sin "
           "balón. Cuanto más oscuro, más acciones; cada mapa se mide contra el propio jugador. El punto blanco es "
           "su posición promedio y el América ataca de izquierda a derecha.",
           "Una cancha pequeña por jugador, con su mapa de calor"),
    Figura("radar_posiciones_{torneo}.png", 6, "Radares por posición",
           "Métricas de los jugadores con más minutos, cada uno en la posición donde más minutos jugó en el "
           "torneo. Los conteos van por 90 minutos y los porcentajes se ponderan por minutos. La escala es la "
           "misma en los cuatro torneos y sale de los jugadores de esa posición con al menos "
           f"{MIN_MINUTOS_RADAR} minutos en un torneo.",
           "Un radar por jugador, con las métricas de su posición"),
]
# figuras de cancha de la puerta 5: una imagen por contexto, con los partidos de los cuatro torneos juntos
PIE_CANCHA = ("Una columna por {columnas}. Arriba, qué parte de los pases de cada tercio da el América. En medio, los "
              "tiros de los dos equipos, con el xG por 90 minutos a favor y en contra. Abajo, dónde hace el América "
              "sus acciones defensivas: la línea continua es la altura media a la que recupera el balón "
              "(recuperaciones e intercepciones) y la punteada, el promedio de los {{n}} partidos. "
              "La línea marca dónde recupera el balón, no dónde presiona; por eso no coincide con la altura de presión de "
              "la tarjeta de localía. El América ataca de izquierda a derecha.")
# regla de Cambio_Partidos.py: un nivel con menos de estos partidos o minutos en un torneo no se dibuja
MIN_PARTIDOS_CANCHA = 5
MIN_MINUTOS_CANCHA = 90
# solo si hay pestañas por torneo: la vista de 91 es la de las tarjetas y cada torneo tiene menos datos
PIE_CANCHA_TORNEOS = ("La pestaña «{n} partidos» es la vista de las cifras de las tarjetas. Cada torneo tiene menos "
                      "datos, así que sus mapas se leen con cautela; la línea punteada es la misma en todas las "
                      f"pestañas. Un nivel con menos de {MIN_PARTIDOS_CANCHA} partidos o {MIN_MINUTOS_CANCHA} minutos "
                      "en un torneo no se dibuja y su columna dice «pocos datos».")
ALT_CANCHA = ("Tres filas de canchas, una columna para {columnas}: porcentaje de pases del América por tercio, "
              "tiros de los dos equipos con su xG y calor de las acciones defensivas del América")
CANCHAS = (
    ("contexto_cancha_marcador.png", "El marcador en la cancha", "perdiendo, empatando y ganando", "score_state"),
    ("contexto_cancha_localia.png", "La localía en la cancha", "local y visitante", "is_home"),
    ("contexto_cancha_rival.png", "La fuerza del rival en la cancha", "rival débil, medio y fuerte",
     "rival_strength_tercil"),
)
COLUMNAS_CANCHA = {ctx: columnas for _, _, columnas, ctx in CANCHAS}
FIGURAS += [Figura(archivo, 5, titulo, PIE_CANCHA.format(columnas=columnas), ALT_CANCHA.format(columnas=columnas), ctx)
            for archivo, titulo, columnas, ctx in CANCHAS]

# contextos de la fase 4: nombre del bloque y como se dice dentro de una frase
CONTEXTOS = {
    "score_state": ("Marcador", "el marcador"),
    "is_home": ("Localía", "la localía"),
    "rival_strength_tercil": ("Fuerza del rival", "la fuerza del rival"),
    "minute_bin": ("Minuto", "el minuto"),
    "stage": ("Fase del torneo", "la fase del torneo"),
    "numerical_state": ("Superioridad numérica", "la superioridad numérica"),
}
# nivel en una tabla y dentro de una frase; lo que no este aqui se muestra como viene
NIVEL_CORTO = {
    ("stage", "regular"): "fase regular", ("stage", "fase final"): "liguilla",
    ("minute_bin", "45+"): "45+ (añadido 1T)", ("minute_bin", "90+"): "90+ (añadido 2T)",
    ("minute_bin", "ET"): "tiempo extra",
}
NIVEL_FRASE = {
    ("score_state", "empatando"): "empatando", ("score_state", "perdiendo"): "perdiendo",
    ("score_state", "ganando"): "ganando",
    ("is_home", "local"): "de local", ("is_home", "visitante"): "de visitante",
    ("rival_strength_tercil", "débil"): "contra rivales débiles",
    ("rival_strength_tercil", "medio"): "contra rivales medios",
    ("rival_strength_tercil", "fuerte"): "contra rivales fuertes",
    ("minute_bin", "45+"): "en el añadido del primer tiempo", ("minute_bin", "90+"): "en el añadido del segundo tiempo",
    ("minute_bin", "ET"): "en tiempo extra",
    ("stage", "regular"): "en fase regular", ("stage", "fase final"): "en liguilla",
    ("numerical_state", "igualdad"): "con igualdad numérica",
    ("numerical_state", "inferioridad"): "en inferioridad numérica",
    ("numerical_state", "superioridad"): "en superioridad numérica",
}
# nombre corto de cada metrica de la fase 4 para las filas de F5.1; si falta, va la etiqueta completa
ETIQUETA_CORTA = {
    "duracion": "Duración de la posesión", "pases": "Pases por posesión", "con_tiro": "Posesiones con tiro",
    "xg": "xG por posesión", "valida": "Posesiones válidas", "altura_inicio": "Altura de inicio",
    "inicio_ultimo_tercio": "Inicio en el último tercio", "balon_parado": "Posesiones a balón parado",
    "tiempo_con_balon": "Tiempo con el balón", "xg_rival": "xG del rival por posesión",
    "con_tiro_rival": "Posesiones del rival con tiro", "puntos": "Puntos por partido", "goles_favor": "Goles a favor",
    "goles_contra": "Goles en contra", "tiempo_ganando": "Tiempo ganando", "tiempo_perdiendo": "Tiempo perdiendo",
    "pases_progresivos": "Pases progresivos", "pases_rompe_lineas": "Pases que rompen líneas",
    "recepciones_espacio": "Recepciones en espacio", "progresiones_profundas": "Progresiones profundas",
    "obv_neto": "OBV neto", "cadena_construccion": "Cadena de construcción", "recupera_5s": "Recupera en 5 s",
    "contrapresion": "Contrapresión", "ppda": "PPDA en juego abierto", "altura_presion": "Altura de la presión",
}
# linea bajo el titulo de la tarjeta de contexto que define sus niveles (03_contexto.py, c4_rival_strength)
DEF_RIVAL = ("El tercio en que queda el rival dentro de su torneo según su diferencia de xG por partido en fase "
             "regular, sin contar sus partidos contra el América.")
DEF_CONTEXTO = {"rival_strength_tercil": f"Rival débil, medio o fuerte: {DEF_RIVAL[0].lower()}{DEF_RIVAL[1:]}"}
# supuestos con cifra: geometria de la cancha (yardas StatsBomb, 120 x 80; ataque hacia x = 120)
LARGO_CANCHA_YD = 120
YARDA_M = 0.9144
ZONA_ALTA_M = 40  # 05_metricas_finales.md: ultimos 40 metros de la cancha rival
TERCIO_FINAL_X = LARGO_CANCHA_YD * 2 / 3  # spec_03_contexto E1: final_third es x >= 80
# que es cada contexto de la fase 4 (sus niveles salen de NIVELES de 04_contexto.py)
DEF_CONTEXTOS = {
    "score_state": "Cómo va el partido para el América justo antes de cada jugada.",
    "is_home": "Si el América juega en su estadio o fuera.",
    "minute_bin": "Tramo del reloj en bloques de 15 minutos, con los añadidos de cada tiempo y el tiempo extra aparte.",
    "stage": "Fase regular del torneo o fase final (liguilla).",
    "numerical_state": "Jugadores del América en cancha contra los del rival, según las expulsiones.",
}
# objetos o supuestos en que se basa cada figura (ids de la puerta 2: def-, sup- o term-); verificar() falla sin ellos
BASE_FIGURA = {
    "2_flujo_pases.png": ("def-fase-de-inicio", "def-fase-de-construccion"),
    "5_red_pases.png": ("def-fase-de-construccion", "def-rol-y-minutos-jugados"),
    "3_tiros_ataque.png": ("def-secuencia-ofensiva", "sup-penales", "term-xg"),
    "2_balon_parado_a_favor.png": ("def-posesion-valida", "sup-penales", "term-xg"),
    "1_corners_mapa_calor.png": ("def-posesion-valida",),
    "4_saques_banda_a_favor.png": ("def-posesion-valida", "def-secuencia-ofensiva"),
    "3_mapa_calor_defensivo.png": ("def-fase-de-presion", "def-zona-de-presion-alta"),
    "1_actividad_defensiva.png": ("def-fase-de-presion",),
    "4_tiros_defensa.png": ("sup-penales", "term-xg"),
    "3_balon_parado_en_contra.png": ("def-posesion-valida", "sup-penales", "term-xg"),
    "5_saques_banda_en_contra.png": ("def-posesion-valida",),
    "mapa_calor_jugadores_{torneo}.png": ("def-rol-y-minutos-jugados",),
    "radar_posiciones_{torneo}.png": ("def-rol-y-minutos-jugados",),
    "contexto_cancha_marcador.png": ("def-marcador", "sup-desde-america", "sup-penales", "term-xg"),
    "contexto_cancha_localia.png": ("def-localia", "sup-penales", "term-xg"),
    "contexto_cancha_rival.png": ("def-fuerza-del-rival", "sup-rival", "sup-penales", "term-xg"),
}
# metrica de la fase 4 -> objeto o termino en que se basa (para la traza de F5.4 y T5.1)
METRICA_OBJETO = {
    "valida": "def-posesion-valida", "recupera_5s": "def-transicion", "contrapresion": "def-contrapresion",
    "pases_rompe_lineas": "def-salto-de-lineas", "cadena_construccion": "def-fase-de-construccion",
    "inicio_ultimo_tercio": "sup-tercio-final", "altura_presion": "def-fase-de-presion", "ppda": "term-ppda",
    "xg": "term-xg", "xg_rival": "term-xg", "obv_neto": "term-obv", "recepciones_espacio": "sup-360",
}
ALCANCE_CAPTURA = [
    "El juego con y sin balón, por fases: inicio, construcción, secuencia ofensiva, transición y presión.",
    "El contexto de cada jugada: marcador, localía, rival, minuto, fase y superioridad numérica.",
    "La evolución por torneo, del {primero} al {ultimo}.",
    "Los jugadores: minutos, rol, formación, rotación y cambios.",
]
ALCANCE_FUERA = [
    "El efecto del entrenador separado del efecto del plantel y del rival.",
    "Un grupo de contraste con otros entrenadores.",
    "Datos físicos, de tracking continuo, de entrenamiento y de lesiones fuera del partido.",
    "El 360 completo: solo una parte de los eventos trae frame.",
    "Causas: las diferencias son asociaciones.",
]
# tarjetas del marco: los objetos de 05_metricas_finales.md por grupo; una tupla de varios es un recorrido
GRUPOS_MARCO = [
    ("Con el balón", [("Posesión válida", "Salto de líneas"),
                      ("Fase de inicio", "Fase de construcción", "Secuencia ofensiva")]),
    ("Sin el balón", [("Transición", "Fase de presión", "Zona de presión alta")]),
]
RECORRIDO = "El recorrido de una posesión"  # titulo de la fila con varias fases seguidas
# 03_ataque.py no filtra por jugadores visibles y el contrato (C19) deja la regla provisional como informativa
SIN_FILTRO_360 = ("En los frames donde se ven pocos jugadores, los conteos del 360 pueden quedarse cortos, porque no "
                  "se filtró por número de jugadores visibles.")
NOTA_OBJETO = {"Fase de presión": "El reporte usa 10 s como tiempo máximo entre un intento y el siguiente."}
# terminos del glosario (T9.3): lo que el reporte usa sin explicar en cada puerta
TERMINOS = [
    ["xG", "Goles esperados: la probabilidad de que un tiro termine en gol según dónde y cómo se tiró. Sumados, dicen "
           "cuántos goles merecían las ocasiones de un equipo. En este reporte no incluyen penales."],
    ["PPDA", "Pases que da el rival por cada acción defensiva del equipo. Más alto quiere decir menos presión. El PPDA "
             "en juego abierto, el que usa este reporte, deja fuera las jugadas que nacen de un balón parado."],
    ["OBV", "Valor de cada acción con balón según StatsBomb: cuánto sube o baja la probabilidad de marcar y la de "
            "recibir gol. El OBV neto resta al del equipo el del rival."],
    ["Verticalidad", "Qué tan directa es una posesión, de 0 a 1. Cerca de 1, el balón avanza de forma sostenida hacia "
                     "la portería rival; cerca de 0, circula o se recicla."],
    ["pp", "Puntos porcentuales: la resta de dos porcentajes. De 50% a 60% hay 10 pp."],
    ["IC 95%", "Intervalo de confianza del 95%, sacado de remuestrear partidos completos. Si el intervalo de una "
               "diferencia no toca el 0, la diferencia se sostiene con estos datos."],
    ["Rival fuerte, medio o débil", DEF_RIVAL],
    ["360 (frame)", "Foto de la posición de los jugadores visibles en el momento de cada evento. Sin frame no se "
                    "pueden contar líneas rotas ni recepciones en espacio."],
    ["Tamaño de efecto", "La diferencia medida contra la variación normal de la métrica, para comparar métricas con "
                         "unidades distintas. Desde {efecto_min} el reporte la cuenta como diferencia."],
]
# orden de los niveles en la tarjeta, igual que las columnas de su figura de cancha; los demas, como NIVELES
ORDEN_TARJETA = {
    "score_state": ("perdiendo", "empatando", "ganando"),
    "is_home": ("local", "visitante"),
    "rival_strength_tercil": ("débil", "medio", "fuerte"),
}
# hallazgo de cada metrica en lenguaje de futbol, cuando sube y cuando baja contra la referencia; si falta, «sube»
# o «baja» con la etiqueta. Ojo con el PPDA: mas alto es menos presion
FRASE_METRICA = {
    "duracion": ("sus posesiones duran más", "sus posesiones duran menos"),
    "pases": ("da más pases por posesión", "da menos pases por posesión"),
    "con_tiro": ("termina más posesiones en tiro", "termina menos posesiones en tiro"),
    "xg": ("genera más xG por posesión", "genera menos xG por posesión"),
    "valida": ("tiene más posesiones válidas", "tiene menos posesiones válidas"),
    "altura_inicio": ("empieza sus posesiones más arriba", "empieza sus posesiones más atrás"),
    "inicio_ultimo_tercio": ("empieza más posesiones en el último tercio",
                             "empieza menos posesiones en el último tercio"),
    "balon_parado": ("juega más a balón parado", "juega menos a balón parado"),
    "tiempo_con_balon": ("tiene más el balón", "tiene menos el balón"),
    "xg_rival": ("concede más xG por posesión", "concede menos xG por posesión"),
    "con_tiro_rival": ("deja tirar más al rival", "deja tirar menos al rival"),
    "puntos": ("suma más puntos", "suma menos puntos"),
    "goles_favor": ("anota más", "anota menos"),
    "goles_contra": ("recibe más goles", "recibe menos goles"),
    "tiempo_ganando": ("pasa más tiempo ganando", "pasa menos tiempo ganando"),
    "tiempo_perdiendo": ("pasa más tiempo perdiendo", "pasa menos tiempo perdiendo"),
    "pases_progresivos": ("hace más pases progresivos", "hace menos pases progresivos"),
    "pases_rompe_lineas": ("rompe más líneas con pases", "rompe menos líneas con pases"),
    "recepciones_espacio": ("recibe más veces en espacio", "recibe menos veces en espacio"),
    "progresiones_profundas": ("llega más veces a zona de peligro", "llega menos veces a zona de peligro"),
    "obv_neto": ("suma más valor por posesión", "suma menos valor por posesión"),
    "cadena_construccion": ("construye más desde atrás", "construye menos desde atrás"),
    "recupera_5s": ("recupera más balones en los 5 s tras perderlo", "recupera menos balones en los 5 s tras perderlo"),
    "contrapresion": ("contrapresiona más", "contrapresiona menos"),
    "ppda": ("presiona menos", "presiona más"),
    "altura_presion": ("presiona más alto", "presiona más abajo"),
}
LECTURA_ET = {"diferencia": "diferencia", "diferencia pequena": "diferencia pequeña", "indicio": "indicio",
              "sin diferencia clara": "sin diferencia clara"}
AJUSTE_ET = {"simple": "simple", "mitad_x_tercil": "mitad × tercil del rival"}
OBS_ET = {"posesion": "posesiones", "evento": "eventos", "partido": "partidos"}
OBS_CORTO = {"posesion": "pos.", "evento": "ev.", "partido": "part."}
OBS_UNO = {"posesion": "posesión", "evento": "evento", "partido": "partido"}
# decimales y sufijos por unidad de la fase 4
DECIMALES = {"xG": 3, "OBV": 3, "s": 1, "yardas": 1, "pases por accion": 1}
SUFIJO_VALOR = {"proporcion": "%", "s": " s", "xG": " xG", "yardas": " yd", "OBV": " OBV"}
SUFIJO_DIF = {"proporcion": " pp", "s": " s", "xG": " xG", "yardas": " yd", "OBV": " OBV",
              "pases por accion": " pases por acción"}
# metrica de la fase 4 -> definicion final de Pato a la que enlaza
METRICA_DEF = {"valida": "Posesión válida", "recupera_5s": "Transición", "contrapresion": "Transición",
               "pases_rompe_lineas": "Salto de líneas", "cadena_construccion": "Fase de construcción"}
ORIGENES = [("juego_abierto", "Juego abierto"), ("corner", "Córner"), ("tiro_libre", "Tiro libre"),
            ("banda", "Saque de banda")]


class ErrorReporte(Exception):
    pass


def _ok(msg):
    print(f"[OK] {msg}")


def _aviso(msg):
    print(f"AVISO: {msg}")


def plano(texto):
    # Texto sin acentos para la consola, como el resto de los mensajes de los scripts.
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()


def esc(texto):
    return html.escape(str(texto), quote=True)


def slug(texto):
    base = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")


def ruta_repo(valor):
    # Ruta absoluta tal cual; relativa, desde la raiz del repo.
    p = Path(valor)
    return p if p.is_absolute() else (ROOT / p).resolve()


def leer_md(ruta):
    # utf-8-sig: un md guardado con BOM en Windows se lee igual
    return Path(ruta).read_text(encoding="utf-8-sig")


# ---------------------------------------------------------------- formato de cifras

def entero(n):
    return "n. d." if pd.isna(n) else f"{int(n):,}"


def decimal(x, d=1):
    return "n. d." if pd.isna(x) else f"{x:,.{d}f}"


def porciento(p, d=1):
    return "n. d." if pd.isna(p) else f"{100 * p:.{d}f}%"


def razon(a, b):
    return a / b if b else float("nan")


def con_signo(texto):
    # Signo menos tipografico para negativos y + explicito para positivos.
    return texto.replace("-", "−") if texto.startswith("-") else f"+{texto}"


def fmt_valor(v, unidad):
    if pd.isna(v):
        return "n. d."
    if unidad == "proporcion":
        return porciento(v)
    return f"{v:,.{DECIMALES.get(unidad, 2)}f}{SUFIJO_VALOR.get(unidad, '')}".replace("-", "−")


def decimales_utiles(x, d, tope=4):
    # Mas decimales si x redondea a 0 sin ser 0: un IC de +0.003 no debe leerse como +0.0.
    while d < tope and x != 0 and round(abs(x), d) == 0:
        d += 1
    return d


def fmt_dif(d, unidad, sufijo=True):
    if pd.isna(d):
        return "n. d."
    if unidad == "proporcion":
        texto = con_signo(f"{100 * d:.{decimales_utiles(100 * d, 1)}f}")
        return texto + (" pp" if sufijo else "")
    texto = con_signo(f"{d:,.{decimales_utiles(d, DECIMALES.get(unidad, 2))}f}")
    return texto + (SUFIJO_DIF.get(unidad, f" {unidad}") if sufijo else "")


def fmt_efecto(e):
    return "n. d." if pd.isna(e) else con_signo(f"{e:.{decimales_utiles(e, 2)}f}")


def fmt_formacion(v):
    digitos = re.sub(r"\D", "", str(v))
    return "-".join(digitos) if digitos else str(v)


def clave_torneo(torneo):
    # Orden por fecha: año y, dentro del año, Clausura antes que Apertura.
    m = re.match(r"(Apertura|Clausura)\s+(\d{4})", str(torneo))
    return (int(m.group(2)), 0 if m.group(1) == "Clausura" else 1, "") if m else (9999, 9, str(torneo))


def y_lista(partes):
    partes = list(partes)
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


# ---------------------------------------------------------------- markdown

@dataclass
class Seccion:
    titulo: str
    nivel: int
    bloques: list = field(default_factory=list)  # ("p", texto), ("lista", items) o ("tabla", encabezados, filas)


def inline_md(texto):
    # Texto md de una linea a HTML: escapa, enlaces a texto plano, `codigo` y **negrita**.
    s = esc(texto)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


def _celdas(linea):
    partes = re.split(r"(?<!\\)\|", linea.strip())
    if partes and partes[0] == "":
        partes = partes[1:]
    if partes and partes[-1] == "":
        partes = partes[:-1]
    return [p.strip().replace("\\|", "|") for p in partes]


def parsear_md(texto):
    # Secciones por encabezado, cada una con sus parrafos, listas con «- » y tablas md, en orden.
    secciones = [Seccion("", 0)]
    tabla, parrafo, lista = None, [], []

    def cerrar():
        nonlocal tabla, parrafo, lista
        if parrafo:
            secciones[-1].bloques.append(("p", " ".join(parrafo)))
            parrafo = []
        if lista:
            secciones[-1].bloques.append(("lista", lista))
            lista = []
        if tabla:
            secciones[-1].bloques.append(("tabla", tabla[0], tabla[1:]))
            tabla = None

    for linea in texto.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", linea)
        item = re.match(r"^\s*[-*]\s+(.*)$", linea)
        if m:
            cerrar()
            secciones.append(Seccion(m.group(2).strip(), len(m.group(1))))
        elif linea.strip().startswith("|"):
            if parrafo or lista:
                cerrar()
            celdas = _celdas(linea)
            if all(re.fullmatch(r":?-{3,}:?", c) for c in celdas if c):
                continue
            tabla = (tabla or []) + [celdas]
        elif item:
            if parrafo or tabla:
                cerrar()
            lista.append(item.group(1).strip())
        elif linea.strip():
            if tabla or lista:
                cerrar()
            parrafo.append(linea.strip())
        else:
            cerrar()
    cerrar()
    return secciones


def tabla_de(seccion):
    tablas = [b for b in seccion.bloques if b[0] == "tabla"]
    return (tablas[0][1], tablas[0][2]) if tablas else None


def tabla_md(encabezados, filas, ids=None, etiqueta="Tabla"):
    # Tabla de un md (framework, LEEME o textos del equipo); ids opcionales por fila (anclas de las definiciones).
    # encabezado alineado como su columna: a la derecha si todas sus celdas empiezan con cifra
    num_col = {j for j in range(1, len(encabezados))
               if filas and all(len(f) > j and re.match(r"^[+\-−]?\d", f[j].strip()) for f in filas if f)}
    th = "".join(f'<th scope="col"{NUM if j in num_col else ""}>{inline_md(h)}</th>' for j, h in enumerate(encabezados))
    cuerpo = ""
    for i, f in enumerate(filas):
        if not f:
            continue
        id_attr = f' id="{ids[i]}"' if ids and i < len(ids) and ids[i] else ""
        celdas = [f'<th scope="row">{inline_md(f[0])}</th>'] + [
            f"<td{NUM if re.match(r'^[+\-−]?\d', v.strip()) else ''}>{inline_md(v)}</td>" for v in f[1:]]
        cuerpo += f"<tr{id_attr}>{''.join(celdas)}</tr>"
    return (f'<div class="tabla-caja" role="region" tabindex="0" aria-label="{esc(etiqueta)}"><table class="doc">'
            f'<thead><tr>{th}</tr></thead><tbody>{cuerpo}</tbody></table></div>')


def md_a_html(texto, nivel_base=3):
    # Un md completo a HTML: encabezados desde h{nivel_base}, parrafos, listas y tablas.
    partes, usadas = [], set()
    for s in parsear_md(texto):
        nombre = s.titulo  # la region de cada tabla lleva el titulo de su seccion o su primera columna
        if s.titulo:
            n = min(nivel_base + s.nivel - 1, 4)
            partes.append(f"<h{n}>{inline_md(s.titulo)}</h{n}>")
        for b in s.bloques:
            if b[0] == "p":
                partes.append(f"<p>{inline_md(b[1])}</p>")
            elif b[0] == "lista":
                partes.append("<ul>" + "".join(f"<li>{inline_md(x)}</li>" for x in b[1]) + "</ul>")
            else:
                et = re.sub(r"[`*]", "", nombre or b[1][0])
                et = f"{et} · {re.sub(r'[`*]', '', b[1][0])}" if et in usadas else et  # dos tablas en una seccion
                usadas.add(et)
                partes.append(tabla_md(b[1], b[2], etiqueta=et))
    return "".join(partes)


@dataclass
class Framework:
    definiciones: tuple  # (encabezados, filas)
    donde: tuple
    crudo: str  # texto del md de metricas, para saber cuantas veces cita cada nombre de columna cruda
    extras: list = field(default_factory=list)  # (nombre, texto) de 01 y 04 que el reporte usa


def leer_framework(carpeta):
    falta_de = "(framework de Pato, llega por la rama D/narrativa; pasa otra carpeta con --framework)"
    if not carpeta.is_dir():
        raise ErrorReporte(f"no existe la carpeta del framework {carpeta} {falta_de}")
    textos = {}
    for nombre in (FRAMEWORK_METRICAS,):
        archivo = carpeta / nombre
        if not archivo.is_file():
            raise ErrorReporte(f"falta {nombre} en {carpeta} {falta_de}")
        try:
            textos[nombre] = leer_md(archivo)
        except (OSError, UnicodeDecodeError) as e:
            raise ErrorReporte(f"no se pudo leer {archivo}: {type(e).__name__}: {e}") from e
    crudo = "\n".join(textos.values())
    textos = {k: sin_marcas(sin_atribucion(v)) for k, v in textos.items()}

    secciones = {s.titulo.lower(): s for s in parsear_md(textos[FRAMEWORK_METRICAS]) if s.nivel == 2}
    tablas = {}
    for titulo in ("definiciones", "dónde se calculan"):
        s = secciones.get(titulo)
        t = tabla_de(s) if s else None
        if t is None or not t[1]:
            raise ErrorReporte(f"falta la seccion «## {titulo.capitalize()}» con su tabla en {FRAMEWORK_METRICAS} "
                               f"{falta_de}")
        tablas[titulo] = t
    return Framework(tablas["definiciones"], tablas["dónde se calculan"], crudo, objetos_extra(carpeta))


def objetos_extra(carpeta):
    # Definiciones que el reporte usa fuera de las 8 finales: contrapresion (01) y los objetos de jugadores (04).
    extras = []
    try:
        texto = sin_marcas(sin_atribucion(leer_md(carpeta / FRAMEWORK_DEFS)))
        for m in re.finditer(r"^- \*\*([^*(:]+?)(?: \(`[^`]*`\))?:\*\*\s*(.+)$", texto, re.M):
            if m.group(1).strip() in OBJETOS_01:
                t = m.group(2).strip()
                extras.append((m.group(1).strip(), t[:1].upper() + t[1:]))
    except (OSError, UnicodeDecodeError) as e:
        _aviso(f"no se pudo leer {FRAMEWORK_DEFS}: {type(e).__name__}; sus definiciones se omiten")
    try:
        texto = sin_marcas(sin_atribucion(leer_md(carpeta / FRAMEWORK_JUGADORES)))
        for clave, nombre in JUGADORES_MARCO.items():
            sec = re.search(rf"^## {clave}\.[^\n]*\n(.*?)(?=^## |\Z)", texto, re.M | re.S)
            que = re.search(r"\*\*Qué mide\.\*\*\s*(.+)", sec.group(1)) if sec else None
            if not que:
                _aviso(f"{FRAMEWORK_JUGADORES} no trae «Qué mide» de {clave}; el objeto se omite")
                continue
            t = re.sub(r"\b(del|el) EQ\b", r"\1 América", que.group(1).strip())
            momento = re.search(r"Los cambios del mismo [^.\n]*momento de cambio\.", sec.group(1))
            extras.append((nombre, t + (f" {momento.group(0)}" if momento else "")))
    except (OSError, UnicodeDecodeError) as e:
        _aviso(f"no se pudo leer {FRAMEWORK_JUGADORES}: {type(e).__name__}; sus objetos se omiten")
    return extras


def sin_marcas(texto):
    # Quita del framework las marcas de trabajo interno («Ver pendiente 2», «Plan 7.3.18», nombres de funciones).
    for patron, reemplazo in SIN_MARCAS:
        texto = patron.sub(reemplazo, texto)
    return texto


def sin_atribucion(texto):
    # Quita del framework quien calcula cada cosa: «03_defensa.py (Pablo)» queda «03_defensa.py».
    for patron, reemplazo in SIN_ATRIBUCION:
        texto = patron.sub(reemplazo, texto)
    return texto


# ---------------------------------------------------------------- tablas

def leer_tabla(clave):
    f = FUENTES[clave]
    archivo = ROOT / f.ruta
    if not archivo.exists():
        raise ErrorReporte(f"no existe {f.ruta}; lo produce {f.script} ({f.dueno})")
    try:
        if archivo.suffix == ".parquet":
            return pd.read_parquet(archivo)
        if archivo.suffix == ".csv":
            return pd.read_csv(archivo)
        return leer_md(archivo)
    except (OSError, ValueError, UnicodeDecodeError, pa.lib.ArrowException) as e:
        raise ErrorReporte(f"no se pudo leer {f.ruta}: {type(e).__name__}: {e}") from e


def revisar_columnas(clave, df):
    f = FUENTES[clave]
    faltan = [c for c in f.columnas if c not in df.columns]
    if not faltan:
        return []
    de = ""
    if clave == "partidos":
        origen = {c: next((quien for patron, quien in ORIGEN_COLUMNA if patron.match(c)), None) for c in faltan}
        partes = [f"{c} viene de {quien}" for c, quien in origen.items() if quien]
        de = f"; {'; '.join(partes)}" if partes else ""
    return [f"faltan {faltan} en {f.ruta} (la produce {f.script}, {f.dueno}{de})"]


def parametros_04():
    # Parametros de la estadistica de la fase 4, leidos del script para no copiarlos a mano.
    ruta = ROOT / "scripts" / "04_contexto.py"
    try:
        spec = importlib.util.spec_from_file_location("contexto_04", ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return {k: getattr(modulo, k) for k in PARAMETROS_04}
    except Exception as e:  # ejecuta un script ajeno: cualquier error se reporta con su causa, sin traceback
        raise ErrorReporte(f"no se pudieron leer {list(PARAMETROS_04)} de {ruta.relative_to(ROOT).as_posix()}: "
                           f"{type(e).__name__}: {e}") from e


@dataclass
class Datos:
    partidos: pd.DataFrame
    posesiones: pd.DataFrame
    n_eventos: int
    celdas: pd.DataFrame
    comps: pd.DataFrame
    cobertura: pd.DataFrame
    framework: Framework
    p04: dict
    tiros: pd.DataFrame  # eventos de los periodos 1 a 4, solo las columnas de FUENTES["penales"]


def leer_tiros():
    # Columnas de penales y autogoles de eventos.parquet, periodos 1 a 4 (sin la tanda).
    f = FUENTES["penales"]
    archivo = ROOT / f.ruta
    if not archivo.exists():
        raise ErrorReporte(f"no existe {f.ruta}; lo produce {f.script} ({f.dueno})")
    try:
        nombres = pq.ParquetFile(archivo).schema_arrow.names
        faltan = [c for c in f.columnas if c not in nombres]
        if faltan:
            raise ErrorReporte(f"faltan {faltan} en {f.ruta} (la produce {f.script}, {f.dueno})")
        return pd.read_parquet(archivo, columns=list(f.columnas), filters=[("period", "<", 5)])
    except (OSError, ValueError, pa.lib.ArrowException) as e:
        raise ErrorReporte(f"no se pudo leer {f.ruta}: {type(e).__name__}: {e}") from e


def cargar(framework_dir):
    fallas, tablas = [], {}
    for clave in ("partidos", "posesiones", "celdas", "comparaciones", "cobertura"):
        try:
            tablas[clave] = leer_tabla(clave)
            fallas += revisar_columnas(clave, tablas[clave])
        except ErrorReporte as e:
            fallas.append(str(e))
    ruta_ev = FUENTES["eventos"].ruta
    try:
        tablas["eventos"] = pq.ParquetFile(ROOT / ruta_ev).metadata.num_rows
    except FileNotFoundError:
        fallas.append(f"no existe {ruta_ev}; lo produce {FUENTES['eventos'].script} (Yordi)")
    except (OSError, pa.lib.ArrowException) as e:
        fallas.append(f"no se pudo leer {ruta_ev}: {type(e).__name__}: {e}")
    try:
        tablas["tiros"] = leer_tiros()
    except ErrorReporte as e:
        fallas.append(str(e))
    try:
        fw = leer_framework(framework_dir)
    except ErrorReporte as e:
        fallas.append(str(e))
        fw = None
    if fallas:
        raise ErrorReporte("\n   ".join([f"{len(fallas)} insumos con problemas:"] + fallas))
    return Datos(tablas["partidos"], tablas["posesiones"], int(tablas["eventos"]), tablas["celdas"],
                 tablas["comparaciones"], tablas["cobertura"], fw, parametros_04(),
                 tablas["tiros"])


# ---------------------------------------------------------------- cifras

def resultados(partidos):
    # G, E y P por el signo de goles_eq - goles_rival; los partidos sin goles no cuentan en ninguno.
    ge = partidos["goles_eq"].astype("Float64")
    gr = partidos["goles_rival"].astype("Float64")
    return tuple(int(x.fillna(False).sum()) for x in (ge > gr, ge == gr, ge < gr))


def calcular_cifras(d):
    p, a = d.partidos, d.posesiones
    c = {}
    c["torneos"] = sorted(p["torneo"].astype("string").dropna().unique(), key=clave_torneo)
    if not c["torneos"]:
        raise ErrorReporte(f"{FUENTES['partidos'].ruta} no trae ningun torneo")
    c["n"] = len(p)
    stage = p["stage"].astype("string")
    c["regular"], c["liguilla"] = int((stage == "regular").sum()), int((stage == "fase final").sum())
    es_final = p["es_final"].astype("boolean").fillna(False)
    c["finales"] = int(es_final.sum())  # partidos de final (ida y vuelta)
    c["n_finales"] = int(p.loc[es_final.to_numpy(dtype=bool), "torneo"].astype("string").nunique())  # una por torneo
    c["G"], c["E"], c["P"] = resultados(p)
    c["resultado_tabla"] = p["resultado"].astype("string").value_counts().to_dict()
    c["gf"], c["gc"] = int(p["goles_eq"].sum()), int(p["goles_rival"].sum())
    es_eq = a["es_eq"].astype("boolean").fillna(False)
    admin = a["es_administrativa"].astype("boolean").fillna(False)
    c["xg_favor"], c["xg_contra"] = float(a.loc[es_eq, "xg"].sum()), float(a.loc[~es_eq, "xg"].sum())
    c["xg_chain"] = float(p["xg_chain_eq"].sum())
    for lado in ("favor", "contra"):
        c[f"origen_{lado}"] = {o: {m: float(p[f"{m}_{o}_{lado}"].sum()) for m in ("tiros", "goles", "xg")}
                               for o, _ in ORIGENES}
        c[f"xg_origen_{lado}"] = sum(v["xg"] for v in c[f"origen_{lado}"].values())
    # penales y autogoles, aparte del xG por origen; es_equipo_analizado True es el America
    ev = d.tiros
    eq_ev = ev["es_equipo_analizado"].astype("boolean").fillna(False)
    pen = (ev["type_name"].astype("string") == "Shot") & (ev["shot_type_name"].astype("string") == "Penalty")
    for lado, mascara in (("favor", eq_ev), ("contra", ~eq_ev)):
        sel = ev[pen & mascara]
        c[f"penales_{lado}"] = {"tiros": len(sel),
                                "goles": int((sel["shot_outcome_name"].astype("string") == "Goal").sum()),
                                "xg": float(sel["shot_statsbomb_xg"].sum())}
        c[f"autogoles_{lado}"] = int(((ev["type_name"].astype("string") == "Own Goal For") & mascara).sum())
    c["posesiones"] = len(a)
    c["posesiones_sin_admin"] = int((~admin).sum())
    c["posesiones_eq"] = int((es_eq & ~admin).sum())
    c["validas_eq"] = int((es_eq & ~admin & a["is_valid_possession"].astype("boolean").fillna(False)).sum())
    c["presiones"] = int(p["presiones"].sum())
    c["presion_alta"] = razon(float(p["presiones_altas_40m"].sum()), c["presiones"])
    c["perdidas"] = int(p["perdidas"].sum())
    c["recupera_5s"] = razon(float(p["perdidas_regain_5s"].sum()), c["perdidas"])
    ppda = p["ppda_juego_abierto"].dropna()
    c["ppda_media"] = float(ppda.mean()) if len(ppda) else float("nan")
    c["ppda_mediana"] = float(ppda.median()) if len(ppda) else float("nan")
    c["ppda_n"] = len(ppda)
    cob = d.cobertura
    c["eventos"] = d.n_eventos
    c["eventos_cob"] = int(cob["eventos"].sum())
    c["con_frame"] = int(cob["eventos_con_frame"].sum())
    c["pct_frame"] = razon(c["con_frame"], c["eventos_cob"])
    c["pct_frame_min"], c["pct_frame_max"] = float(cob["pct_con_frame"].min()), float(cob["pct_con_frame"].max())
    conteo = p["formacion_1t"].dropna().astype("string").value_counts()
    c["formacion"], c["formacion_n"] = (fmt_formacion(conteo.index[0]), int(conteo.iloc[0])) if len(conteo) \
        else ("n. d.", 0)
    # columnas que solo existen para el America: con valor en el America y nulas en todo el rival
    c["solo_eq"] = [col for col in a.columns if col != "es_eq"
                    and a.loc[~es_eq, col].isna().all() and a.loc[es_eq, col].notna().any()]
    sim = d.comps[d.comps["ajuste"].astype("string") == "simple"]
    lect = sim["lectura"].astype("string").value_counts()
    c["comps_simple"] = len(sim)
    c["comps_ajustadas"] = len(d.comps) - len(sim)
    c["lecturas"] = {k: int(lect.get(k, 0)) for k in LECTURA_ET}
    bajo, alto = d.p04["PERCENTILES"]
    c["ic"] = f"{alto - bajo:g}"  # nivel del IC: 97.5 - 2.5 = 95
    return c


def cuadres(c):
    # Informativos: G+E+P contra partidos y contra resultado, xG por origen contra posesiones, eventos contra 360.
    gep = c["G"] + c["E"] + c["P"]
    if gep != c["n"]:
        _aviso(f"G+E+P = {gep} y hay {c['n']} partidos: {c['n'] - gep} sin goles completos")
    tabla = {k: int(c["resultado_tabla"].get(k, 0)) for k in "GEP"}
    if tabla != {"G": c["G"], "E": c["E"], "P": c["P"]}:
        _aviso(f"G-E-P por goles {c['G']}-{c['E']}-{c['P']} y por la columna resultado {tabla['G']}-{tabla['E']}-"
               f"{tabla['P']}; el reporte usa los goles")
    else:
        _ok(f"G-E-P {c['G']}-{c['E']}-{c['P']}: suman {gep} partidos y coinciden con la columna resultado")
    for lado, ref in (("favor", c["xg_favor"]), ("contra", c["xg_contra"])):
        dif = c[f"xg_origen_{lado}"] - ref
        msg = (f"cuadre xG {lado}: suma por origen {c[f'xg_origen_{lado}']:.2f} contra xG de las posesiones "
               f"{ref:.2f} (dif {dif:+.2f})")
        if abs(dif) > TOL_CUADRE_XG:
            _aviso(msg + f"; pasa de {TOL_CUADRE_XG}")
        else:
            _ok(msg)
    for lado, goles in (("favor", c["gf"]), ("contra", c["gc"])):
        pen, auto = c[f"penales_{lado}"], c[f"autogoles_{lado}"]
        orig = int(sum(v["goles"] for v in c[f"origen_{lado}"].values()))
        msg = (f"goles {lado}: {orig} por origen + {pen['goles']} de penal + {auto} autogoles = "
               f"{orig + pen['goles'] + auto} contra {goles} del partido; penales {lado}: {pen['tiros']} tiros, "
               f"{pen['goles']} goles, {pen['xg']:.1f} xG")
        if orig + pen["goles"] + auto != goles:
            _aviso(msg)
        else:
            _ok(msg)
    if c["eventos"] != c["eventos_cob"]:
        _aviso(f"contexto_eventos tiene {c['eventos']:,} filas y la cobertura 360 suma {c['eventos_cob']:,} eventos")
    else:
        _ok(f"eventos: {c['eventos']:,} en contexto_eventos y en la cobertura 360")


# ---------------------------------------------------------------- figuras

def carpeta_torneo(figuras, torneo):
    for nombre in (torneo, torneo.replace(" ", "_")):
        if (figuras / nombre).is_dir():
            return figuras / nombre
    return None


def incrustar(ruta):
    # PNG a data URI en WebP, reducido a ANCHO_MAX sin recortar.
    with Image.open(ruta) as im:
        im.load()
        if im.width > ANCHO_MAX:
            im = im.resize((ANCHO_MAX, round(im.height * ANCHO_MAX / im.width)), Image.LANCZOS)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=CALIDAD_WEBP, method=4)
        ancho, alto = im.size
    return f"data:image/webp;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}", ancho, alto


def incrustar_recurso(ruta):
    # Logo o foto a data URI: un WebP ya preparado va tal cual; un PNG pasa a WebP sin perdidas (son chicos).
    with Image.open(ruta) as im:
        ancho, alto = im.size
        if ruta.suffix.lower() == ".webp":
            datos = ruta.read_bytes()
        else:
            buf = io.BytesIO()
            im.convert("RGBA").save(buf, "WEBP", lossless=True, method=6)
            datos = buf.getvalue()
    return f"data:image/webp;base64,{base64.b64encode(datos).decode('ascii')}", ancho, alto


def rutas_figura(figuras_dir, fig, torneos):
    # (torneo, ruta) de cada imagen de la figura que existe; las de contexto tienen ademas la de los 91 partidos en la
    # raiz, con torneo "".
    rutas = []
    if fig.contexto and (figuras_dir / fig.archivo).is_file():
        rutas.append(("", figuras_dir / fig.archivo))
    for torneo in torneos:
        carpeta = carpeta_torneo(figuras_dir, torneo)
        ruta = carpeta / fig.archivo.format(torneo=torneo.replace(" ", "_")) if carpeta else None
        if ruta is not None and ruta.is_file():
            rutas.append((torneo, ruta))
    return rutas


def codigos_figuras(presentes):
    # Codigo F{puerta}.{n} de cada figura con al menos una imagen, asignado una sola vez en el orden de FIGURAS.
    codigos, por_puerta = {}, {}
    for fig in FIGURAS:
        if fig.archivo not in presentes:
            continue
        n = por_puerta.get(fig.puerta, 0) + 1
        por_puerta[fig.puerta] = n
        codigos[fig.archivo] = (f"F{fig.puerta}.{n}", f"f{fig.puerta}-{n}")
    return codigos, por_puerta


# ---------------------------------------------------------------- armado

class Reporte:
    # Lleva los codigos F/T por puerta, lo que falta, los textos usados y las imagenes incrustadas o faltantes.
    def __init__(self, cifras, datos, figuras_dir, textos_dir, recursos_dir):
        self.c, self.d, self.figuras_dir, self.textos_dir = cifras, datos, figuras_dir, textos_dir
        self.recursos_dir = recursos_dir
        self.rutas_fig = {f.archivo: rutas_figura(figuras_dir, f, cifras["torneos"]) for f in FIGURAS}
        self.cod_fig, por_puerta = codigos_figuras({a for a, r in self.rutas_fig.items() if r})
        self.contador = {("F", p): n for p, n in por_puerta.items()}
        self.pendientes = []  # (quien, que falta); solo para la consola y --estricto, nunca en el HTML
        self.textos_usados = []  # claves de PENDIENTES que llegaron como md
        self.incrustadas, self.faltantes = [], []  # (codigo, torneo, archivo)
        self.peso_grupo = {}  # "F3.1 titulo" -> bytes
        self.recursos, self.recursos_faltantes = {}, []  # clave -> (uri, ancho, alto); archivos que faltan
        self.primera_cancha = None  # codigo de la primera figura de cancha, la que lleva el pie completo
        self.trazas = []  # (codigo, ancla, puerta, ids): en que objetos se basa cada figura y tabla
        self.defs = {fila[0]: f"def-{slug(fila[0])}" for fila in datos.framework.definiciones[1] if fila}
        self.ic = cifras["ic"]
        self.etiquetas = self.etiquetas_objetos()  # id -> nombre corto, en el orden de la puerta 2

    def etiquetas_objetos(self):
        # id de cada objeto, supuesto y termino de la puerta 2 y el glosario, con el nombre de «Se basa en».
        et = {self.defs[f[0]]: f[0] for f in self.d.framework.definiciones[1] if f}
        et.update({f"def-{slug(n)}": n for n, _ in CONTEXTOS.values()})
        et.update({f"def-{slug(n)}": n for n, _ in self.d.framework.extras})
        et.update({k: corto for k, corto, _ in self.supuestos()})
        et.update({f"term-{slug(t)}": t for t, _ in TERMINOS})
        return et

    def supuestos(self):
        # (id, nombre corto, texto) de cada supuesto; las cifras salen de constantes, del framework o de las tablas.
        c, p04 = self.c, self.d.p04
        defs = {f[0]: f for f in self.d.framework.definiciones[1] if f}
        col = {h.strip().lower(): i for i, h in enumerate(self.d.framework.definiciones[0])}
        donde = {f[0]: f for f in self.d.framework.donde[1] if f}

        def umbral(nombre):
            f = defs.get(nombre)
            i = col.get("umbral")
            t = inline_md(f[i]).rstrip(".") if f and i is not None and i < len(f) else "n. d."
            return t[:1].lower() + t[1:] if t[:2].isalpha() else t  # va despues de dos puntos

        def consid(nombre):
            f = defs.get(nombre)
            i = col.get("fórmula o consideración")
            return inline_md(f[i]) if f and i is not None and i < len(f) else ""

        penal_valida = inline_md(donde["Posesión válida"][-1]) if "Posesión válida" in donde else ""
        x_alta = LARGO_CANCHA_YD - ZONA_ALTA_M / YARDA_M
        if f"{ZONA_ALTA_M} metros" not in umbral("Zona de presión alta"):
            _aviso(f"el framework ya no dice {ZONA_ALTA_M} metros para la zona de presion alta; revisa ZONA_ALTA_M")
        bajo, alto = p04["PERCENTILES"]
        return [
            ("sup-posesion", "Umbral de posesión",
             f"<b>Posesión válida:</b> {umbral('Posesión válida')}. {consid('Posesión válida')} {penal_valida}"),
            ("sup-penales", "Penales aparte",
             f"<b>Penales:</b> fuera de todo tiro y de todo xG; se cuentan aparte ({c['penales_favor']['tiros']} a "
             f"favor y {c['penales_contra']['tiros']} en contra)."),
            ("sup-administrativas", "Sin posesiones administrativas",
             f"<b>Posesiones administrativas</b> (alineación, medio tiempo, cambios): fuera; quedan "
             f"{entero(c['posesiones_sin_admin'])} de {entero(c['posesiones'])}."),
            ("sup-presion-alta", "Presión alta: 40 m",
             f"<b>Zona de presión alta:</b> últimos {ZONA_ALTA_M} m de la cancha rival (x ≥ {x_alta:.2f} yd en una "
             f"cancha de {LARGO_CANCHA_YD} yd)."),
            ("sup-fase-presion", "Fase de presión: 10 s",
             f"<b>Fase de presión:</b> {umbral('Fase de presión')}. {esc(NOTA_OBJETO['Fase de presión'])}"),
            ("sup-transicion", "Transición: 5 s", f"<b>Transición:</b> {umbral('Transición')}."),
            ("sup-tercio-final", "Tercio final",
             f"<b>Tercio final:</b> x ≥ {TERCIO_FINAL_X:g} yd, el último tercio de una cancha de {LARGO_CANCHA_YD} yd."),
            ("sup-rival", "Rival por tercio de xG", f"<b>Rival fuerte, medio o débil:</b> {esc(DEF_RIVAL)}"),
            ("sup-desde-america", "Desde el América",
             "<b>Marcador y superioridad numérica:</b> se leen desde el América, también en las jugadas del rival. "
             "La superioridad solo cuenta expulsiones de jugadores que estaban en cancha."),
            ("sup-360", "360 solo con frame",
             f"<b>Métricas del 360:</b> solo con los eventos que traen frame ({porciento(c['pct_frame'])} de "
             f"{entero(c['eventos_cob'])}); no se filtra por número de jugadores visibles."),
            ("sup-bootstrap", "Bootstrap por partido",
             f"<b>Comparaciones:</b> bootstrap de partidos completos ({entero(p04['REPLICAS'])} réplicas, IC del "
             f"{alto - bajo:g}%); hay «diferencia» desde |efecto| ≥ {p04['EFECTO_MIN']}, y una celda es inestable con "
             f"menos de {p04['MIN_PARTIDOS']} partidos o {p04['MIN_OBS']} observaciones."),
        ]

    def base_html(self, ids, cod, ancla, puerta):
        # Linea «Se basa en» con enlaces a la puerta 2; registra la traza para la matriz y para verificar().
        ids = tuple(dict.fromkeys(ids))
        self.trazas.append((cod, ancla, puerta, ids))
        enlaces = " · ".join(f'<a href="#{i}">{esc(self.etiquetas.get(i, i))}</a>' for i in ids)
        return f'<p class="base">Se basa en: {enlaces}</p>' if ids else ""

    def codigo(self, tipo, puerta):
        n = self.contador.get((tipo, puerta), 0) + 1
        self.contador[(tipo, puerta)] = n
        return f"{tipo}{puerta}.{n}", f"{tipo.lower()}{puerta}-{n}"

    def pendiente(self, clave):
        # El md de --textos si existe; si no, el espacio se omite y se avisa en la consola.
        quien, falta = PENDIENTES[clave]
        archivo = self.textos_dir / f"{clave}.md"
        if archivo.is_file():
            try:
                cuerpo = md_a_html(leer_md(archivo))
            except (OSError, UnicodeDecodeError) as e:
                _aviso(f"no se pudo leer {archivo}: {type(e).__name__}; el espacio {clave} se omite")
            else:
                if cuerpo:
                    self.textos_usados.append(clave)
                    return f'<div class="aporte" data-texto="{esc(clave)}">{cuerpo}</div>'
                _aviso(f"{archivo.name} esta vacio; el espacio se omite")
        else:
            _aviso(f"falta {clave}.md en {self.textos_dir}; el espacio se omite")
        self.pendientes.append((quien, falta))
        return ""

    def recurso(self, clave, clase, decorativa=False):
        # <img> de un logo o de la foto de --recursos; si falta, "" y se avisa una vez.
        if clave not in self.recursos:
            r = RECURSOS[clave]
            ruta = self.recursos_dir / r.archivo
            self.recursos[clave] = None
            if ruta.is_file():
                try:
                    self.recursos[clave] = incrustar_recurso(ruta)
                except (OSError, ValueError, Image.DecompressionBombError) as e:
                    _aviso(f"no se pudo incrustar {r.archivo}: {type(e).__name__}: {e}")
            if self.recursos[clave] is None:
                _aviso(f"falta {r.archivo} en {self.recursos_dir}; se omite (lo deja preparar_recursos.py)")
                self.recursos_faltantes.append(r.archivo)
                self.pendientes.append(("Yordi", f"recurso {r.archivo}"))
        if self.recursos[clave] is None:
            return ""
        uri, ancho, alto = self.recursos[clave]
        alt = "" if decorativa else esc(RECURSOS[clave].alt)
        return f'<img class="{clase}" src="{uri}" width="{ancho}" height="{alto}" alt="{alt}" decoding="async">'

    def enlace_def(self, nombre_def, texto):
        ancla = self.defs.get(nombre_def)
        return f'<a href="#{ancla}" class="def">{texto}</a>' if ancla else texto

    def enlace_fig(self, archivo):
        cod, ancla = self.cod_fig[archivo]
        return f'<a href="#{ancla}">{cod}</a>'

    # -- piezas comunes

    def cifra(self, valor, texto):
        return f'<div class="cifra"><p class="cifra-valor">{valor}</p><p class="cifra-texto">{texto}</p></div>'

    def filas_talon(self, items):
        # Filas tipo talon: etiqueta (y su detalle) a la izquierda, cifra tabular a la derecha, filete fino.
        filas = "".join(f'<div{" class=\"apilar\"" if "<small>" in valor else ""}><dt>{et}<small>{detalle}</small>'
                        f'</dt><dd>{valor}</dd></div>' for et, valor, detalle in items)
        return f'<dl class="filas-talon">{filas}</dl>'

    def tabla(self, puerta, titulo, encabezados, filas, pie=None, nota="", numericas=(), id_tabla=None,
              aparte=None, base=()):
        cod, ancla = self.codigo("T", puerta)
        th = "".join(f'<th scope="col"{NUM if i in numericas else ""}>{h}</th>'
                     for i, h in enumerate(encabezados))

        def fila(f):
            return "<tr>" + "".join(f'<td{NUM if i in numericas else ""}>{v}</td>' for i, v in enumerate(f)) + "</tr>"

        cuerpo = "".join(fila(f) for f in filas)
        fila_aparte = fila(aparte).replace("<tr>", '<tr class="aparte">', 1) if aparte else ""
        tfoot = f"<tfoot>{fila(pie)}{fila_aparte}</tfoot>" if pie else ""
        id_attr = f' id="{id_tabla}"' if id_tabla else ""
        nota_html = f'<p class="nota">{nota}</p>' if nota else ""
        nota_html += self.base_html(base, cod, ancla, puerta)
        return (f'<figure class="tabla" id="{ancla}"><figcaption><span class="codigo">{cod}</span> '
                f'{titulo}</figcaption><div class="tabla-caja" role="region" tabindex="0" '
                f'aria-label="{cod} {esc(re.sub("<[^>]+>", "", titulo))}"><table{id_attr}><thead><tr>{th}</tr>'
                f'</thead><tbody>{cuerpo}</tbody>{tfoot}</table></div>{nota_html}</figure>')

    def figura(self, fig, pie=None):
        # Figura con una pestaña por torneo; las de contexto llevan antes la de los 91 partidos (torneo ""). Lo que
        # falta se omite.
        rutas = dict(self.rutas_fig[fig.archivo])
        torneos = ([""] if fig.contexto else []) + list(self.c["torneos"])
        todos = f"{self.c['n']} partidos"
        cod, ancla = self.cod_fig.get(fig.archivo, ("F?", ""))
        grupo = f"{cod} {fig.titulo}"
        paneles = []
        for i, torneo in enumerate(torneos):
            archivo = fig.archivo.format(torneo=torneo.replace(" ", "_"))
            uri = None
            if torneo in rutas:
                try:
                    uri, ancho, alto = incrustar(rutas[torneo])
                except (OSError, ValueError, Image.DecompressionBombError) as e:
                    _aviso(f"no se pudo incrustar {torneo or '(raiz)'}/{archivo}: {type(e).__name__}: {e}")
            if not uri:
                self.faltantes.append((cod, torneo or "(raiz)", archivo))
                self.pendientes.append(("Pablo", f"figura {cod} de {torneo or 'la raiz'} ({archivo})"))
                continue
            self.incrustadas.append((cod, torneo or "(raiz)", archivo))
            self.peso_grupo[grupo] = self.peso_grupo.get(grupo, 0) + len(uri)
            et = torneo or todos
            img = (f'<div class="marco"><img src="{uri}" width="{ancho}" height="{alto}" loading="lazy" '
                   f'decoding="async" alt="{esc(fig.titulo)}, {esc(et)}. {esc(fig.alt)}."></div>')
            paneles.append(f'<div class="panel" id="{ancla}-p{i}" data-torneo="{esc(et)}">'
                           f'<p class="panel-torneo">{esc(et)}</p>{img}</div>')
        if not paneles:
            return ""
        pie = esc((pie or fig.pie).replace("{n}", str(self.c["n"])))
        if len(paneles) == 1:
            cuerpo = paneles[0]
        else:
            de = "Partidos" if fig.contexto else "Torneo"
            inicio = f' data-inicio="{esc(todos)}"' if fig.contexto else ""  # pestaña con que abren las de contexto
            cuerpo = (f'<div class="pestanas" id="{ancla}-pestanas" data-pestanas="{de} de {esc(fig.titulo.lower())}"'
                      f'{inicio}>{"".join(paneles)}</div>')
        base = self.base_html(BASE_FIGURA.get(fig.archivo, ()), cod, ancla, fig.puerta)
        return (f'<figure class="fig" id="{ancla}"><figcaption><span class="codigo">{cod}</span> {esc(fig.titulo)}'
                f'</figcaption><p class="pie">{pie}</p>{base}{cuerpo}</figure>')

    def figuras_de(self, puerta):
        return "".join(self.figura(f) for f in FIGURAS if f.puerta == puerta and not f.contexto)

    def letrero(self, ancla, numero, titulo, linea):
        return (f'<header class="letrero"><span class="letrero-num" aria-hidden="true">{numero}</span><div>'
                f'<h2 id="{ancla}-titulo"><span class="sr">Puerta {numero}. </span>{esc(titulo)}</h2>'
                f'<p>{esc(linea)}</p></div></header>')

    def puerta(self, ancla, cuerpo):
        i = next(k for k, p in enumerate(PUERTAS) if p[0] == ancla)
        _, numero, _, titulo, linea = PUERTAS[i]
        return (f'<section class="puerta" id="{ancla}" aria-labelledby="{ancla}-titulo">'
                f'{self.letrero(ancla, numero, titulo, linea)}<div class="sector">{cuerpo}</div></section>')

    # -- secciones

    def inicio(self):
        c = self.c
        periodo = f"{c['torneos'][0]} – {c['torneos'][-1]}"
        foto = self.recurso("jardine", "foto-img")
        escudo = self.recurso("america", "escudo-img")
        clase = " con-foto" if foto else ""
        escudo = f'<div class="talon-escudo">{escudo}</div>' if escudo else ""
        foto = f'<div class="boleto-foto">{foto}</div>' if foto else ""
        autores = "<br>".join(esc(a) for a in AUTORES)
        return f"""<section class="portada" id="inicio" aria-label="Portada">
<div class="boleto{clase}">
<div class="boleto-cuerpo">
<div class="boleto-texto">
<h1>Jardine<br>en el<br><span>América</span></h1>
<p class="periodo">{esc(periodo)} · {c['regular']} de fase regular y {c['liguilla']} de liguilla</p>
<p class="pregunta">{esc(PREGUNTA_RETO)}</p>
</div>
{foto}
</div>
<div class="talon">
<div class="talon-arriba">
<p class="talon-grande">{c['n']}<span>partidos</span></p>
{escudo}
</div>
<div class="marcador">
<p class="celda"><b>{c['G']}</b><span>ganados</span></p>
<p class="celda"><b>{c['E']}</b><span>empatados</span></p>
<p class="celda"><b>{c['P']}</b><span>perdidos</span></p>
</div>
<dl class="filas">
<div><dt>Goles a favor y en contra (total)</dt><dd>{c['gf']} – {c['gc']}</dd></div>
<div><dt>xG a favor y en contra (total)</dt><dd>{decimal(c['xg_favor'])} – {decimal(c['xg_contra'])}</dd></div>
<div><dt>xG por partido</dt><dd>{decimal(c['xg_favor'] / c['n'], 2)} – {decimal(c['xg_contra'] / c['n'], 2)}</dd></div>
</dl>
<p class="talon-nota">{esc(NOTA_PENALES)}</p>
<p class="talon-pie"><span class="autores">{autores}<br><b>{esc(FACULTAD)}</b></span></p>
</div>
</div>
</section>"""

    def s_pregunta(self):
        c, p, a = self.c, self.d.partidos, self.d.posesiones
        torneo_pos = a[["match_id", "es_eq", "xg"]].merge(p[["match_id", "torneo"]], on="match_id", how="left")
        filas = []
        for t in c["torneos"]:
            sel = p[p["torneo"].astype("string") == t]
            g, e, pe = resultados(sel)
            xg = torneo_pos[torneo_pos["torneo"].astype("string") == t]
            eq = xg["es_eq"].astype("boolean").fillna(False)
            filas.append([esc(t), entero(len(sel)), entero((sel["stage"].astype("string") == "fase final").sum()),
                          entero(g), entero(e), entero(pe), entero(sel["goles_eq"].sum()),
                          entero(sel["goles_rival"].sum()), decimal(xg.loc[eq, "xg"].sum()),
                          decimal(xg.loc[~eq, "xg"].sum())])
        pie = ["Total", entero(c["n"]), entero(c["liguilla"]), entero(c["G"]), entero(c["E"]), entero(c["P"]),
               entero(c["gf"]), entero(c["gc"]), decimal(c["xg_favor"]), decimal(c["xg_contra"])]
        t11 = self.tabla(1, "Partidos y resultados por torneo",
                         ["Torneo", "PJ", "Liguilla", "G", "E", "P", "GF", "GC", "xG favor", "xG contra"],
                         filas, pie, numericas=range(1, 10),
                         nota="PJ: partidos jugados, la n de cada fila. G, E y P salen de los goles, con tiempo extra "
                              "y sin la tanda de penales.", base=("def-fase-del-torneo", "sup-penales", "term-xg"))
        cuerpo = self.cifra(f"{c['n_finales']}<small> finales</small>",
                            f"jugadas a ida y vuelta ({c['finales']} partidos): una en cada uno de los "
                            f"{len(c['torneos'])} torneos.")
        cuerpo += self.pendiente("pato_introduccion")
        cuerpo += t11
        return self.puerta("pregunta", cuerpo)

    def s_marco(self):
        # Los objetos de las metricas finales del framework como tarjetas, por grupo, con un recorrido de fases.
        c, fw = self.c, self.d.framework
        enc, filas = fw.definiciones
        col = {h.strip().lower(): i for i, h in enumerate(enc)}
        defs = {f[0]: f for f in filas if f}

        def celda(f, nombre):
            i = col.get(nombre)
            return inline_md(f[i]) if i is not None and i < len(f) else ""

        def tarjeta(nombre):
            f = defs[nombre]
            nota = NOTA_OBJETO.get(nombre)
            nota = f'<p class="objeto-nota">{esc(nota)}</p>' if nota else ""
            consid = celda(f, "fórmula o consideración")
            consid = f'<p class="objeto-consid">{consid}</p>' if consid else ""
            return (f'<article class="objeto" id="{self.defs[nombre]}"><h4>{inline_md(nombre)}</h4>'
                    f'<p class="objeto-que">{celda(f, "qué mide")}</p>{consid}'
                    f'<p class="objeto-umbral"><span>Umbral</span>{celda(f, "umbral")}</p>{nota}</article>')

        usados, grupos, por_grupo = set(), [], []
        for titulo, filas_grupo in GRUPOS_MARCO:
            partes, n = [], 0
            for fila in filas_grupo:
                presentes = [x for x in fila if x in defs]
                for x in fila:
                    if x not in defs:
                        _aviso(f"el framework no trae la metrica «{plano(x)}»; su tarjeta se omite")
                if not presentes:
                    continue
                usados.update(presentes)
                n += len(presentes)
                tarjetas = "".join(f"<li>{tarjeta(x)}</li>" for x in presentes)
                if len(fila) == 3 and titulo == GRUPOS_MARCO[0][0]:
                    partes.append(f'<p class="recorrido-et">{esc(RECORRIDO)}</p><ol class="objetos recorrido">'
                                  f'{tarjetas}</ol>')
                else:
                    partes.append(f'<ul class="objetos">{tarjetas}</ul>')
            if partes:
                grupos.append(f'<h4 class="marco-grupo">{esc(titulo)}</h4>{"".join(partes)}')
                por_grupo.append(n)
        resto = [x for x in defs if x not in usados]
        if resto:
            _aviso(f"metricas del framework sin grupo en GRUPOS_MARCO: {plano(', '.join(resto))}; van en «Otras»")
            grupos.append('<h4 class="marco-grupo">Otras</h4><ul class="objetos">'
                          + "".join(f"<li>{tarjeta(x)}</li>" for x in resto) + "</ul>")
        intro = ('<p class="marco-intro">El reporte lee al América de Jardine con objetos y supuestos que el '
                 'equipo fijó antes de medir.</p>')
        datos = (f'<p class="marco-datos">{c["n"]} partidos ({c["regular"]} de fase regular y {c["liguilla"]} de '
                 f'liguilla) · Hudl StatsBomb, eventos y 360 · {porciento(c["pct_frame"])} de los eventos con frame '
                 f'360 · {entero(c["posesiones_sin_admin"])} posesiones de juego</p>')
        # objetos de contexto: niveles de 04_contexto.py, la referencia primero
        filas_ctx, ids_ctx = [], []
        for ctx, (nombre, _) in CONTEXTOS.items():
            niveles = list(self.d.p04["NIVELES"].get(ctx, []))
            if not niveles:
                continue
            txt = [f"{nivel_corto(ctx, niveles[0])} (referencia)"] + [nivel_corto(ctx, n) for n in niveles[1:]]
            filas_ctx.append([nombre, ", ".join(txt), DEF_RIVAL if ctx == "rival_strength_tercil"
                              else DEF_CONTEXTOS.get(ctx, "")])
            ids_ctx.append(f"def-{slug(nombre)}")
        t_ctx = tabla_md(["Contexto", "Niveles", "Qué es"], filas_ctx, ids=ids_ctx, etiqueta="Objetos de contexto")
        extras = self.d.framework.extras
        t_otros = (tabla_md(["Objeto", "Qué es"], [[n, t] for n, t in extras], ids=[f"def-{slug(n)}" for n, _ in extras],
                            etiqueta="Otros objetos") if extras else "")
        objetos = (f'<h3>Definición de objetos</h3>{"".join(grupos)}'
                   f'<h4 class="marco-grupo">El contexto de cada jugada</h4>{t_ctx}'
                   + (f'<h4 class="marco-grupo">Presión tras la pérdida y jugadores</h4>{t_otros}' if t_otros else "")
                   + '<p class="nota">Las métricas que salen de estos objetos (xG, PPDA, OBV, verticalidad y las '
                     'demás) están en los <a href="#terminos">términos del glosario</a>.</p>')
        sups = "".join(f'<li id="{k}">{texto}</li>' for k, _, texto in self.supuestos())
        supuestos = f'<h3>Supuestos explícitos</h3><ul class="supuestos">{sups}</ul>'
        coherencia = ('<h3>Coherencia interna</h3><p>Las figuras, las tablas y las métricas del reporte salen de estos '
                      'objetos y supuestos. Bajo cada figura y cada tabla, la línea «Se basa en» enlaza a los que usa; '
                      'la tabla de abajo los junta por objeto.</p><details class="pliegue" id="matriz"><summary>Dónde '
                      'se usa cada objeto y supuesto</summary><!--MATRIZ--></details>')
        cap = "".join(f"<li>{esc(x.format(primero=c['torneos'][0], ultimo=c['torneos'][-1]))}</li>"
                      for x in ALCANCE_CAPTURA)
        fuera = "".join(f"<li>{esc(x)}</li>" for x in ALCANCE_FUERA)
        alcance = (f'<h3>Alcance y límites</h3><div class="alcance"><div><h4>Qué captura</h4><ul>{cap}</ul></div>'
                   f'<div><h4>Qué queda fuera</h4><ul>{fuera}</ul></div></div><p class="nota">Cómo pesan estos '
                   f'límites en los resultados está en la <a href="#limitaciones">puerta 8</a>.</p>')
        return self.puerta("marco", intro + datos + objetos + supuestos + coherencia + alcance)

    def matriz(self):
        # Objeto o supuesto -> figuras y tablas que lo usan y en que puertas; sale de las trazas, no a mano.
        usos = {}
        for cod, ancla, puerta, ids in self.trazas:
            for i in ids:
                usos.setdefault(i, []).append((cod, ancla, puerta))
        filas = []
        for i, nombre in self.etiquetas.items():
            if i not in usos:
                continue
            cods = " · ".join(f'<a href="#{a}">{esc(c)}</a>' for c, a, _ in usos[i])
            puertas = ", ".join(str(x) for x in sorted({pu for _, _, pu in usos[i]}))
            filas.append(f'<tr><th scope="row"><a href="#{i}">{esc(nombre)}</a></th><td>{cods}</td><td>{puertas}</td>'
                         f'</tr>')
        return ('<div class="tabla-caja" role="region" tabindex="0" aria-label="Dónde se usa cada objeto"><table '
                'class="doc matriz"><thead><tr><th scope="col">Objeto o supuesto</th><th scope="col">Figuras y '
                f'tablas</th><th scope="col">Puertas</th></tr></thead><tbody>{"".join(filas)}</tbody></table></div>')


    def pliegue_metodo(self):
        c, p04 = self.c, self.d.p04
        lec = c["lecturas"]
        lista_inest = esc(celdas_inestables(self.d.celdas))
        inest_frase = (f"En esta versión quedan inestables las celdas {lista_inest}." if lista_inest else
                       "En esta versión ninguna celda queda inestable.")
        metodo = f"""<details class="pliegue" id="como-leer"><summary>Cómo comparamos por contexto</summary>
<p>Cada métrica se calcula en cada nivel de cada contexto y se compara contra un nivel de referencia, por ejemplo perdiendo contra empatando o de local contra de visitante. Los intervalos salen de un bootstrap que remuestrea partidos completos: {entero(p04['REPLICAS'])} réplicas con semilla fija ({p04['SEMILLA']}), así que dos corridas dan lo mismo. Todos los intervalos son del {self.ic}%.</p>
<p>Además de la diferencia, cada comparación trae un tamaño de efecto que no depende de la unidad: g de Hedges para las medias, h de Cohen para las proporciones y, para las medianas, la diferencia de medianas dividida entre su dispersión (MAD). Cada una recibe una de estas lecturas:</p>
<ul class="lecturas">
<li>{marca_lectura('diferencia')} El intervalo de la diferencia no toca el 0, el efecto es de al menos {p04['EFECTO_MIN']} en valor absoluto y las dos celdas son estables. Es lo que el reporte afirma.</li>
<li>{marca_lectura('diferencia pequena')} El intervalo no toca el 0 y las dos celdas son estables, pero el efecto es menor que {p04['EFECTO_MIN']}: un cambio chico frente a la variación entre posesiones o partidos, que se lee como pista.</li>
<li>{marca_lectura('indicio')} El intervalo no toca el 0 y el efecto llega a {p04['EFECTO_MIN']}, pero alguna celda es inestable. Señala algo que revisar, sin afirmarlo.</li>
<li>{marca_lectura('sin diferencia clara')} Cualquier otro caso. No prueba que no haya cambio: solo que con estos datos no se puede afirmar.</li>
</ul>
<p>De las {entero(c['comps_simple'])} comparaciones de ajuste simple, {entero(lec['diferencia'])} dan diferencia, {entero(lec['diferencia pequena'])} diferencia pequeña, {entero(lec['indicio'])} indicio y {entero(lec['sin diferencia clara'])} sin diferencia clara.</p>
<p>Una celda es inestable si tiene menos de {p04['MIN_PARTIDOS']} partidos o, cuando se mide por posesión o por evento, menos de {p04['MIN_OBS']} observaciones. {inest_frase}</p>
<p>Las cuentas y las tarjetas de esta puerta usan las {entero(c['comps_simple'])} comparaciones de ajuste simple. Las {entero(c['comps_ajustadas'])} del marcador ajustadas por mitad del partido y tercil del rival repiten esas comparaciones y solo están en la tabla completa.</p>
</details>"""
        return metodo

    def tabla_origen(self, puerta, lado):
        c = self.c
        org = c[f"origen_{lado}"]
        total = {m: sum(v[m] for v in org.values()) for m in ("tiros", "goles", "xg")}
        filas = [[esc(nombre), entero(org[o]["tiros"]), entero(org[o]["goles"]), decimal(org[o]["xg"]),
                  porciento(razon(org[o]["xg"], total["xg"]))] for o, nombre in ORIGENES]
        pie = ["Total", entero(total["tiros"]), entero(total["goles"]), decimal(total["xg"]),
               porciento(razon(total["xg"], total["xg"]))]
        goles = c["gf"] if lado == "favor" else c["gc"]
        pen, auto = c[f"penales_{lado}"], c[f"autogoles_{lado}"]
        orig = int(total["goles"])
        partes = [f"{entero(orig)} goles por origen", f"{entero(pen['goles'])} de penal"]
        if auto:
            partes.append(f"{entero(auto)} autogoles del {'rival' if lado == 'favor' else 'América'}")
        nota = (f"Tiros: la n de cada fila. La fila de penales no se suma al total. {y_lista(partes)} dan los "
                f"{entero(goles)} goles {'a favor' if lado == 'favor' else 'en contra'}")
        suma = orig + pen["goles"] + auto
        if suma == goles:
            nota += "."
        else:
            nota += f". La suma es {entero(suma)} y los goles del partido son {entero(goles)}: no cuadra."
            _aviso(f"goles {lado}: por origen {orig} + penales {pen['goles']} + autogoles {auto} = {suma} y los "
                   f"partidos suman {goles}")
        aparte = ["Penales (aparte)", entero(pen["tiros"]), entero(pen["goles"]), decimal(pen["xg"]), ""]
        titulo = "xG a favor por origen" if lado == "favor" else "xG en contra por origen"
        return self.tabla(puerta, titulo, ["Origen", "Tiros", "Goles", "xG", "% xG"], filas, pie, nota,
                          numericas=range(1, 5), aparte=aparte, base=("sup-penales", "term-xg"))

    def s_ofensiva(self):
        c = self.c
        cuerpo = self.cifra(decimal(razon(c["xg_favor"], c["n"]), 2),
                            f"xG por partido a favor: {decimal(c['xg_favor'])} en {c['n']} partidos.")
        cuerpo += self.filas_talon([
            ("Goles a favor", entero(c["gf"]),
             f"{decimal(razon(c['gf'], c['n']), 2)} por partido; n = {c['n']} partidos"),
            (self.enlace_def("Posesión válida", "Posesiones válidas"), entero(c["validas_eq"]),
             f"{porciento(razon(c['validas_eq'], c['posesiones_eq']))} de {entero(c['posesiones_eq'])} posesiones "
             f"del América"),
        ])
        cuerpo += self.pendiente("lee_ofensiva")
        cuerpo += self.tabla_origen(3, "favor")
        cuerpo += self.figuras_de(3)
        return self.puerta("ofensiva", cuerpo)

    def s_defensa(self):
        c = self.c
        cuerpo = self.cifra(decimal(razon(c["xg_contra"], c["n"]), 2),
                            f"xG por partido en contra: {decimal(c['xg_contra'])} en {c['n']} partidos.")
        cuerpo += self.filas_talon([
            ("Goles en contra", entero(c["gc"]),
             f"{decimal(razon(c['gc'], c['n']), 2)} por partido; n = {c['n']} partidos"),
            ("PPDA en juego abierto", f"{decimal(c['ppda_media'])} <small>media</small> · "
                                      f"{decimal(c['ppda_mediana'])} <small>mediana</small>",
             f"n = {c['ppda_n']} partidos; más alto es menos presión"),
            (self.enlace_def("Zona de presión alta", "Presiones en los últimos 40 m"), porciento(c["presion_alta"]),
             f"de {entero(c['presiones'])} presiones"),
            (self.enlace_def("Transición", "Pérdidas recuperadas en 5 s"), porciento(c["recupera_5s"]),
             f"de {entero(c['perdidas'])} pérdidas"),
        ])
        cuerpo += self.pendiente("lee_defensa")
        cuerpo += self.tabla_origen(4, "contra")
        cuerpo += self.figuras_de(4)
        return self.puerta("defensa", cuerpo)

    def s_contexto(self):
        c, d = self.c, self.d
        celda = {(r.metrica, r.contexto, r.nivel): r for r in d.celdas.itertuples()}
        meta = d.celdas.drop_duplicates("metrica").set_index("metrica")
        sim = d.comps[d.comps["ajuste"].astype("string") == "simple"]
        orden_ctx = list(CONTEXTOS) + [x for x in sim["contexto"].astype("string").unique() if x not in CONTEXTOS]
        for x in orden_ctx[len(CONTEXTOS):]:
            _aviso(f"contexto {plano(x)} sin nombre legible en CONTEXTOS; se muestra como viene")
        lec = c["lecturas"]
        # solo las de ajuste simple; el detalle del ajuste esta en el plegable «Cómo comparamos por contexto»
        cuerpo = self.cifra(f"{lec['diferencia']}<small> de {c['comps_simple']}</small>",
                            'comparaciones muestran una diferencia clara; abajo, la más fuerte de cada contexto. '
                            '<a href="#como-leer">Cómo leerlas</a>.')
        cuerpo += self.pliegue_metodo()
        tarjetas, filas_fig = [], []
        for ctx in orden_ctx:
            sel = sim[sim["contexto"].astype("string") == ctx]
            if sel.empty:
                continue
            hall = sel[sel["lectura"].astype("string").isin(["diferencia", "indicio"])]
            hall = hall.assign(_orden=(hall["lectura"].astype("string") != "diferencia").astype(int),
                               _abs=-hall["efecto"].abs()).sort_values(["_orden", "_abs"])
            filas_fig += [(ctx, r, meta.loc[r.metrica]) for r in hall.itertuples()]
            tarjetas.append(self.tarjeta(ctx, sel, hall, meta, celda))
        cuerpo += "".join(tarjetas)
        cuerpo += (f'<details class="pliegue" id="tamanos-de-efecto"><summary>Tamaño de efecto de cada comparación '
                   f'con diferencia</summary>{self.f51(filas_fig)}</details>')
        cuerpo += self.t51(meta)
        return self.puerta("contexto", cuerpo)

    def tarjeta(self, ctx, sel, hall, meta, celda):
        # Un contexto: su hallazgo principal (la «diferencia» de mayor |efecto|, o el indicio si no hay ninguna), la
        # cifra de cada nivel con su n, la lectura, otro hallazgo de otra metrica si lo hay y la figura de cancha.
        nombre, en_frase = CONTEXTOS.get(ctx, (ctx, ctx))
        conteo = sel["lectura"].astype("string").value_counts()
        partes = [f"{int(conteo.get('diferencia', 0))} con diferencia"]
        if int(conteo.get("indicio", 0)):
            partes.append(f"{int(conteo.get('indicio', 0))} con indicio")
        partes += [f"{int(conteo.get('diferencia pequena', 0))} con diferencia pequeña",
                   f"{int(conteo.get('sin diferencia clara', 0))} sin diferencia clara"]
        conteo_txt = f'<p class="hallazgo-conteo">{len(sel)} comparaciones en este contexto: {y_lista(partes)}.</p>'
        fig = next((self.figura_cancha(f) for f in FIGURAS if f.contexto == ctx), "")
        filas = list(hall.itertuples())
        id_ctx = f"ctx-{slug(ctx)}"
        if not filas:
            cuerpo = (f'<p class="hallazgo-titular">Sin diferencias claras según {esc(en_frase)}</p>'
                      f'<p>Ninguna comparación de este contexto muestra una diferencia clara ni un indicio.</p>')
        else:
            r = filas[0]
            m = meta.loc[r.metrica]
            unidad, obs = m["unidad"], m["nivel_dato"]
            cuerpo = (f'<p class="hallazgo-titular">{esc(self.titular(ctx, r, m))}</p>'
                      f'{self.niveles(ctx, r, m, celda)}'
                      f'<p class="hallazgo-lectura">{marca_lectura(r.lectura, r.inestable)} '
                      f'{esc(capital(nivel_corto(ctx, r.nivel)))} contra {esc(nivel_corto(ctx, r.referencia))}: '
                      f'{fmt_dif(r.diferencia, unidad)} (IC {self.ic}%: {fmt_dif(r.dif_ic_inf, unidad, False)} a '
                      f'{fmt_dif(r.dif_ic_sup, unidad, False)}). <span class="club-n">n = {entero(r.n_obs_nivel)} y '
                      f'{entero(r.n_obs_ref)} {esc(OBS_ET.get(obs, obs))}</span></p>')
            otra = next((t for t in filas[1:] if t.metrica != r.metrica and t.lectura == "diferencia"), None)
            if otra is not None:
                cuerpo += f'<p class="hallazgo-tambien">{self.tambien(ctx, otra, meta.loc[otra.metrica], celda)}</p>'
        definicion = f'<p class="hallazgo-def">{esc(DEF_CONTEXTO[ctx])}</p>' if ctx in DEF_CONTEXTO else ""
        return (f'<section class="hallazgo" aria-labelledby="{id_ctx}"><h3 id="{id_ctx}">{esc(nombre)}</h3>'
                f'{definicion}{cuerpo}{conteo_txt}{fig}</section>')

    def figura_cancha(self, fig):
        # La primera figura de cancha lleva el pie completo; las siguientes solo dicen sus columnas y remiten a ella.
        # Con pestañas por torneo, cada una dice ademas que niveles no se dibujan por pocos datos.
        por_torneo = len(self.rutas_fig[fig.archivo]) > 1
        pocos = self.pocos_datos(fig.contexto) if por_torneo else ""
        primera = self.primera_cancha
        if primera is None:
            html_fig = self.figura(fig, pie=fig.pie + (f" {PIE_CANCHA_TORNEOS}" if por_torneo else "") + pocos)
            if html_fig:
                self.primera_cancha = self.cod_fig[fig.archivo][0]
            return html_fig
        corto = (f"Una columna por {COLUMNAS_CANCHA[fig.contexto]}. Se lee igual que {primera}: pases arriba, "
                 f"tiros en medio y acciones defensivas abajo, con la altura media de recuperación.")
        return self.figura(fig, pie=corto + pocos)

    def pocos_datos(self, ctx):
        # « En Clausura 2025, rival débil no se dibuja (4 partidos, 416 min).», con la regla de MIN_*_CANCHA.
        p = self.d.partidos
        mins = {k: p[f"minutos_{k}"].astype("float64").fillna(0) for k in ("perdiendo", "empatando", "ganando")}
        total = sum(mins.values())
        if ctx == "score_state":
            niveles = {k: (m > 0, m) for k, m in mins.items()}
        elif ctx == "is_home":
            local = p["is_home"].astype("boolean").fillna(False)
            niveles = {"local": (local, total), "visitante": (~local, total)}
        elif ctx == "rival_strength_tercil":
            t = p["rival_strength_tercil"].astype("string")
            niveles = {f"rival {k}": (t == k, total) for k in ORDEN_TARJETA[ctx]}
        else:
            return ""
        frases = []
        for torneo in self.c["torneos"]:
            en = (p["torneo"].astype("string") == torneo).fillna(False)
            for nivel, (mascara, minutos) in niveles.items():
                sel = (en & mascara.fillna(False)).to_numpy(dtype=bool)
                n, m = int(sel.sum()), float(minutos[sel].sum())
                if n < MIN_PARTIDOS_CANCHA or m < MIN_MINUTOS_CANCHA:
                    frases.append(f"en {torneo}, {nivel} ({n} partidos, {m:,.0f} min)")
        return f" No se dibuja por pocos datos: {y_lista(frases)}." if frases else ""

    def titular(self, ctx, r, m):
        # «Perdiendo, el América tiene más el balón»; sin frase propia, «…, la métrica sube».
        sube = pd.notna(r.diferencia) and r.diferencia > 0
        donde = capital(nivel_frase(ctx, r.nivel))
        if r.metrica in FRASE_METRICA:
            return f"{donde}, el América {FRASE_METRICA[r.metrica][0 if sube else 1]}"
        return f"{donde}, {m['etiqueta_metrica'].lower()} {'sube' if sube else 'baja'}"

    def niveles(self, ctx, r, m, celda):
        # La metrica del hallazgo en cada nivel del contexto, con su n; marca el nivel del hallazgo y la referencia.
        orden = list(ORDEN_TARJETA.get(ctx, self.d.p04["NIVELES"].get(ctx, [])))
        presentes = [k[2] for k in celda if k[0] == r.metrica and k[1] == ctx]
        orden += [x for x in presentes if x not in orden]
        items = []
        for nivel in orden:
            cel = celda.get((r.metrica, ctx, nivel))
            if cel is None:
                continue
            clase = " es-hallazgo" if nivel == r.nivel else ""
            ref = ' <span class="nivel-ref">referencia</span>' if nivel == r.referencia else ""
            n = cel.n_obs
            obs = OBS_ET.get(m["nivel_dato"], m["nivel_dato"]) if n != 1 else OBS_UNO.get(m["nivel_dato"], "")
            inest = " · inestable" if es_verdad(cel.inestable) else ""
            items.append(f'<div class="nivel{clase}"><dt>{esc(capital(nivel_corto(ctx, nivel)))}{ref}</dt>'
                         f'<dd class="nivel-valor">{fmt_valor(cel.valor, m["unidad"])}</dd>'
                         f'<dd class="nivel-n">{entero(n)} {esc(obs)}{inest}</dd></div>')
        etiqueta = self.enlace_def(METRICA_DEF.get(r.metrica, ""), esc(m["etiqueta_metrica"]))
        return f'<p class="niveles-et">{etiqueta}</p><dl class="niveles">{"".join(items)}</dl>'

    def tambien(self, ctx, t, m, celda):
        # Otro hallazgo del mismo contexto en una linea: «De local también suma más puntos: 2.27 contra 1.61 de …».
        sube = pd.notna(t.diferencia) and t.diferencia > 0
        v1 = celda.get((t.metrica, ctx, t.nivel))
        v0 = celda.get((t.metrica, ctx, t.referencia))
        v1 = fmt_valor(v1.valor if v1 is not None else float("nan"), m["unidad"])
        v0 = fmt_valor(v0.valor if v0 is not None else float("nan"), m["unidad"])
        donde = esc(capital(nivel_frase(ctx, t.nivel)))
        if t.metrica in FRASE_METRICA:
            que = f"{donde} también {esc(FRASE_METRICA[t.metrica][0 if sube else 1])}"
        else:
            que = f"{donde} también {'sube' if sube else 'baja'} {esc(m['etiqueta_metrica'].lower())}"
        obs = OBS_ET.get(m["nivel_dato"], m["nivel_dato"])
        return (f"{que}: {v1}, frente a {v0} {esc(nivel_frase(ctx, t.referencia))} "
                f"({esc(m['etiqueta_metrica'].lower())}). {marca_lectura(t.lectura, t.inestable)} "
                f'<span class="club-n">n = {entero(t.n_obs_nivel)} y {entero(t.n_obs_ref)} {esc(obs)}</span>')

    def f51(self, filas):
        # Tamaño de efecto con su IC por comparacion, agrupado por contexto; cada fila es HTML con su SVG.
        cod, ancla = self.codigo("F", 5)
        if not filas:
            return (f'<figure class="fig" id="{ancla}"><figcaption><span class="codigo">{cod}</span> Tamaño de efecto '
                    f'por comparación</figcaption><p class="pie">Ninguna comparación tiene lectura diferencia o '
                    f'indicio.</p></figure>')
        bajos = [v for _, r, _ in filas for v in (r.efecto, r.efecto_ic_inf) if pd.notna(v)]
        altos = [v for _, r, _ in filas for v in (r.efecto, r.efecto_ic_sup) if pd.notna(v)]
        umbral = self.d.p04["EFECTO_MIN"]
        lo, hi = min(bajos + [-umbral]), max(altos + [umbral])
        span = hi - lo
        paso = 0.25 if span <= 1.6 else 0.5 if span <= 3.2 else 1.0
        lo, hi = paso * (lo // paso), paso * -((-hi) // paso)

        def x(v):
            return 1000 * (v - lo) / (hi - lo)

        ticks = [lo + i * paso for i in range(int(round((hi - lo) / paso)) + 1)]
        banda = (f'<rect x="{x(-umbral):.1f}" y="0" width="{x(umbral) - x(-umbral):.1f}" height="24" class="f-banda"/>'
                 + "".join(f'<line x1="{x(u):.1f}" x2="{x(u):.1f}" y1="0" y2="24" class="f-umbral" '
                           f'vector-effect="non-scaling-stroke"/>' for u in (-umbral, umbral)))
        rejilla = "".join(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="0" y2="24" class="f-rejilla" '
                          f'vector-effect="non-scaling-stroke"/>' for t in ticks if abs(t) > 1e-9)
        cero = f'<line x1="{x(0):.1f}" x2="{x(0):.1f}" y1="0" y2="24" class="f-cero" vector-effect="non-scaling-stroke"/>'
        grupos, actual = [], None
        for ctx, r, m in filas:
            if ctx != actual:
                grupos.append((ctx, r.referencia, []))
                actual = ctx
            indicio = r.lectura == "indicio"
            ic = ""
            if pd.notna(r.efecto_ic_inf) and pd.notna(r.efecto_ic_sup):
                ic = (f'<line x1="{x(r.efecto_ic_inf):.1f}" x2="{x(r.efecto_ic_sup):.1f}" y1="12" y2="12" '
                      f'class="f-ic" vector-effect="non-scaling-stroke"/>')
            px = f"{x(r.efecto):.1f}" if pd.notna(r.efecto) else None
            punto = ""
            if px:
                punto = f'<line x1="{px}" x2="{px}" y1="12" y2="12" class="f-punto" vector-effect="non-scaling-stroke"/>'
                if indicio:
                    punto += (f'<line x1="{px}" x2="{px}" y1="12" y2="12" class="f-hueco" '
                              f'vector-effect="non-scaling-stroke"/>')
            unidad = m["unidad"]
            corta = ETIQUETA_CORTA.get(r.metrica, m["etiqueta_metrica"])
            et = f"{corta} · {nivel_corto(r.contexto, r.nivel)}"
            completo = (f"{m['etiqueta_metrica']}, {nivel_corto(r.contexto, r.nivel)} contra "
                        f"{nivel_corto(r.contexto, r.referencia)}")
            dif = (f"{fmt_dif(r.diferencia, unidad)} (IC {self.ic}%: {fmt_dif(r.dif_ic_inf, unidad, False)} a "
                   f"{fmt_dif(r.dif_ic_sup, unidad, False)})")
            datos = (f"diferencia {dif}; {r.tipo_efecto} {fmt_efecto(r.efecto)} (IC {self.ic}%: "
                     f"{fmt_efecto(r.efecto_ic_inf)} a {fmt_efecto(r.efecto_ic_sup)}); lectura: "
                     f"{LECTURA_ET.get(r.lectura, r.lectura)}")
            n_txt = f"{entero(r.n_obs_nivel)}/{entero(r.n_obs_ref)} {OBS_CORTO.get(m['nivel_dato'], '')}"
            marca = ' <span class="f-indicio">indicio, inestable</span>' if indicio else ""
            grupos[-1][2].append(
                f'<li class="f-fila" title="{esc(completo)}. {esc(datos)}"><span class="f-et">{esc(et)}{marca}'
                f'<span class="sr">. {esc(completo)}. {esc(datos)}</span><span class="f-dif" aria-hidden="true">'
                f'{esc(dif)}</span></span><svg class="f-plot" viewBox="0 0 1000 24" preserveAspectRatio="none" '
                f'aria-hidden="true" focusable="false">{banda}{rejilla}{cero}{ic}{punto}</svg>'
                f'<span class="f-n">{n_txt}</span></li>')
        eje = "".join(f'<span style="left:{x(t) / 10:.2f}%">{fmt_efecto(t) if abs(t) > 1e-9 else "0"}</span>'
                      for t in ticks)
        cuerpo = "".join(f'<h3 class="f-grupo">{esc(CONTEXTOS.get(ctx, (ctx,))[0])} <span>contra '
                         f'{esc(nivel_corto(ctx, ref))}</span></h3><ul class="f-lista">{"".join(f)}</ul>'
                         for ctx, ref, f in grupos)
        leyenda = ('<p class="f-leyenda"><span class="f-clave"><svg viewBox="0 0 24 24" aria-hidden="true">'
                   '<circle cx="12" cy="12" r="6" class="f-clave-lleno"/></svg>diferencia</span>'
                   '<span class="f-clave"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="5" '
                   'class="f-clave-hueco"/></svg>indicio (celda inestable)</span>'
                   f'<span class="f-clave"><span class="f-clave-banda"></span>|efecto| menor que {umbral}</span></p>')
        pie = (f"Punto: tamaño de efecto; línea: su IC del {self.ic}%. A la derecha, la n del nivel y la de la "
               f"referencia, en posesiones (pos.), eventos (ev.) o partidos (part.).")
        base = self.base_html(self.base_contexto({r.metrica for _, r, _ in filas}), cod, ancla, 5)
        return (f'<figure class="fig f51" id="{ancla}"><figcaption><span class="codigo">{cod}</span> Qué cambia y '
                f'cuánto</figcaption><p class="pie">{pie}</p>{base}{leyenda}<div class="f-cuerpo">'
                f'{cuerpo}<div class="f-eje" aria-hidden="true"><span class="f-eje-et">Tamaño de efecto</span>'
                f'<div class="f-eje-ticks">{eje}</div></div></div></figure>')

    def base_contexto(self, metricas):
        # Los seis contextos, el bootstrap y los objetos de las metricas comparadas.
        ids = [f"def-{slug(n)}" for n, _ in CONTEXTOS.values()] + ["sup-desde-america", "sup-rival", "sup-bootstrap"]
        return ids + [METRICA_OBJETO[m] for m in sorted(metricas) if m in METRICA_OBJETO]

    def t51(self, meta):
        comps = self.d.comps
        filas = []
        for r in comps.itertuples():
            m = meta.loc[r.metrica] if r.metrica in meta.index else None
            unidad = m["unidad"] if m is not None else ""
            et_m = esc(m["etiqueta_metrica"]) if m is not None else esc(r.metrica)
            ctx_et = CONTEXTOS.get(r.contexto, (r.contexto,))[0]
            lectura = LECTURA_ET.get(r.lectura, r.lectura) + (" (inestable)" if es_verdad(r.inestable) else "")
            # lo que se lee primero (metrica, contexto, nivel, lectura y diferencia) va a la izquierda
            filas.append((r.contexto, r.lectura, ctx_et, LECTURA_ET.get(r.lectura, r.lectura), [
                et_m, esc(ctx_et), esc(nivel_corto(r.contexto, r.nivel)), esc(lectura), fmt_dif(r.diferencia, unidad),
                f"{fmt_dif(r.dif_ic_inf, unidad, False)} a {fmt_dif(r.dif_ic_sup, unidad, False)}",
                esc(nivel_corto(r.contexto, r.referencia)), esc(AJUSTE_ET.get(r.ajuste, r.ajuste)),
                f"{fmt_efecto(r.efecto)} <small>{esc(r.tipo_efecto)}</small>",
                f"{fmt_efecto(r.efecto_ic_inf)} a {fmt_efecto(r.efecto_ic_sup)}",
                entero(r.n_obs_nivel), entero(r.n_obs_ref),
                f"{entero(r.n_partidos_nivel)} / {entero(r.n_partidos_ref)}"]))
        cod, ancla = self.codigo("T", 5)
        enc = ["Métrica", "Contexto", "Nivel", "Lectura", "Diferencia", f"IC {self.ic}%", "Referencia", "Ajuste",
               "Efecto", f"IC {self.ic}% del efecto", "n nivel", "n ref.", "Partidos"]
        num = {4, 5, 8, 9, 10, 11, 12}
        th = "".join(f'<th scope="col"{NUM if i in num else ""}>{h}</th>' for i, h in enumerate(enc))
        cuerpo = "".join(
            f'<tr data-contexto="{esc(ctx)}" data-contexto-et="{esc(cet)}" data-lectura="{esc(lec)}" '
            f'data-lectura-et="{esc(let)}">' + "".join(f'<td{NUM if i in num else ""}>{v}</td>'
                                                     for i, v in enumerate(celdas)) + "</tr>"
            for ctx, lec, cet, let, celdas in filas)
        return (f'<details class="pliegue" id="{ancla}"><summary><span class="codigo">{cod}</span> Las '
                f'{entero(len(comps))} comparaciones</summary><p class="nota">Una fila por métrica, contexto, '
                f'nivel y ajuste. Diferencia en la unidad de la métrica (pp: puntos porcentuales). n. d.: sin IC, '
                f'porque alguna de las dos celdas tiene menos de {self.d.p04["MIN_PARTIDOS_IC"]} partidos. Partidos: '
                f'los del nivel y los de la referencia.</p>'
                f'{self.base_html(self.base_contexto(set(comps["metrica"].astype("string"))), cod, ancla, 5)}'
                f'<div class="filtros" id="t5-1-filtros" hidden></div><div class="tabla-caja" role="region" '
                f'tabindex="0" aria-label="{cod} comparaciones por contexto"><table id="{ID_T51}" class="densa" '
                f'data-orden-lectura="{esc("|".join(LECTURA_ET))}">'
                f'<thead><tr>{th}</tr></thead><tbody>{cuerpo}</tbody></table></div></details>')

    def s_jugadores(self):
        c = self.c
        cuerpo = self.cifra(esc(c["formacion"]),
                            f"es la formación inicial más usada: {c['formacion_n']} de {c['n']} partidos "
                            f"({porciento(razon(c['formacion_n'], c['n']))}).")
        cuerpo += self.pendiente("pato_jugadores")
        cuerpo += self.figuras_de(6)
        return self.puerta("jugadores", cuerpo)

    def s_decisiones(self):
        return self.puerta("decisiones", self.pendiente("lee_decisiones"))

    def s_limitaciones(self):
        c, d = self.c, self.d
        sin_frame = 1 - c["pct_frame"]
        # primero la respuesta al reto; despues la cifra y la lista de limites
        cuerpo = self.pendiente("pato_cierre")
        cuerpo += self.cifra(porciento(sin_frame),
                             f"de los eventos no traen frame 360: {entero(c['eventos_cob'] - c['con_frame'])} de "
                             f"{entero(c['eventos_cob'])}.")
        presion = next((f[2] for f in d.framework.donde[1]
                        if len(f) > 2 and f[0].strip().lower() == "fase de presión"), None)
        presion_txt = (inline_md(presion) if presion else
                       "La definición de la fase de presión está pendiente de confirmar.")
        # lo que el texto de limitaciones no cubre; si ese md falta, van tambien las que si cubre
        extra = [f"Fase de presión: {presion_txt[:1].lower()}{presion_txt[1:]}",
                 "Modelos: el xG y el OBV son estimaciones de modelos de StatsBomb, no observaciones directas."]
        texto = self.pendiente("lee_limitaciones")
        if not texto:
            inest_txt = esc(celdas_inestables(d.celdas))
            extra = [
                f"Cobertura 360 parcial: {porciento(sin_frame)} de los eventos no tiene frame 360; según el partido, "
                f"entre {decimal(c['pct_frame_min'])}% y {decimal(c['pct_frame_max'])}% sí lo tiene. {SIN_FILTRO_360}",
                (f"Celdas con pocos datos: hay celdas inestables {inest_txt}. Sus comparaciones salen como indicio o "
                 f"sin diferencia clara." if inest_txt else "Celdas con pocos datos: ninguna celda queda inestable."),
                f"Métricas solo del América: {len(c['solo_eq'])} métricas de las posesiones existen solo para el "
                f"América, así que no se pueden comparar contra el rival.",
                "Un solo entrenador: no hay contraste con otros entrenadores del América, así que las cifras no "
                "separan lo que es de Jardine de lo que es del club.",
            ] + extra
        lis = "".join(f"<li>{x}</li>" for x in extra)
        if texto.endswith("</ul></div>"):
            cuerpo += texto[:-len("</ul></div>")] + lis + "</ul></div>"  # una sola lista con la del md
        else:
            cuerpo += texto + f'<ul class="limites">{lis}</ul>'
        return self.puerta("limitaciones", cuerpo)

    def s_glosario(self):
        # La tabla de terminos del reporte (T9.1), abierta, y las fuentes de las imagenes tomadas de internet.
        cod, ancla = self.codigo("T", 9)
        terminos_txt = [[t, d.format(efecto_min=self.d.p04["EFECTO_MIN"])] for t, d in TERMINOS]
        t = tabla_md(["Término", "Qué quiere decir"], terminos_txt, ids=[f"term-{slug(x)}" for x, _ in TERMINOS],
                     etiqueta=f"{cod} Términos")
        terminos = (f'<h3 id="terminos">Términos del reporte</h3>'
                    f'<figure class="tabla" id="{ancla}"><figcaption><span class="codigo">{cod}</span> Términos'
                    f'</figcaption>{t}{self.base_html(("sup-penales", "sup-rival"), cod, ancla, 9)}</figure>'
                    f'<p class="nota">Los objetos y supuestos del reporte están en el <a href="#marco">marco de '
                    f'análisis</a>.</p>')
        refs = "".join(f'<li>{esc(que)}. Fuente: <a href="{esc(url)}" target="_blank" rel="noopener noreferrer">'
                       f'{esc(texto)}</a></li>' for que, texto, url in REFERENCIAS_IMAGENES)
        referencias = f'<h3 id="referencias">Referencias de las imágenes</h3><ul class="referencias">{refs}</ul>'
        return self.puerta("glosario", terminos + referencias)


def celdas_inestables(celdas):
    # «en tiempo extra, 1 partido; en inferioridad numérica, de 4 a 6 partidos según la métrica»
    inest = celdas[celdas["inestable"].astype("boolean").fillna(False)]
    grupos = inest.groupby(["contexto", "nivel"])["n_partidos"].agg(["min", "max"]).reset_index()
    partes = []
    for r in grupos.itertuples():
        if r.min == r.max:
            rango = f"{entero(r.min)} partido" + ("s" if r.min != 1 else "")
        else:
            rango = f"de {entero(r.min)} a {entero(r.max)} partidos según la métrica"
        partes.append(f"{nivel_frase(r.contexto, r.nivel)}, {rango}")
    return "; ".join(partes)


def capital(texto):
    # Primera letra en mayuscula, sin tocar el resto («de local» -> «De local»).
    texto = str(texto)
    return texto[:1].upper() + texto[1:]


def nivel_corto(contexto, nivel):
    return NIVEL_CORTO.get((contexto, nivel), str(nivel))


def nivel_frase(contexto, nivel):
    if (contexto, nivel) in NIVEL_FRASE:
        return NIVEL_FRASE[(contexto, nivel)]
    if contexto == "minute_bin" and re.fullmatch(r"\d+-\d+", str(nivel)):
        a, b = str(nivel).split("-")
        return f"del minuto {a} al {b}"
    return str(nivel)


def es_verdad(v):
    # True solo si v es verdadero y no nulo (las banderas boolean de pandas pueden venir como NA).
    return bool(v) if pd.notna(v) else False


def marca_lectura(lectura, inestable=False):
    et = LECTURA_ET.get(lectura, lectura)
    extra = " · celda inestable" if es_verdad(inestable) and lectura == "indicio" else ""
    return f'<span class="lectura lectura-{slug(lectura)}">{esc(et)}{extra}</span>'


def armar(datos, cifras, figuras_dir, textos_dir, recursos_dir):
    r = Reporte(cifras, datos, figuras_dir, textos_dir, recursos_dir)
    secciones = [r.inicio(), r.s_pregunta(), r.s_marco(), r.s_ofensiva(), r.s_defensa(), r.s_contexto(),
                 r.s_jugadores(), r.s_decisiones(), r.s_limitaciones(), r.s_glosario()]
    secciones = [x.replace("<!--MATRIZ-->", r.matriz(), 1) for x in secciones]
    logos = "".join(r.recurso(k, f"logo logo-{k}") for k in LOGOS_BARRA)
    logos = f'<p class="logos">{logos}</p>' if logos else ""
    marca = r.recurso("america", "logo logo-america", decorativa=True) or "Inicio"
    puertas = "".join(f'<li><a href="#{a}" data-num="{n}" data-et="{esc(et)}"><b>{n}</b><span>{esc(et)}</span></a></li>'
                      for a, n, et, _, _ in PUERTAS)
    doc = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jardine en el América · Reporte de análisis</title>
<meta name="description" content="Análisis táctico de André Jardine con el América, {esc(cifras['torneos'][0])} a {esc(cifras['torneos'][-1])}: {cifras['n']} partidos con datos de eventos y 360 de Hudl StatsBomb.">
<meta name="color-scheme" content="light">
<meta name="theme-color" content="#0A1F44">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@600;800;900&amp;display=swap">
<style>{CSS}</style>
</head>
<body>
<a class="saltar" href="#pregunta">Saltar al reporte</a>
<nav class="barra" aria-label="Puertas del reporte">
<div class="barra-dentro">
<a class="marca" href="#inicio" aria-label="Ir a la portada">{marca}</a>
<p class="barra-actual" aria-hidden="true"><b></b><span>Inicio</span></p>
<button class="barra-boton" type="button" aria-expanded="false" aria-controls="lista-puertas">Puertas</button>
<div class="puertas-caja"><ul class="lista-puertas" id="lista-puertas">{puertas}</ul><span class="muesca" aria-hidden="true"></span>{logos}</div>
</div>
</nav>
<main id="contenido">
{"".join(secciones)}
</main>
<script>{JS}</script>
</body>
</html>
"""
    return doc, r


# ---------------------------------------------------------------- verificacion

def credenciales():
    # Valores de SB_USER y SB_PASS de .env y del entorno; nunca se imprimen.
    valores, ruta = {}, ROOT / ".env"
    if ruta.is_file():
        try:
            for linea in leer_md(ruta).splitlines():
                m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", linea)
                if not m or m.group(1) not in CREDENCIALES:
                    continue
                v = m.group(2)
                if v[:1] in "'\"" and v[-1:] == v[:1] and len(v) > 1:
                    v = v[1:-1]
                else:
                    v = re.split(r"\s+#", v, maxsplit=1)[0].strip()  # comentario al final de la linea
                if v:
                    valores.setdefault(m.group(1), set()).add(v)
        except (OSError, UnicodeDecodeError) as e:
            _aviso(f".env existe pero no se pudo leer ({type(e).__name__}); no se revisaron sus valores")
    for k in CREDENCIALES:
        if os.environ.get(k):
            valores.setdefault(k, set()).add(os.environ[k])
    if not valores:
        _aviso("no hay valores de SB_USER ni SB_PASS en .env ni en el entorno; solo se buscan los nombres")
    return valores


def verificar(doc, reporte, estricto, n_comps):
    # Devuelve (fallas, info) del HTML armado.
    fallas, info = [], {}
    peso = len(doc.encode("utf-8"))
    info["peso"] = peso
    if peso > LIMITE_MB * 1024 ** 2:
        fallas.append(f"el HTML pesa {peso / 1024 ** 2:.1f} MB y el limite es {LIMITE_MB} MB")
    elif peso > META_MB * 1024 ** 2:
        _aviso(f"el HTML pesa {peso / 1024 ** 2:.1f} MB, mas que la meta de {META_MB} MB")
    # texto sin las imagenes incrustadas, para no confundir base64 con texto
    texto = re.sub(r"data:image/[a-z+]+;base64,[A-Za-z0-9+/=]+", "data:image", doc)

    malas = [k for k, vs in credenciales().items() if any(v in texto or esc(v) in texto for v in vs)]
    malas += [k for k in CREDENCIALES if k in texto]
    if re.search("password", texto, re.IGNORECASE):
        malas.append("la palabra password")
    if malas:
        fallas.append(f"credenciales: aparece {', '.join(sorted(set(malas)))} (valores no impresos)")
    info["credenciales"] = not malas

    # un nombre crudo solo se acepta si el framework de Pato lo cita, y no mas veces que ahi
    permitidos = {n: reporte.d.framework.crudo.count(n) for n in CRUDOS}
    crudos = {n: (texto.count(n), permitidos[n]) for n in CRUDOS if texto.count(n) > permitidos[n]}
    if crudos:
        fallas.append("datos crudos: nombres de columnas crudas mas veces que en el framework (en el HTML, en el "
                      f"framework): {crudos}")
    filas_max, filas_t51 = 0, None
    for tabla in re.findall(r"<table\b.*?</table>", texto, re.S):
        cuerpo = re.search(r"<tbody>(.*?)</tbody>", tabla, re.S)
        n = len(re.findall(r"<tr\b", cuerpo.group(1) if cuerpo else tabla))
        if f'id="{ID_T51}"' in tabla[:200]:
            filas_t51 = n
        else:
            filas_max = max(filas_max, n)
    if filas_max > MAX_FILAS_TABLA:
        fallas.append(f"datos crudos: una tabla tiene {filas_max} filas (maximo {MAX_FILAS_TABLA})")
    if filas_t51 != n_comps:
        fallas.append(f"T5.1 tiene {filas_t51} filas y comparaciones_contexto {n_comps}")
    info["crudos"], info["filas_max"], info["filas_t51"] = not crudos, filas_max, filas_t51

    externos = []
    externos += [f"<script src> {m}" for m in re.findall(r"<script\b[^>]*\bsrc\s*=\s*[\"']?([^\"' >]+)", texto)]
    externos += [f"<img> {m}" for m in re.findall(r"<img\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)", texto)
                 if not m.startswith("data:")]
    externos += [f"srcset {m}" for m in re.findall(r"\bsrcset\s*=\s*[\"']([^\"']+)", texto)]
    for m in re.findall(r"<link\b[^>]*\bhref\s*=\s*[\"']([^\"']+)", texto):
        host = re.match(r"^(?:https?:)?//([^/]+)", m)
        if not host or host.group(1).lower() not in HOSTS_PERMITIDOS:
            externos.append(f"<link> {m}")
    for m in re.findall(r"(?:@import\s+(?:url\()?|url\()\s*[\"']?((?:https?:)?//[^\"')\s]+)", texto):
        host = re.match(r"^(?:https?:)?//([^/]+)", m)
        if not host or host.group(1).lower() not in HOSTS_PERMITIDOS:
            externos.append(f"css {m}")
    externos += [f"<{t}>" for t in ("iframe", "object", "embed") if re.search(rf"<{t}\b", texto)]
    if externos:
        fallas.append(f"recursos externos fuera de Google Fonts: {externos[:5]}")
    info["externos"] = not externos

    nombres = nombres_fuera_de_autores(texto)
    if nombres:
        fallas.append(f"atribucion: {len(nombres)} nombres del equipo fuera de la linea de autores: "
                      + "; ".join(f"«{plano(x)}»" for x in nombres[:5]))
    info["nombres"] = not nombres
    visible = re.sub(r"<(style|script)\b.*?</\1>", "", texto, flags=re.S)
    marcas = [f"{que}: «{plano(m.group(0))}»" for patron, que in PROHIBIDO_VISIBLE for m in [patron.search(visible)] if m]
    if marcas:
        fallas.append(f"marcas de trabajo interno en el HTML: {'; '.join(marcas)}")
    info["marcas"] = not marcas
    ids = set(re.findall(r'\bid="([^"]+)"', texto))
    rotos = sorted({h for h in re.findall(r'href="#([^"]+)"', texto) if h not in ids})
    if rotos:
        fallas.append(f"enlaces internos sin destino: {rotos[:8]}")
    info["anclas"] = not rotos
    sin_base = [cod for cod, _, _, base in reporte.trazas if not base]
    base_rota = sorted({i for _, _, _, base in reporte.trazas for i in base if i not in ids})
    con_traza = {cod for cod, _, _, _ in reporte.trazas}
    sin_traza = sorted(set(re.findall(r'<span class="codigo">([FT]\d+\.\d+)</span>', texto)) - con_traza)
    if sin_base or base_rota or sin_traza:
        fallas.append(f"traza al marco: sin objetos {sin_base + sin_traza}; ids que no existen {base_rota}")
    info["traza"] = not (sin_base or base_rota or sin_traza)
    repetidas = []
    for linea in re.findall(r'<p class="base">(.*?)</p>', texto, re.S):
        ets = re.findall(r">([^<]+)</a>", linea)
        repetidas += sorted({e for e in ets if ets.count(e) > 1})
    if repetidas:
        fallas.append(f"«Se basa en» con etiquetas repetidas: {sorted(set(repetidas))}")
    info["etiquetas"] = not repetidas
    if estricto and reporte.pendientes:
        fallas.append(f"--estricto: faltan {len(reporte.pendientes)} textos, figuras o recursos (lista arriba)")
    return fallas, info


def nombres_fuera_de_autores(texto):
    # Fragmentos donde aparece un nombre del equipo, sin contar la linea de autores ni el CSS y el JS. «Lee» al
    # inicio de oracion y seguido de minuscula es el verbo («Lee la tabla…»), no el nombre.
    s = re.sub(r'<span class="autores">.*?</span>', "", texto, count=1, flags=re.S)
    s = re.sub(r"<(style|script)\b.*?</\1>", "", s, flags=re.S)
    encontrados = []
    for m in re.finditer(rf"\b({'|'.join(NOMBRES_EQUIPO)})\b", s):
        if m.group(1) == "Lee":
            antes = re.sub(r"<[^>]*>", "", s[max(0, m.start() - 200):m.start()]).rstrip()
            inicio = not antes or antes[-1] in ".!?:¿¡«>\"" or s[:m.start()].rstrip().endswith(">")
            if inicio and re.match(r"Lee\s+[a-záéíóúñ]", s[m.start():m.start() + 12]):
                continue
        crudo = s[max(0, m.start() - 40):m.end() + 40]
        frag = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", crudo)).strip()
        encontrados.append(frag if m.group(1) in frag else re.sub(r"\s+", " ", crudo))  # en un atributo, como viene
    return encontrados


def resumen(cifras, reporte, info):
    c = cifras
    print(f"Cifras: {c['n']} partidos ({c['regular']} regular, {c['liguilla']} liguilla, {c['finales']} finales); "
          f"G-E-P {c['G']}-{c['E']}-{c['P']}; goles {c['gf']}-{c['gc']}; xG sin penales {c['xg_favor']:.1f}-"
          f"{c['xg_contra']:.1f}; xG a favor por origen " + " + ".join(
              f"{v['xg']:.1f}" for v in c["origen_favor"].values()))
    for lado in ("favor", "contra"):
        pen = c[f"penales_{lado}"]
        print(f"        penales {lado}: {pen['tiros']} tiros, {pen['goles']} goles, {pen['xg']:.1f} xG; autogoles "
              f"{lado}: {c[f'autogoles_{lado}']}")
    print(f"        {c['posesiones_sin_admin']:,} posesiones sin administrativas; {c['validas_eq']:,} validas del "
          f"America; presion alta 40 m {100 * c['presion_alta']:.1f}%; {c['eventos']:,} eventos, "
          f"{100 * c['pct_frame']:.1f}% con frame 360; diferencia {c['lecturas']['diferencia']} de "
          f"{c['comps_simple']} simples; formacion {c['formacion']} ({c['formacion_n']} de {c['n']})")
    print(f"Figuras: {len(reporte.incrustadas)} incrustadas (WebP, max {ANCHO_MAX} px, calidad {CALIDAD_WEBP}), "
          f"{len(reporte.faltantes)} faltantes")
    for grupo, peso in reporte.peso_grupo.items():
        print(f"   {plano(grupo)}: {peso / 1024 ** 2:.2f} MB")
    print(f"   total figuras: {sum(reporte.peso_grupo.values()) / 1024 ** 2:.2f} MB")
    print(f"Peso del HTML: {info['peso'] / 1024 ** 2:.2f} MB (meta < {META_MB} MB, limite {LIMITE_MB} MB)")
    print(f"Verificacion: credenciales {'OK' if info['credenciales'] else 'FALLA'}; datos crudos "
          f"{'OK' if info['crudos'] else 'FALLA'} (tabla mas larga: {info['filas_max']} filas; T5.1: "
          f"{info['filas_t51']}); recursos externos {'OK, solo Google Fonts' if info['externos'] else 'FALLA'}; "
          f"nombres fuera de los autores {'OK' if info['nombres'] else 'FALLA'}; marcas internas "
          f"{'OK' if info['marcas'] else 'FALLA'}; anclas {'OK' if info['anclas'] else 'FALLA'}; traza al marco "
          f"{'OK' if info['traza'] else 'FALLA'}; etiquetas sin repetir {'OK' if info['etiquetas'] else 'FALLA'}")
    usados = ", ".join(reporte.textos_usados) or "ninguno"
    print(f"Textos del equipo: {len(reporte.textos_usados)} de {len(PENDIENTES)} ({usados})")
    puestos = len(reporte.recursos) - len(reporte.recursos_faltantes)
    print(f"Logos y foto: {puestos} de {len(RECURSOS)} incrustados")
    print(f"Faltan y se omitieron ({len(reporte.pendientes)}):")
    por_quien = {}
    for quien, falta in reporte.pendientes:
        por_quien.setdefault(quien, []).append(falta)
    for quien, faltas in por_quien.items():
        figs = [f for f in faltas if f.startswith("figura ")]
        for f in faltas:
            if not f.startswith("figura "):
                print(f"   {quien}: {plano(f)}")
        if figs:
            print(f"   {quien}: {len(figs)} figuras faltantes")


def avisar_faltantes(reporte):
    # Un AVISO por figura con todos los torneos que le faltan.
    por_fig = {}
    for cod, torneo, archivo in reporte.faltantes:
        por_fig.setdefault((cod, re.sub(r"_(Apertura|Clausura)_\d{4}", "_<torneo>", archivo)), []).append(torneo)
    for (cod, archivo), torneos in por_fig.items():
        _aviso(f"figura faltante {cod} {archivo}: falta en {', '.join(torneos)}; se omite")


# ---------------------------------------------------------------- escritura

def escribir(doc, salida):
    # Archivo temporal en la misma carpeta y reemplazo atomico.
    try:
        salida.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=PREFIJO_TMP, suffix=".html", dir=salida.parent)
    except OSError as e:
        raise ErrorReporte(f"no se pudo preparar {salida.parent}: {e}") from e
    tmp = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(doc)
        os.replace(tmp, salida)
    except OSError as e:
        raise ErrorReporte(f"no se pudo escribir {salida} (si esta abierto en otro programa, cierralo): {e}") from e
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------- CSS y JS en linea

CSS = r"""
:root{--marino:#0A1F44;--marino-2:#112A57;--marino-3:#061633;--borde-marino:#23396A;--amarillo:#FFD23F;
--suelo:#F4F6F9;--blanco:#FFFFFF;--tinta:#0F1A2E;--tinta-2:#4A5568;--linea:#D5DBE5;--panel:#EEF1F6;
--claro-1:#C9D3E6;--claro-2:#DCE3F0;--barra:56px;--radio:4px;
--esp-1:4px;--esp-2:8px;--esp-3:16px;--esp-4:24px;--esp-5:32px;--esp-6:48px;
--display:"Big Shoulders Display","Bahnschrift Condensed","Avenir Next Condensed","Helvetica Neue Condensed Bold","Arial Narrow","Roboto Condensed",sans-serif-condensed,sans-serif;
--texto:system-ui,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
*,*::before,*::after{box-sizing:border-box}
html{scroll-padding-top:calc(var(--barra) + 20px);-webkit-text-size-adjust:100%}
body{margin:0;padding-top:var(--barra);background:var(--suelo);color:var(--tinta);font:400 17px/1.6 var(--texto)}
::selection{background:var(--marino);color:var(--blanco)}
a{color:var(--marino);text-decoration-thickness:1px;text-underline-offset:3px}
a:hover{text-decoration-thickness:2px}
:focus-visible{outline:3px solid var(--marino);outline-offset:2px;border-radius:2px}
h1,h2,h3,h4{font-family:var(--display);font-stretch:condensed;line-height:1.05;text-wrap:balance}
code{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace;font-size:.88em;background:var(--panel);padding:1px 4px;border-radius:3px;overflow-wrap:anywhere}
.sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
.saltar{position:absolute;left:12px;top:-60px;z-index:30;background:var(--amarillo);color:var(--marino);padding:12px 16px;border-radius:var(--radio);font-weight:700}
.saltar:focus{top:8px}
/* barra de puertas */
.barra{position:fixed;inset:0 0 auto 0;height:var(--barra);background:var(--marino);color:var(--blanco);z-index:20}
.barra-dentro{max-width:1440px;height:100%;margin:0 auto;padding:0 24px;display:flex;align-items:stretch}
.barra :focus-visible{outline-color:var(--amarillo);outline-offset:-3px}
.marca{display:flex;align-items:center;min-width:44px;padding:0 12px 0 0;margin-right:12px;font-family:var(--display);font-stretch:condensed;font-weight:800;font-size:18px;letter-spacing:.06em;color:var(--blanco);text-decoration:none;white-space:nowrap}
.marca .logo-america{height:36px}
.puertas-caja{position:relative;display:flex;flex:1;min-width:0}
/* logos de la UNAM e ISAC: a la derecha de la barra; en el celular, al pie del menu abierto */
.logos{display:flex;align-items:center;gap:16px;margin:0 0 0 auto;padding:0 0 0 16px}
.logo{display:block;width:auto;height:30px}
.logo-isac{height:22px}
.lista-puertas{display:flex;list-style:none;margin:0;padding:0;gap:2px}
.lista-puertas a{display:flex;align-items:center;gap:8px;height:var(--barra);min-width:44px;padding:0 12px;color:var(--claro-1);font-size:14px;text-decoration:none;white-space:nowrap}
.lista-puertas a:hover,.lista-puertas a[aria-current]{color:var(--blanco)}
.lista-puertas b{font-family:var(--display);font-stretch:condensed;font-weight:800;font-size:22px;color:var(--amarillo);line-height:1}
.muesca{position:absolute;left:0;bottom:0;height:5px;width:0;background:var(--amarillo);opacity:0;transition:transform 150ms ease-out,width 150ms ease-out,opacity 150ms ease-out;pointer-events:none}
.barra-actual,.barra-boton{display:none}
@media (prefers-reduced-motion:reduce){.muesca{transition:none}}
@media (max-width:1239px){.lista-puertas a{padding:0 12px;justify-content:center}.lista-puertas a span{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}}
@media (max-width:859px){
 html:not(.js) body{padding-top:0}
 html:not(.js) .barra{position:static;height:auto}
 html:not(.js) .barra-dentro{flex-wrap:wrap;padding:0 12px}
 html:not(.js) .lista-puertas{flex-wrap:wrap}
 html:not(.js) .lista-puertas a{height:48px}
 html:not(.js) .lista-puertas a span{position:static;width:auto;height:auto;clip:auto}
 .js .barra-dentro{padding:0 12px;gap:8px}
 .js .marca{font-size:16px;padding:0 8px;margin-right:0}
 .js .barra-actual{display:flex;align-items:center;gap:8px;margin:0;color:var(--blanco);font-size:15px;position:relative;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;align-self:stretch}
 .js .barra-actual b{font-family:var(--display);font-stretch:condensed;font-weight:800;font-size:22px;color:var(--amarillo)}
 .js .barra-actual b:empty{display:none}
 .js .barra-actual:has(b:not(:empty))::after{content:"";position:absolute;left:0;width:min(100%,9rem);bottom:0;height:5px;background:var(--amarillo)}
 .js .barra-boton{display:block;align-self:center;min-height:44px;padding:0 16px;margin-left:auto;background:transparent;color:var(--blanco);border:1px solid var(--claro-1);border-radius:var(--radio);font:600 15px var(--texto);cursor:pointer}
 .js .barra-boton[aria-expanded="true"]{background:var(--marino-2)}
 .js .muesca{display:none}
 .js .puertas-caja{position:absolute;top:var(--barra);left:0;right:0;display:none;background:var(--marino);border-top:1px solid var(--borde-marino);max-height:calc(100dvh - var(--barra));overflow:auto}
 .js .barra.abierta .puertas-caja{display:block}
 .js .logos{margin:0 12px;padding:16px 12px 20px;border-top:1px solid var(--borde-marino);gap:20px}
 html:not(.js) .puertas-caja{flex-wrap:wrap}
 html:not(.js) .logos{padding:8px 0 12px}
 .js .lista-puertas{flex-direction:column;padding:8px 12px 16px}
 .js .lista-puertas a{height:48px;justify-content:flex-start;padding:0 12px;font-size:16px}
 .js .lista-puertas a span{position:static;width:auto;height:auto;clip:auto}
 .js .lista-puertas a[aria-current]{background:var(--marino-2);box-shadow:inset 5px 0 0 var(--amarillo)}
}
/* portada: boleto */
.portada{max-width:1440px;margin:0 auto;padding:28px 40px 0}
.boleto{display:grid;grid-template-columns:minmax(0,1fr) 420px;min-height:560px;border-radius:8px;color:var(--blanco);background:repeating-linear-gradient(90deg,var(--marino) 0 88px,var(--marino-2) 88px 176px)}
.boleto-cuerpo{position:relative;padding:52px 56px 44px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:0 24px;min-width:0}
.boleto-texto{grid-column:1;grid-row:1;display:flex;flex-direction:column;min-width:0;position:relative;z-index:1}
/* foto de reportaje: recortada, de pie sobre el borde inferior del boleto, con un disco amarillo detras */
.boleto-foto{grid-column:2;grid-row:1;align-self:end;position:relative;margin:0 -24px -44px 0;display:flex;flex-direction:column;align-items:center}
.boleto-foto::before{content:"";position:absolute;left:50%;top:12%;width:92%;aspect-ratio:1;transform:translateX(-50%);border-radius:50%;background:var(--amarillo)}
.foto-img{position:relative;display:block;width:auto;height:clamp(420px,38vw,560px)}
.talon-arriba{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
.talon-escudo{flex:none;padding-top:6px}
.escudo-img{display:block;width:clamp(96px,8vw,124px);height:auto}
.boleto h1{font-weight:900;font-size:clamp(64px,9vw,136px);line-height:.86;margin:0;letter-spacing:-.01em;text-transform:uppercase}
.boleto h1 span{display:inline-block;margin-top:.08em;color:var(--amarillo)}
.periodo{font-family:var(--display);font-stretch:condensed;font-weight:600;font-size:clamp(20px,2.2vw,28px);letter-spacing:.02em;margin:18px 0 28px;color:var(--claro-2);line-height:1.3}
.pregunta{margin:auto 0 0;padding:0 0 0 20px;max-width:62ch;font-size:clamp(17px,1.5vw,20px);line-height:1.5;border-left:5px solid var(--amarillo)}
.talon{position:relative;background:var(--marino);padding:44px 40px 28px;display:flex;flex-direction:column;border-left:3px dashed rgba(255,255,255,.35);border-radius:0 8px 8px 0}
.talon::before,.talon::after{content:"";position:absolute;left:-17px;width:30px;height:30px;border-radius:50%;background:var(--suelo)}
.talon::before{top:-15px}.talon::after{bottom:-15px}
.talon-grande{margin:0;font-family:var(--display);font-stretch:condensed;font-weight:900;font-size:clamp(110px,11.7vw,168px);line-height:.8;color:var(--amarillo)}
.talon-grande span{display:block;font-size:26px;letter-spacing:.08em;color:var(--blanco);margin-top:14px;font-weight:700;text-transform:uppercase}
.marcador{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:30px}
.celda{margin:0;background:var(--marino-3);border:1px solid var(--borde-marino);border-radius:var(--radio);padding:10px 12px;text-align:center}
.celda b{display:block;font-family:var(--display);font-stretch:condensed;font-weight:800;font-size:44px;line-height:1}
.celda span{font-size:13px;letter-spacing:.04em;color:var(--claro-1)}
.filas{margin:22px 0 0;font-size:15px;line-height:1.5;color:var(--claro-2)}
.filas div{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-top:1px solid var(--borde-marino)}
.filas dt{margin:0}.filas dd{margin:0;font-variant-numeric:tabular-nums;color:var(--blanco);font-weight:700;white-space:nowrap}
.talon-nota{margin:16px 0 0;padding-left:12px;border-left:3px solid var(--amarillo);font-size:14px;line-height:1.5;color:var(--claro-2)}
.talon-pie{margin:auto 0 0;padding-top:20px;font-size:13px;line-height:1.6;color:var(--claro-1);border-top:1px solid var(--borde-marino)}
.talon-pie .autores{font-size:14px;color:var(--blanco)}
.talon-pie .autores b{font-weight:600;color:var(--amarillo)}
/* referencias de las imagenes (puerta 9): el enlace largo de la foto se parte en el celular */
.referencias{margin:0;padding-left:20px;max-width:72ch}
.referencias li{margin:0 0 var(--esp-2);overflow-wrap:anywhere}
/* en escritorio la portada completa cabe en la primera vista: la tipografia grande y los espacios bajan con la altura */
@media (min-width:1240px){
 .portada{--aire-portada:clamp(16px,3vh,28px);padding-top:var(--aire-portada)}
 /* la tarjeta llena la primera vista con el mismo aire arriba y abajo; tope para monitores muy altos */
 .boleto{min-height:min(calc(100vh - var(--barra) - 2 * var(--aire-portada)),900px)}
 .boleto-cuerpo{padding:clamp(28px,5vh,52px) 56px clamp(24px,4vh,44px)}
 .boleto h1{font-size:clamp(64px,min(9vw,13.5vh),136px)}
 .periodo{font-size:clamp(18px,min(2.2vw,3.6vh),28px);margin:clamp(10px,1.8vh,18px) 0 clamp(14px,2.6vh,28px)}
 .pregunta{font-size:clamp(16px,min(1.5vw,2.6vh),20px)}
 .boleto-foto{margin:0 -24px calc(-1 * clamp(24px,4vh,44px)) 0}
 .foto-img{height:clamp(360px,min(38vw,76vh),560px)}
 .talon{padding:clamp(24px,4.4vh,44px) 36px clamp(16px,2.6vh,28px)}
 .talon-grande{font-size:clamp(84px,min(11.7vw,15vh),168px)}
 .talon-grande span{font-size:clamp(20px,3.2vh,26px);margin-top:clamp(8px,1.4vh,14px)}
 .escudo-img{width:clamp(72px,min(8vw,13vh),124px)}
 .marcador{margin-top:clamp(14px,2.8vh,30px)}
 .celda{padding:clamp(6px,1vh,10px) 12px}
 .celda b{font-size:clamp(32px,5.2vh,44px)}
 .filas{margin-top:clamp(10px,2vh,22px)}
 .filas div{padding:clamp(4px,.8vh,8px) 0}
 .talon-nota{margin-top:clamp(10px,1.6vh,16px);font-size:13px;line-height:1.45}
 .talon-pie{padding-top:clamp(10px,1.8vh,20px);line-height:1.45}
}
@media (max-width:1239px){
 .boleto{grid-template-columns:1fr;min-height:0}
 .boleto-cuerpo{padding:40px 40px 32px}
 .foto-img{height:clamp(300px,44vw,500px)}
 .boleto-foto{margin-bottom:-32px}
 .talon{border-left:0;border-top:3px dashed rgba(255,255,255,.35);border-radius:0 0 8px 8px;padding:36px 24px 24px}
 .talon::before{top:-17px;left:-15px}.talon::after{top:-17px;bottom:auto;left:auto;right:-15px}
 .talon-pie{margin-top:22px}
}
@media (max-width:1023px){
 .portada{padding:20px 16px 0}
 .boleto-cuerpo{padding:32px 24px}
}
/* puertas y letreros */
main{padding-bottom:30vh}
.puerta{max-width:1180px;margin:0 auto;padding:96px 24px 0}
.letrero{display:flex;align-items:center;gap:22px;margin:0 0 24px}
.letrero-num{flex:none;min-width:72px;height:72px;padding:0 12px;display:flex;align-items:center;justify-content:center;background:var(--marino);color:var(--amarillo);border-radius:var(--radio);font-family:var(--display);font-stretch:condensed;font-weight:900;font-size:56px;line-height:1}
.letrero h2{margin:0;font-weight:800;font-size:clamp(32px,4vw,44px);text-transform:uppercase;letter-spacing:.02em}
.letrero p{margin:6px 0 0;color:var(--tinta-2);font-size:16px;max-width:70ch}
.sector{background:var(--blanco);border:1px solid var(--linea);border-radius:var(--radio);padding:36px 40px 40px}
.sector > p,.sector li,.pliegue p,.hallazgo p,.aporte p{max-width:72ch}
.sector h3{font-size:30px;font-weight:800;margin:var(--esp-6) 0 var(--esp-3);text-transform:uppercase;letter-spacing:.02em}
.sector h4{font-size:22px;font-weight:800;margin:28px 0 10px}
.sector > :first-child,.aporte > :first-child{margin-top:0}
td code,th code{overflow-wrap:normal}
/* cifra grande, filas tipo talon y tablas */
.cifra{display:flex;flex-wrap:wrap;align-items:flex-end;gap:12px 32px;margin:0 0 28px;padding:24px 32px;background:var(--marino);color:var(--blanco);border-radius:var(--radio)}
.cifra-valor{margin:0;font-family:var(--display);font-stretch:condensed;font-weight:900;font-size:clamp(68px,9vw,120px);line-height:.82;color:var(--amarillo);white-space:nowrap}
.cifra-valor small{font-size:32px;font-weight:800;color:var(--blanco);letter-spacing:.02em}
.cifra-texto{margin:0;flex:1 1 30ch;max-width:56ch;font-size:17px;color:var(--claro-2)}
.cifra-texto a{color:var(--blanco)}
.cifra :focus-visible{outline-color:var(--amarillo)}
.filas-talon{margin:0 0 36px;max-width:760px;border-bottom:1px solid var(--linea)}
.filas-talon > div{display:flex;justify-content:space-between;align-items:baseline;gap:16px;padding:10px 0;border-top:1px solid var(--linea)}
.filas-talon dt{margin:0;font-size:16px;font-weight:600}
.filas-talon dt small{display:block;font-size:14px;font-weight:400;color:var(--tinta-2);line-height:1.4;margin-top:2px}
.filas-talon dd{margin:0;font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap;text-align:right}
.filas-talon dd small{font-size:13px;font-weight:600;color:var(--tinta-2)}
figure{margin:var(--esp-5) 0}
figcaption{font-family:var(--display);font-stretch:condensed;font-weight:800;font-size:22px;line-height:1.3;margin:0 0 8px}
.codigo{display:inline-block;background:var(--marino);color:var(--amarillo);padding:1px 12px;border-radius:var(--radio);font-family:var(--display);font-stretch:condensed;font-weight:800;letter-spacing:.02em;margin-right:6px}
.pie,.nota{font-size:15px;color:var(--tinta-2);margin:var(--esp-2) 0 var(--esp-3);max-width:80ch}
.tabla-caja{overflow-x:auto;background:linear-gradient(90deg,var(--blanco) 30%,rgba(255,255,255,0)) left center/40px 100% no-repeat local,linear-gradient(270deg,var(--blanco) 30%,rgba(255,255,255,0)) right center/40px 100% no-repeat local,radial-gradient(farthest-side at 0 50%,rgba(10,31,68,.28),rgba(10,31,68,0)) left center/14px 100% no-repeat scroll,radial-gradient(farthest-side at 100% 50%,rgba(10,31,68,.28),rgba(10,31,68,0)) right center/14px 100% no-repeat scroll}
table{border-collapse:collapse;width:100%;font-size:15px;line-height:1.4}
th,td{padding:10px 12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--linea)}
thead th{background:var(--panel);font-weight:700;font-size:14px;white-space:nowrap;border-bottom:2px solid var(--marino)}
tbody th{font-weight:600}
tfoot td{font-weight:700;border-top:2px solid var(--marino);border-bottom:0}
tfoot tr.aparte td{font-weight:400;color:var(--tinta-2);border-top:1px solid var(--linea)}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
table.densa{font-size:14px}
table.densa td{padding:7px 12px;white-space:nowrap}
table.doc th[scope=row]{min-width:12ch}
table.doc thead th{white-space:normal;vertical-align:bottom}
/* textos del equipo */
.aporte{margin:32px 0}
.aporte ul{padding-left:20px}
.aporte h3{font-size:26px}
/* figuras con pestanas, marco y visor */
.marco{max-width:1034px;margin:0 auto;padding:16px;background:var(--blanco);border:1px solid var(--marino);border-radius:var(--radio)}
.fig img{display:block;max-width:100%;height:auto;margin:0 auto}
.ampliar{display:block;width:100%;margin:0;padding:0;border:0;background:none;font:inherit;color:inherit;cursor:zoom-in;text-align:center}
.ampliar-pista{display:block;margin-top:8px;font-size:14px;font-weight:600;color:var(--marino);text-decoration:underline;text-underline-offset:3px}
.visor{width:100vw;max-width:none;height:100dvh;max-height:none;margin:0;padding:0;border:0;background:var(--blanco);color:var(--tinta)}
.visor::backdrop{background:rgba(6,22,51,.7)}
.visor-barra{position:sticky;top:0;display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:56px;padding:6px 12px;background:var(--marino);color:var(--blanco)}
.visor-barra p{margin:0;font-size:15px;font-weight:600}
.visor-cerrar{min-height:44px;padding:0 16px;background:transparent;color:var(--blanco);border:1px solid var(--claro-1);border-radius:var(--radio);font:600 15px var(--texto);cursor:pointer}
.visor :focus-visible{outline-color:var(--amarillo)}
.visor-lienzo{height:calc(100dvh - 56px);overflow:auto;padding:12px}
.visor-lienzo img{display:block;max-width:none;width:auto;height:auto}
.panel{margin:0 0 20px}
.panel-torneo{font-family:var(--display);font-stretch:condensed;font-weight:800;font-size:20px;margin:16px 0 8px}
.con-pestanas .panel-torneo{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.con-pestanas .panel{padding-top:16px}
[role="tablist"]{display:flex;flex-wrap:wrap;gap:4px;border-bottom:2px solid var(--marino)}
[role="tab"]{min-height:44px;padding:0 16px;border:0;border-radius:var(--radio) var(--radio) 0 0;background:var(--panel);color:var(--marino);font:600 15px var(--texto);cursor:pointer}
[role="tab"]:hover{background:var(--claro-2)}
[role="tab"][aria-selected="true"]{background:var(--marino);color:var(--blanco);box-shadow:inset 0 -5px 0 var(--amarillo)}
[role="tab"]:focus-visible{outline:3px solid var(--marino);outline-offset:2px}
/* plegables */
.pliegue{margin:var(--esp-4) 0;border:1px solid var(--linea);border-radius:var(--radio);background:var(--blanco)}
.pliegue > summary:hover{background:var(--panel)}
.pliegue > summary{min-height:48px;display:flex;align-items:center;gap:10px;padding:12px 16px;cursor:pointer;font-weight:700;color:var(--marino);list-style:none}
.pliegue > summary::-webkit-details-marker{display:none}
.pliegue > summary::before{content:"";flex:none;width:10px;height:10px;border-right:2px solid var(--marino);border-bottom:2px solid var(--marino);transform:rotate(-45deg);transition:transform 150ms ease-out}
.pliegue[open] > summary::before{transform:rotate(45deg)}
.pliegue[open] > summary{border-bottom:1px solid var(--linea)}
.pliegue > :not(summary){margin-left:20px;margin-right:20px}
.pliegue > :last-child{margin-bottom:var(--esp-4)}
.pliegue figure{margin:var(--esp-4) 20px}
@media (prefers-reduced-motion:reduce){.pliegue > summary::before{transition:none}}
.pliegue tr:target{background:var(--panel)}
/* lecturas */
.lectura{display:inline-flex;align-items:center;gap:6px;padding:0 12px;border:1px solid var(--marino);border-radius:var(--radio);font-size:14px;font-weight:600;line-height:1.7;white-space:nowrap;color:var(--marino)}
.lectura::before{content:"";width:9px;height:9px;flex:none}
.lectura-diferencia{background:var(--marino);color:var(--blanco)}
.lectura-diferencia::before{background:var(--amarillo)}
.lectura-diferencia-pequena::before{background:var(--marino);width:6px;height:6px}
.lectura-indicio::before{border:2px solid var(--marino);border-radius:50%}
.lectura-sin-diferencia-clara{border-style:dotted}
.lectura-sin-diferencia-clara::before{display:none}
.lecturas{padding-left:0;list-style:none}
.lecturas li{margin:10px 0}
/* marco de analisis: los objetos del framework como tarjetas, con el recorrido de una posesion */
.marco-intro{margin:0 0 var(--esp-3);font-size:18px}
.marco-datos{margin:0;padding:10px 0;border-top:1px solid var(--linea);border-bottom:1px solid var(--linea);font-size:15px;color:var(--tinta-2);font-variant-numeric:tabular-nums}
.sector h4.marco-grupo{margin:var(--esp-5) 0 var(--esp-3);text-transform:uppercase;letter-spacing:.02em}
.base{margin:var(--esp-2) 0 var(--esp-3);font-size:13px;color:var(--tinta-2);max-width:80ch}
.base a{color:var(--tinta-2)}
.supuestos{margin:0;padding-left:20px}
.sector .supuestos li{margin:6px 0;max-width:80ch}
.supuestos li:target,.doc tr:target{background:var(--panel)}
.alcance{display:grid;grid-template-columns:1fr 1fr;gap:16px 32px}
.sector .alcance h4{margin:0 0 6px}
.alcance ul{margin:0;padding-left:20px}
@media (max-width:719px){.base{line-height:2.3}.base a{display:inline-block;min-height:24px;padding:4px 0}}
.sector .alcance li{margin:4px 0}
@media (max-width:719px){.alcance{grid-template-columns:minmax(0,1fr)}}
.objetos{list-style:none;margin:0 0 20px;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.sector .objetos li{max-width:none;margin:0}
.objeto{height:100%;display:flex;flex-direction:column;padding:20px;border:1px solid var(--linea);border-top:5px solid var(--marino);border-radius:var(--radio);background:var(--blanco)}
.sector .objeto h4{margin:0 0 8px;font-size:24px;text-transform:uppercase;letter-spacing:.02em}
.objeto-que{margin:0 0 8px}
.objeto-consid{margin:0 0 14px;font-size:14px;color:var(--tinta-2)}
.objeto-umbral{margin:auto 0 0;padding:12px 14px;background:var(--marino);color:var(--blanco);border-radius:var(--radio);font-weight:600;line-height:1.45}
.objeto-umbral span{display:block;font-family:var(--display);font-stretch:condensed;font-weight:800;font-size:15px;letter-spacing:.08em;text-transform:uppercase;color:var(--amarillo)}
.objeto-nota{margin:10px 0 0;font-size:14px;color:var(--tinta-2)}
.objeto:target{outline:3px solid var(--marino);outline-offset:2px}
.recorrido-et{margin:var(--esp-4) 0 var(--esp-2);font-size:15px;font-weight:600}
.objetos.recorrido{grid-template-columns:repeat(3,minmax(0,1fr));gap:32px}
.recorrido li{position:relative}
.recorrido li + li::before{content:"";position:absolute;left:-25px;top:50%;width:12px;height:12px;border-right:3px solid var(--marino);border-bottom:3px solid var(--marino);transform:translateY(-50%) rotate(-45deg)}
@media (max-width:859px){.objetos.recorrido{grid-template-columns:minmax(0,1fr);gap:28px}.recorrido li + li::before{left:50%;top:-21px;transform:translateX(-50%) rotate(45deg)}}
/* ritmo vertical: texto y bloques (tablas, figuras, plegables, tarjetas) separados por --esp-4 */
:is(.sector,.aporte,.hallazgo) > :is(p,ul,ol,dl):not(.nota,.base,.pie,.niveles-et,.recorrido-et) + :is(.tabla-caja,figure,details,.objetos,.alcance,.aporte,.filas-talon),
:is(.sector,.aporte,.hallazgo) > :is(.tabla-caja,figure,details,.objetos,.alcance,.filas-talon,.niveles) + :is(p,ul,ol):not(.nota,.base,.pie){margin-top:var(--esp-4)}
:is(.sector,.aporte) > .tabla-caja + :is(.nota,.base){margin-top:var(--esp-2)}
.alcance + .nota{margin-top:var(--esp-4)}
.aporte .tabla-caja + *{margin-top:var(--esp-4)}
/* contexto: una tarjeta por contexto con su hallazgo */
.hallazgo{margin:var(--esp-5) 0 0;padding:var(--esp-4) 28px var(--esp-2);border:1px solid var(--linea);border-top:5px solid var(--marino);border-radius:var(--radio)}
.sector .hallazgo h3{font-size:20px;margin:0 0 var(--esp-2);color:var(--tinta-2);letter-spacing:.06em}
.hallazgo-titular{margin:0 0 var(--esp-4);font-family:var(--display);font-stretch:condensed;font-weight:800;font-size:clamp(28px,3.4vw,38px);line-height:1.05;text-transform:uppercase;letter-spacing:.01em;color:var(--marino);text-wrap:balance}
.niveles-et{margin:0 0 var(--esp-2);font-size:15px;font-weight:600}
.niveles{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 var(--esp-3)}
.nivel{flex:1 1 7.5rem;max-width:13rem;margin:0;padding:10px 12px;background:var(--panel);border-radius:var(--radio);display:flex;flex-direction:column}
.nivel dt{font-size:14px;font-weight:600;line-height:1.3;flex:1 0 auto}
.nivel dd{margin:0}
.nivel-ref{display:block;font-size:12px;font-weight:400;color:var(--tinta-2)}
.nivel-valor{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.3}
.nivel-n{font-size:13px;color:var(--tinta-2);font-variant-numeric:tabular-nums}
.nivel.es-hallazgo{background:var(--marino);color:var(--blanco)}
.nivel.es-hallazgo .nivel-valor{color:var(--amarillo)}
.nivel.es-hallazgo .nivel-n{color:var(--claro-1)}
.hallazgo-lectura,.hallazgo-tambien{margin:0 0 10px;font-size:16px}
.hallazgo-conteo{margin:0 0 var(--esp-3);font-size:14px;color:var(--tinta-2)}
.hallazgo .fig{margin:var(--esp-4) -20px var(--esp-3)}
.hallazgo-def{margin:0 0 var(--esp-3);font-size:14px;color:var(--tinta-2)}
.club-n{font-size:14px;color:var(--tinta-2);white-space:nowrap}
/* F5.1 */
.sector .f51 h3.f-grupo{font-size:18px;margin:16px 0 2px;text-transform:none;letter-spacing:0}
.f51 h3.f-grupo span{font-family:var(--texto);font-size:14px;font-weight:400;color:var(--tinta-2)}
.f-leyenda{display:flex;flex-wrap:wrap;gap:8px 20px;margin:8px 0 12px;font-size:14px;color:var(--tinta-2)}
.f-clave{display:inline-flex;align-items:center;gap:6px}
.f-clave svg{width:16px;height:16px}
.f-clave-lleno{fill:var(--marino)}
.f-clave-hueco{fill:var(--blanco);stroke:var(--marino);stroke-width:2.5}
.f-clave-banda{display:inline-block;width:22px;height:12px;background:var(--panel);border-left:1px dashed var(--tinta-2);border-right:1px dashed var(--tinta-2)}
.f-lista{list-style:none;margin:0;padding:0}
.sector .f-lista li{max-width:none}
.f-fila,.f-eje{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1.6fr) 7.5rem;gap:2px 16px;align-items:center;padding:8px 0;box-shadow:inset 0 1px 0 var(--panel)}
.f-et{font-size:14px;line-height:1.35}
.f-dif{display:block;font-size:12px;color:var(--tinta-2);font-variant-numeric:tabular-nums}
.f-indicio{display:inline-block;font-size:12px;font-weight:600;padding:0 12px;border:1px dotted var(--marino);border-radius:var(--radio)}
.f-plot{width:100%;height:24px;display:block}
.f-banda{fill:var(--panel)}
.f-umbral{stroke:var(--tinta-2);stroke-width:1;stroke-dasharray:3 3}
.f-rejilla{stroke:var(--linea);stroke-width:1}
.f-cero{stroke:var(--tinta-2);stroke-width:1}
.f-ic{stroke:var(--marino);stroke-width:2;stroke-linecap:round}
.f-punto{stroke:var(--marino);stroke-width:11;stroke-linecap:round}
.f-hueco{stroke:var(--blanco);stroke-width:6;stroke-linecap:round}
.f-n{font-size:13px;font-variant-numeric:tabular-nums;color:var(--tinta-2);text-align:right;white-space:nowrap}
.f-eje{box-shadow:inset 0 1px 0 var(--tinta-2);padding-top:8px}
.f-eje-et{font-size:13px;color:var(--tinta-2)}
.f-eje-ticks{position:relative;height:20px;font-size:12px;color:var(--tinta-2);font-variant-numeric:tabular-nums}
.f-eje-ticks span{position:absolute;top:0;transform:translateX(-50%)}
.f-eje-ticks span:first-child{transform:none}
.f-eje-ticks span:last-child{transform:translateX(-100%)}
.filtros{display:flex;flex-wrap:wrap;gap:12px 20px;align-items:flex-end;margin:12px 20px}
.filtros label{display:flex;flex-direction:column;font-size:14px;font-weight:600;gap:4px}
.filtros select{min-height:44px;padding:0 12px;border:1px solid var(--tinta-2);border-radius:var(--radio);background:var(--blanco);color:var(--tinta);font:15px var(--texto)}
.filtros output{font-size:14px;color:var(--tinta-2);padding-bottom:10px}
/* limitaciones */
.limites{padding-left:20px}
.limites li{margin:14px 0}
@media (max-width:719px){
 .hallazgo .fig{margin:16px -8px 12px}
 body{font-size:16px}
 .puerta{padding:56px 12px 0}
 .sector{padding:24px 16px 28px}
 .letrero{gap:14px;margin-bottom:16px}
 .letrero-num{min-width:56px;height:56px;font-size:42px}
 .cifra{padding:20px 16px;margin-bottom:20px}
 .cifra-texto{font-size:16px}
 .cifra-valor small{font-size:24px}
 .filas-talon dd{font-size:19px}
 .f-fila{grid-template-columns:minmax(0,1fr) auto;gap:0 8px;padding:1px 0;box-shadow:none}
 .f-et{grid-column:1;grid-row:1;font-size:13px;line-height:1.3}
 .f-n{grid-column:2;grid-row:1;font-size:12px}
 .f-plot{grid-column:1 / -1;grid-row:2;height:12px}
 .f51 .pie,.f-leyenda{font-size:14px}
 .f-leyenda{margin:4px 0 6px}
 .f-dif{display:none}
 .f-eje{grid-template-columns:minmax(0,1fr);margin-top:12px}
 .f-eje-et{grid-row:2}
 .sector .f51 h3.f-grupo{margin-top:10px;font-size:17px}
 .hallazgo{margin-top:20px;padding:16px 12px 4px}
 .sector .hallazgo h3{font-size:18px}
 .hallazgo-titular{margin-bottom:12px}
 .niveles{gap:6px}
 .nivel{flex-basis:6.5rem;padding:8px}
 .nivel-valor{font-size:21px}
 .hallazgo-lectura,.hallazgo-tambien{font-size:15px}
 .pliegue > :not(summary){margin-left:12px;margin-right:12px}
 .pliegue figure{margin:20px 12px}
 .filtros{margin:12px}
 th,td{padding:8px 8px}
 table{font-size:14px}
 .marco{padding:8px}
 .boleto-cuerpo{grid-template-columns:minmax(0,1fr)}
 .boleto-foto{grid-column:1;grid-row:2;justify-self:center;margin:24px 0 -32px}
 .escudo-img{width:clamp(80px,18vw,112px)}
 .cifra-valor{font-size:60px}
 .puerta{padding-top:48px}
}
@media (max-width:600px){
 .filas-talon > div.apilar{flex-direction:column;align-items:flex-start;gap:2px}
 .filas-talon .apilar dd{text-align:left;white-space:normal}
}
@media print{
 .barra,.saltar,[role="tablist"],.filtros,.ampliar-pista{display:none!important}
 body{padding-top:0;background:#fff}
 .panel[hidden]{display:block!important}
 .con-pestanas .panel-torneo{position:static;width:auto;height:auto;clip:auto}
 details::details-content{content-visibility:visible;display:contents}
 .puerta{padding-top:24px;break-before:page}
 tr[hidden]{display:table-row!important}
}
"""

JS = r"""
(function(){
var d=document;d.documentElement.classList.add('js');
var barra=d.querySelector('.barra'),lista=d.getElementById('lista-puertas'),boton=d.querySelector('.barra-boton');
var actual=d.querySelector('.barra-actual'),muesca=d.querySelector('.muesca');
var enlaces=[].slice.call(lista.querySelectorAll('a')),activo=null;
function moverMuesca(){
 if(!activo){muesca.style.opacity='0';return;}
 muesca.style.opacity='1';muesca.style.width=Math.max(activo.offsetWidth-24,20)+'px';
 muesca.style.transform='translateX('+(activo.offsetLeft+12)+'px)';
}
function marcar(a){
 if(a===activo)return;activo=a;
 enlaces.forEach(function(x){if(x===a)x.setAttribute('aria-current','location');else x.removeAttribute('aria-current');});
 actual.querySelector('b').textContent=a?a.getAttribute('data-num'):'';
 actual.querySelector('span').textContent=a?a.getAttribute('data-et'):'Inicio';
 moverMuesca();
}
var objetivos=[d.getElementById('inicio')].concat(enlaces.map(function(a){return d.getElementById(a.getAttribute('href').slice(1));}));
if('IntersectionObserver' in window){
 var io=new IntersectionObserver(function(entradas){
  entradas.forEach(function(e){
   if(!e.isIntersecting)return;
   var id=e.target.id;marcar(enlaces.filter(function(a){return a.getAttribute('href')==='#'+id;})[0]||null);
  });
 },{rootMargin:'-25% 0px -74% 0px'});
 objetivos.forEach(function(s){if(s)io.observe(s);});
}
window.addEventListener('resize',moverMuesca);
function cerrar(){barra.classList.remove('abierta');boton.setAttribute('aria-expanded','false');}
boton.addEventListener('click',function(){
 var abrir=boton.getAttribute('aria-expanded')!=='true';
 boton.setAttribute('aria-expanded',String(abrir));barra.classList.toggle('abierta',abrir);
 if(abrir&&enlaces[0])enlaces[0].focus();
});
d.addEventListener('keydown',function(ev){if(ev.key==='Escape'&&barra.classList.contains('abierta')){cerrar();boton.focus();}});
d.addEventListener('click',function(ev){if(barra.classList.contains('abierta')&&!barra.contains(ev.target))cerrar();});
enlaces.forEach(function(a){a.addEventListener('click',cerrar);});
/* pestanas por torneo, sincronizadas: elegir un torneo lo cambia en todas las figuras */
var grupos=[];
function elegirTorneo(nombre,origen,foco){
 grupos.forEach(function(g){
  var i=g.nombres.indexOf(nombre);if(i<0)return;
  g.botones.forEach(function(b,j){var si=i===j;b.setAttribute('aria-selected',String(si));b.tabIndex=si?0:-1;g.paneles[j].hidden=!si;});
  if(foco&&g===origen)g.botones[i].focus();
 });
}
[].forEach.call(d.querySelectorAll('[data-pestanas]'),function(caja){
 var paneles=[].slice.call(caja.children).filter(function(x){return x.classList.contains('panel');});
 if(paneles.length<2)return;
 var tl=d.createElement('div');tl.setAttribute('role','tablist');tl.setAttribute('aria-label',caja.getAttribute('data-pestanas'));
 var g={paneles:paneles,nombres:[],botones:[]};
 paneles.forEach(function(p,i){
  var b=d.createElement('button');b.type='button';b.setAttribute('role','tab');b.id=caja.id+'-t'+i;
  b.setAttribute('aria-controls',p.id);b.textContent=p.getAttribute('data-torneo');
  p.setAttribute('role','tabpanel');p.setAttribute('aria-labelledby',b.id);p.tabIndex=0;tl.appendChild(b);
  g.botones.push(b);g.nombres.push(p.getAttribute('data-torneo'));
  b.addEventListener('click',function(){elegirTorneo(g.nombres[i],g,false);});
 });
 tl.addEventListener('keydown',function(ev){
  var i=g.botones.indexOf(d.activeElement),n=g.botones.length,j=null;if(i<0)return;
  if(ev.key==='ArrowRight')j=(i+1)%n;else if(ev.key==='ArrowLeft')j=(i-1+n)%n;else if(ev.key==='Home')j=0;else if(ev.key==='End')j=n-1;
  if(j!==null){ev.preventDefault();elegirTorneo(g.nombres[j],g,true);}
 });
 g.inicio=caja.getAttribute('data-inicio');caja.insertBefore(tl,paneles[0]);caja.classList.add('con-pestanas');grupos.push(g);
});
/* al cargar: las figuras por torneo abren en el primero; las de contexto, en su pestaña de inicio («91 partidos»),
   que solo ellas tienen, asi que elegirla no mueve a las demas */
var normal=grupos.filter(function(g){return !g.inicio;})[0];
if(normal)elegirTorneo(normal.nombres[0],null,false);
grupos.forEach(function(g){if(g.inicio)elegirTorneo(g.inicio,null,false);});
/* figuras en pantallas chicas: tocar abre la vista ampliada; Escape o Cerrar vuelve a la figura */
var visor=d.createElement('dialog');visor.className='visor';visor.setAttribute('aria-label','Figura ampliada');
visor.innerHTML='<div class="visor-barra"><p></p><button type="button" class="visor-cerrar">Cerrar</button></div><div class="visor-lienzo" tabindex="0"><img alt=""></div>';
d.body.appendChild(visor);
var vTit=visor.querySelector('p'),vImg=visor.querySelector('img'),origenVisor=null;
visor.querySelector('.visor-cerrar').addEventListener('click',function(){visor.close();});
visor.addEventListener('close',function(){if(origenVisor)origenVisor.focus();});
var chico=window.matchMedia('(max-width:600px)');
var marcos=[].slice.call(d.querySelectorAll('.fig .marco'));
function abrirVisor(b,img){
 var fig=img.closest('figure'),panel=img.closest('.panel');
 vTit.textContent=(fig?fig.querySelector('.codigo').textContent:'')+(panel?' · '+panel.getAttribute('data-torneo'):'');
 vImg.src=img.src;vImg.alt=img.alt;vImg.width=img.naturalWidth||img.width;vImg.height=img.naturalHeight||img.height;
 origenVisor=b;if(typeof visor.showModal==='function')visor.showModal();else visor.setAttribute('open','');
 visor.querySelector('.visor-lienzo').scrollTo(0,0);
}
function ampliables(){
 marcos.forEach(function(m){
  var img=m.querySelector('img'),b=m.querySelector('.ampliar');if(!img)return;
  var siempre=!!m.closest('.hallazgo');/* las canchas de contexto se amplian tambien en escritorio */
  if((chico.matches||siempre)&&!b){
   b=d.createElement('button');b.type='button';b.className='ampliar';
   m.insertBefore(b,img);b.appendChild(img);
   var pista=d.createElement('span');pista.className='ampliar-pista';pista.textContent='Ver en grande';b.appendChild(pista);
   b.addEventListener('click',function(){abrirVisor(b,img);});
  }else if(!chico.matches&&!siempre&&b){m.insertBefore(img,b);m.removeChild(b);}
 });
}
if(chico.addEventListener)chico.addEventListener('change',ampliables);else if(chico.addListener)chico.addListener(ampliables);
ampliables();
/* enlaces a definiciones o figuras dentro de un plegable */
function abrirDestino(id){
 var el=id&&d.getElementById(id);if(!el)return;
 var p=el.closest('details');while(p){p.open=true;p=p.parentElement&&p.parentElement.closest('details');}
 el.scrollIntoView({block:'start'});
}
d.addEventListener('click',function(ev){
 var a=ev.target.closest&&ev.target.closest('a[href^="#def-"],a[href^="#t"],a[href^="#f"],a[href="#como-leer"],a[href="#terminos"],a[href="#matriz"]');
 if(a){var id=a.getAttribute('href').slice(1),el=d.getElementById(id);if(el&&el.closest('details:not([open])')){ev.preventDefault();history.pushState(null,'','#'+id);abrirDestino(id);}}
});
window.addEventListener('hashchange',function(){abrirDestino(decodeURIComponent(location.hash.slice(1)));});
if(location.hash)abrirDestino(decodeURIComponent(location.hash.slice(1)));
/* T5.1: filtros por contexto y lectura */
var tabla=d.getElementById('t5-1-tabla'),caja=d.getElementById('t5-1-filtros');
if(tabla&&caja){
 var filas=[].slice.call(tabla.tBodies[0].rows);
 function selector(attr,titulo){
  var lab=d.createElement('label'),s=d.createElement('select'),vistos={},orden=[];
  lab.textContent=titulo;
  filas.forEach(function(r){var v=r.getAttribute('data-'+attr);if(!(v in vistos)){vistos[v]=r.getAttribute('data-'+attr+'-et');orden.push(v);}});
  var o=d.createElement('option');o.value='';o.textContent='Todos';s.appendChild(o);
  var fijo=(tabla.getAttribute('data-orden-'+attr)||'').split('|');
  if(fijo[0])orden.sort(function(a,b){return fijo.indexOf(a)-fijo.indexOf(b);});
  orden.forEach(function(v){var o=d.createElement('option');o.value=v;o.textContent=vistos[v];s.appendChild(o);});
  lab.appendChild(s);caja.appendChild(lab);return s;
 }
 var sc=selector('contexto','Contexto'),sl=selector('lectura','Lectura'),out=d.createElement('output');
 out.setAttribute('aria-live','polite');caja.appendChild(out);
 function filtrar(){
  var c=sc.value,l=sl.value,n=0;
  filas.forEach(function(r){var ok=(!c||r.getAttribute('data-contexto')===c)&&(!l||r.getAttribute('data-lectura')===l);r.hidden=!ok;if(ok)n++;});
  out.textContent='Se ven '+n+' de '+filas.length+' comparaciones.';
 }
 sc.addEventListener('change',filtrar);sl.addEventListener('change',filtrar);filtrar();caja.hidden=false;
}
/* impresion: abre los plegables y muestra todos los torneos */
var abiertos=[];
window.addEventListener('beforeprint',function(){abiertos=[].filter.call(d.querySelectorAll('details'),function(x){return !x.open;});abiertos.forEach(function(x){x.open=true;});});
window.addEventListener('afterprint',function(){abiertos.forEach(function(x){x.open=false;});abiertos=[];});
})();
"""


# ---------------------------------------------------------------- main

def main():
    try:
        sys.stdout.reconfigure(errors="replace")  # acentos en consolas sin UTF-8
        sys.stderr.reconfigure(errors="replace")
    except AttributeError:
        pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--salida", default=SALIDA, help=f"HTML de salida (por defecto {SALIDA})")
    p.add_argument("--figuras", default=FIGURAS_DIR, help=f"carpeta de figuras de Pablo (por defecto {FIGURAS_DIR})")
    p.add_argument("--recursos", default=RECURSOS_DIR,
                   help=f"carpeta con los logos y la foto de la portada (por defecto {RECURSOS_DIR}; de "
                        f"Local/ARCHIVOS_YORDI/preparar_recursos.py)")
    p.add_argument("--framework", default=FRAMEWORK_DIR,
                   help=f"carpeta del framework de Pato (por defecto {FRAMEWORK_DIR})")
    p.add_argument("--textos", default=TEXTOS_DIR,
                   help=f"carpeta con un md por espacio pendiente (por defecto {TEXTOS_DIR}; puede no existir)")
    p.add_argument("--sin-escribir", action="store_true", help="arma y verifica sin escribir")
    p.add_argument("--estricto", action="store_true", help="falla si falta un texto, una figura o un recurso")
    args = p.parse_args()
    inicio = time.perf_counter()
    salida, figuras_dir = ruta_repo(args.salida), ruta_repo(args.figuras)
    framework_dir, textos_dir = ruta_repo(args.framework), ruta_repo(args.textos)
    recursos_dir = ruta_repo(args.recursos)

    if not WEBP:
        causa = "Pillow no esta instalado" if not PILLOW else "Pillow esta instalado sin soporte WebP (falta libwebp)"
        print(f"ERROR: {causa}. Sin WebP las figuras no se pueden reducir y el HTML no cabe en un correo. Corre "
              f"'pip install -r requirements.txt' (o 'pip install --force-reinstall pillow' con las ruedas oficiales, "
              f"que traen WebP).\nNo se escribio nada.", file=sys.stderr)
        return 1
    if not figuras_dir.is_dir():
        print(f"ERROR: no existe la carpeta de figuras {figuras_dir} (figuras de Pablo, scripts/graficas.py de "
              f"C/visualizacion); pasa la carpeta con --figuras.\nNo se escribio nada.", file=sys.stderr)
        return 1
    try:
        datos = cargar(framework_dir)
        cifras = calcular_cifras(datos)
        cuadres(cifras)
        doc, reporte = armar(datos, cifras, figuras_dir, textos_dir, recursos_dir)
    except ErrorReporte as e:
        print(f"ERROR: {e}\nNo se escribio nada.", file=sys.stderr)
        return 1
    avisar_faltantes(reporte)
    fallas, info = verificar(doc, reporte, args.estricto, len(datos.comps))
    resumen(cifras, reporte, info)
    if fallas:
        sys.stdout.flush()  # que el ERROR salga despues del resumen, tambien con 2>&1
        print(f"ERROR: {len(fallas)} revisiones fallaron:", file=sys.stderr)
        for f in fallas:
            print(f"   {f}", file=sys.stderr)
        print("No se escribio nada.", file=sys.stderr)
        return 1
    if args.sin_escribir:
        print(f"Sin escribir (--sin-escribir). {time.perf_counter() - inicio:.1f} s")
        return 0
    try:
        escribir(doc, salida)
    except ErrorReporte as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    try:
        mostrar = salida.relative_to(ROOT).as_posix()
    except ValueError:
        mostrar = str(salida)
    print(f"Escrito en {mostrar} ({info['peso'] / 1024 ** 2:.2f} MB). {time.perf_counter() - inicio:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
