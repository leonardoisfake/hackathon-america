import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from mplsoccer import VerticalPitch

AQUI = Path(__file__).resolve().parent
ARCHIVO = "eventos_parquet"
TORNEOS = ["Apertura 2023", "Apertura 2024", "Clausura 2024", "Clausura 2025"]
CARPETA_SALIDA = AQUI / "graficas"

COLUMNAS = ["match_id", "id", "torneo", "period", "type_name", "team_name", "player_name", "es_equipo_analizado",
            "x", "y", "x_eq", "y_eq", "end_x", "end_y", "duel_type_name", "pass_type_name", "pass_outcome_name",
            "pass_completed", "pass_recipient_name", "shot_outcome_name", "shot_statsbomb_xg"]


def buscar_archivo():
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(ARCHIVO)
    for candidato in [ruta, AQUI / ruta, Path.cwd() / ruta]:
        if candidato.is_file():
            return candidato
    sys.exit(f"No encuentro '{ruta}'. Ponlo junto al script o pasa la ruta: python 3_tiros_ataque.py mi_archivo.parquet")


ruta = buscar_archivo()
disponibles = pd.read_parquet(ruta).columns
faltan = [c for c in COLUMNAS if c not in disponibles]
if faltan:
    sys.exit(f"A {ruta.name} le faltan columnas: {faltan}. Este script espera la tabla limpia 'eventos', no el parquet crudo.")

eventos = pd.read_parquet(ruta, columns=COLUMNAS)
eventos["torneo"] = eventos["torneo"].astype(str)
eventos["es_equipo_analizado"] = eventos["es_equipo_analizado"].fillna(False).astype(bool)
equipo = eventos.loc[eventos["es_equipo_analizado"], "team_name"].iloc[0]

torneos = [t for t in TORNEOS if t in set(eventos["torneo"])]
for t in set(TORNEOS) - set(torneos):
    print(f"Aviso: el torneo '{t}' no está en el archivo (torneos encontrados: {sorted(eventos['torneo'].unique())})")
if not torneos:
    sys.exit("Ningún torneo de la lista coincide con la columna torneo.")

CARPETA_SALIDA.mkdir(exist_ok=True)
por_torneo = {t: eventos[eventos["torneo"] == t] for t in torneos}


def cuadricula(titulo, figsize, **kw):
    fig, axs = plt.subplots(2, 2, figsize=figsize, **kw)
    fig.suptitle(titulo, fontsize=22, fontweight="bold")
    for ax in axs.flat[len(torneos):]:
        ax.axis("off")
    return fig, axs.flat


def titulo_panel(ax, t, extra=""):
    partidos = por_torneo[t]["match_id"].nunique()
    ax.set_title(f"{t}  ({partidos} partidos){extra}", fontsize=14, fontweight="bold")


def guardar(fig, nombre):
    ruta_png = CARPETA_SALIDA / nombre
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    print("Guardado:", ruta_png)


# 3 y 4. Mapas de tiros
def mapa_tiros(nombre, etiqueta, propios):
    fig, axs = cuadricula(f"{etiqueta} {equipo}", (14, 10))
    pitch_t = VerticalPitch(pitch_type="statsbomb", goal_type="box", half=True)
    for ax, t in zip(axs, torneos):
        d = por_torneo[t]
        tiros = d[(d["type_name"] == "Shot") & (d["es_equipo_analizado"] == propios) & (d["period"] < 5)].dropna(subset=["x", "y"])
        goles = tiros[tiros["shot_outcome_name"] == "Goal"]
        no_goles = tiros[tiros["shot_outcome_name"] != "Goal"]
        pitch_t.draw(ax=ax)
        pitch_t.scatter(no_goles.x, no_goles.y, ax=ax, s=no_goles.shot_statsbomb_xg.fillna(0) * 1000 + 25,
                        alpha=.6, ec="black", color="white", zorder=1)
        pitch_t.scatter(goles.x, goles.y, ax=ax, s=goles.shot_statsbomb_xg.fillna(0) * 1000 + 25,
                        alpha=.9, ec="black", color="blue", zorder=2)
        titulo_panel(ax, t)
        ax.text(0.97, 0.03, f"{len(tiros)} tiros\n{len(goles)} goles\n{tiros.shot_statsbomb_xg.sum():.1f} xG",
                transform=ax.transAxes, va="bottom", ha="right", fontsize=13, fontweight="bold",
                bbox=dict(fc="white", ec="black", alpha=.85))
    leyenda = [Line2D([], [], marker="o", ls="", ms=12, mfc="white", mec="black", label="Tiros"),
               Line2D([], [], marker="o", ls="", ms=12, mfc="blue", mec="black", label="Goles")]
    fig.legend(handles=leyenda, loc="lower center", ncol=2, fontsize=13, shadow=True, edgecolor="black")
    guardar(fig, nombre)


mapa_tiros("3_tiros_ataque.png", "Ataque", True)

plt.show()