import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from mplsoccer import VerticalPitch

partido = pd.read_parquet("eventos.parquet")
equipo = partido.loc[partido["es_equipo_analizado"], "team_name"].iloc[0]

tiros = partido[(partido["type_name"] == "Shot") & partido["es_equipo_analizado"] & (partido["period"] < 5)]
tiros = tiros.dropna(subset=["x", "y"])
goles = tiros[tiros["shot_outcome_name"] == "Goal"]
no_goles = tiros[tiros["shot_outcome_name"] != "Goal"]

fig, ax = plt.subplots(figsize=(10, 9))
pitch = VerticalPitch(pitch_type="statsbomb", goal_type="box", half=True)
pitch.draw(ax=ax)

pitch.scatter(no_goles.x, no_goles.y, ax=ax, s=no_goles.shot_statsbomb_xg * 1500 + 30,
              alpha=.6, ec="black", color="white", zorder=1)
pitch.scatter(goles.x, goles.y, ax=ax, s=goles.shot_statsbomb_xg * 1500 + 30,
              alpha=.9, ec="black", color="blue", zorder=2)

leyenda = [Line2D([], [], marker="o", ls="", ms=12, mfc="white", mec="black", label="Tiros"),
           Line2D([], [], marker="o", ls="", ms=12, mfc="blue", mec="black", label="Goles")]
ax.legend(handles=leyenda, ncol=2, loc="lower center", prop={"size": 14}, shadow=True, edgecolor="black")

ax.text(0.97, 0.97, f"Ataque\n{equipo}", transform=ax.transAxes, va="top", ha="right", fontsize=20, fontweight="bold")
ax.text(0.97, 0.86, f"{len(tiros)} Tiros\n{len(goles)} Goles\n{tiros.shot_statsbomb_xg.sum():.2f} xG",
        transform=ax.transAxes, va="top", ha="right", fontsize=16)

plt.show()