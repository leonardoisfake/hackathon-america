import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from mplsoccer import Pitch

partido = pd.read_parquet("eventos.parquet")
equipo = partido.loc[partido["es_equipo_analizado"], "team_name"].iloc[0]

tipos = ["Pressure", "Foul Committed", "Interception", "Block"]
defensivas = partido[(partido["period"] < 5) & (
    partido["type_name"].isin(tipos)
    | ((partido["type_name"] == "Duel") & (partido["duel_type_name"] == "Tackle"))
    | ((partido["type_name"] == "Pass") & (partido["pass_type_name"] == "Interception"))
)].dropna(subset=["x", "y"])

propias = defensivas[defensivas["es_equipo_analizado"]]
rival = defensivas[~defensivas["es_equipo_analizado"]]

colores = ["#171832", "#323A60", "#45537F", "#7183A3", "#B5C6D5", "#D3DEE4", "#DEDFE0",
           "#F2BAAD", "#F7A18E", "#F17B67", "#E84335", "#E11F19", "#B40B0E"]
cmap = LinearSegmentedColormap.from_list("statsbomb", colores)

pitch = Pitch(pitch_type="statsbomb", line_zorder=2, line_color="black", pad_top=10, pad_bottom=20)
fig, ax = pitch.draw(figsize=(12, 8))

stat = pitch.bin_statistic(propias.x, propias.y, statistic="count", bins=(6, 5))
stat_rival = pitch.bin_statistic(rival.x, rival.y, statistic="count", bins=(6, 5))
stat["statistic"] = stat["statistic"] / stat["statistic"].sum() * 100 - stat_rival["statistic"] / stat_rival["statistic"].sum() * 100

limite = np.abs(stat["statistic"]).max()
hm = pitch.heatmap(stat, ax=ax, cmap=cmap, vmin=-limite, vmax=limite, zorder=1)
pitch.label_heatmap(stat, ax=ax, str_format="{:+.1f}", fontsize=13, fontweight="bold", ha="center", va="center", zorder=3,
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")])

ax.arrow(10, 85, 100, 0, head_width=4, head_length=8, fc="k", ec="k", clip_on=False)
ax.text(60, 91, "Dirección de ataque", ha="center", va="center", fontsize=13, clip_on=False)
ax.set_title(f"¿Dónde defiende {equipo} frente a su rival?", fontsize=20, fontweight="bold")

cbar = fig.colorbar(hm, ax=ax, shrink=0.7, pad=0.02)
cbar.set_ticks([-limite, 0, limite])
cbar.set_ticklabels(["menos que el rival", "igual", "más que el rival"], fontsize=12)

fig.text(0.5, 0.06, f"Diferencia en puntos porcentuales: % de las acciones defensivas de {equipo} en cada zona menos el % del rival",
         ha="center", fontsize=11)
plt.show()