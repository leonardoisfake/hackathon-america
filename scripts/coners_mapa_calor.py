import sys
from pathlib import Path

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from mplsoccer import VerticalPitch
from scipy.ndimage import gaussian_filter

AQUI = Path(__file__).resolve().parent
ARCHIVO = "eventos_parquet"
TORNEOS = ["Apertura 2023", "Apertura 2024", "Clausura 2024", "Clausura 2025"]
LADOS = ["Izquierda", "Derecha"]
CARPETA_SALIDA = AQUI / "graficas"

COLOR_CONTACTO = "#DEDFE0"
COLOR_TIRO = "#B40B0E"
COLOR_GOL = "#171832"
PALETA = ["white", "#9a9a9a", "#8f8f8f", "#858585", "#7a7a7a", "#707070", "#666666", "#5c5c5c", "#525252", "#484848",
          "#3f3f3f", "#9a1120", "#a2111f", "#aa111e", "#b2111d", "#ba111c", "#c2111b", "#ca111a", "#d11119", "#d91018", "#e21017"]
cmap = LinearSegmentedColormap.from_list("statsbomb", PALETA)
contorno = [pe.Stroke(linewidth=1.5, foreground="white"), pe.Normal()]

COLUMNAS = ["match_id", "id", "torneo", "period", "minute", "second", "possession", "type_name", "team_name", "player_name",
            "es_equipo_analizado", "x", "y", "end_x", "end_y", "x_eq", "y_eq", "pass_type_name", "pass_technique_name",
            "pass_recipient_name", "pass_shot_assist", "pass_goal_assist", "shot_key_pass_id"]


def buscar_archivo():
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(ARCHIVO)
    for candidato in [ruta, AQUI / ruta, Path.cwd() / ruta]:
        if candidato.is_file():
            return candidato
    sys.exit(f"No encuentro '{ruta}'. Ponlo junto al script o pasa la ruta: python 1_corners_mapa_calor.py mi_archivo")


ruta = buscar_archivo()
disponibles = pd.read_parquet(ruta).columns
faltan = [c for c in COLUMNAS if c not in disponibles]
if faltan:
    sys.exit(f"A {ruta.name} le faltan columnas: {faltan}. Este script espera la tabla limpia 'eventos'.")

eventos = pd.read_parquet(ruta, columns=COLUMNAS)
eventos["torneo"] = eventos["torneo"].astype(str)
eventos["es_equipo_analizado"] = eventos["es_equipo_analizado"].fillna(False).astype(bool)
equipo = eventos.loc[eventos["es_equipo_analizado"], "team_name"].iloc[0]
torneos = [t for t in TORNEOS if t in set(eventos["torneo"])]
for t in set(TORNEOS) - set(torneos):
    print(f"Aviso: el torneo '{t}' no está en el archivo (encontrados: {sorted(eventos['torneo'].unique())})")
if not torneos:
    sys.exit("Ningún torneo de la lista coincide con la columna torneo.")
eventos = eventos[eventos["torneo"].isin(torneos)].copy()
eventos["tiempo"] = eventos["minute"] * 60 + eventos["second"]
partidos = eventos.groupby("torneo")["match_id"].nunique()

corners = eventos[(eventos["type_name"] == "Pass") & (eventos["pass_type_name"] == "Corner") & eventos["es_equipo_analizado"]]
corners = corners.dropna(subset=["x", "y", "end_x", "end_y"]).copy()
corners["lado"] = np.where(corners["y"] < 40, "Izquierda", "Derecha")
corners["corto"] = np.where(corners["lado"] == "Izquierda", corners["end_y"] <= 18, corners["end_y"] >= 62)
CARPETA_SALIDA.mkdir(exist_ok=True)


def seleccion(t, lado):
    return corners[(corners["torneo"] == t) & (corners["lado"] == lado)]


def cuadricula(titulo, ancho, alto_fila, hspace=0.55):
    fig, axs = plt.subplots(len(torneos), 2, figsize=(ancho, alto_fila * len(torneos)), squeeze=False)
    fig.suptitle(f"{titulo}\n{equipo}", fontsize=20, fontweight="bold")
    fig.subplots_adjust(top=1 - 1.9 / (alto_fila * len(torneos)), hspace=hspace, wspace=0.25)
    return fig, axs


def corto_nombre(n):
    p = str(n).split()
    return p[0] if len(p) == 1 else f"{p[0]} {p[-1]}"


def guardar(fig, nombre):
    ruta_png = CARPETA_SALIDA / nombre
    fig.savefig(ruta_png, dpi=130, bbox_inches="tight")
    print("Guardado:", ruta_png)


pitch = VerticalPitch(pitch_type="statsbomb", half=True, line_color="black", pad_bottom=-5)
fig, axs = cuadricula("Hacia dónde cobra los córners", 15, 4.6, hspace=0.6)

for fila, t in enumerate(torneos):
    for col, lado in enumerate(LADOS):
        ax = axs[fila, col]
        todos = seleccion(t, lado)
        data = todos[~todos["corto"]]
        pitch.draw(ax=ax)
        ax.set_ylim(72, 122)
        cabecera = f"{t} ({partidos[t]} partidos) - Córners {lado.lower()}"
        if data.empty:
            ax.set_title(f"{cabecera}: sin datos", fontsize=13)
            continue
        stat = pitch.bin_statistic(data["end_x"], data["end_y"], statistic="count", bins=(15, 11), normalize=True)
        pitch.heatmap(stat, edgecolors="white", cmap=cmap, ax=ax, alpha=0.75, zorder=3)
        pitch.label_heatmap(stat, color="black", fontsize=11, fontweight="bold", ax=ax, ha="center", va="center",
                            str_format="{:.0%}", path_effects=contorno, exclude_zeros=True)
        pitch.scatter(data["end_x"], data["end_y"], ax=ax, color="grey", s=10)
        outs = (data["pass_technique_name"] == "Outswinging").mean() * 100
        ins = (data["pass_technique_name"] == "Inswinging").mean() * 100
        cobradores = todos.groupby("player_name").size().sort_values(ascending=False) / len(todos) * 100
        texto = " | ".join(f"{corto_nombre(n)} ({p:.0f}%)" for n, p in cobradores.head(2).items())
        ax.set_title(f"{cabecera}\nAl área: {len(data)} de {len(todos)} | Cobran: {texto}\n"
                     f"Outswinging: {outs:.0f}% | Inswinging: {ins:.0f}%", fontsize=12)

guardar(fig, "1_corners_mapa_calor.png")
plt.show()