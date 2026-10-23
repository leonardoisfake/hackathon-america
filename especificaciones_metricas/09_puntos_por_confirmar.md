[Volver al índice](README.md)

# 11. Puntos por confirmar con el equipo

## Resumen general

Diez puntos abiertos sobre umbrales y supuestos, numerados del 1 al 10. Las fichas que dependen de alguno lo señalan.

Son las dudas que salieron al convertir `Umbrales.pdf` en fórmulas. En cada una se indica lo que se asumió para poder avanzar.

1. **Unidad de la zona de presión alta.** `Umbrales.pdf` dice «últimos 40 metros» y los datos están en yardas. Se asumió 40 yardas (x ≥ 80, que coincide con el último tercio: 120 / 3). Si son metros reales (43.7 yardas), el corte es x ≥ 76.26. Además, StatsBomb define la presión alta como la que ocurre en la mitad rival (x ≥ 60); [D1](05_presion_y_defensa.md#d1-press_height-y-high_press) reporta ambas.
2. **«Evitando presiones» en la fase de inicio.** Se interpretó como reportar las salidas con y sin presión (`under_pressure`). La alternativa es excluir las salidas bajo presión, y entonces la fase de inicio solo contaría salidas tranquilas.
3. **Bloques del salto de líneas.** `Umbrales.pdf` habla de «los equipos» como tres bloques, sin decir si son los del equipo que pasa o los del rival ni cómo se miden. La versión 1 usa los bloques del EQ con la posición media por rol; la versión 2 usa los del rival con el `freeze_frame`. Hay que elegir cuál es la oficial.
4. **Posesión mínima.** ¿Los 3 pases son intentados o completos? ¿Qué cuenta como «toque del rival sin dirección»? Se asumió: pases intentados; toque sin dirección = `Block`, `Clearance`, `Miscontrol` o recuperación fallida.
5. **Fase de presión.** El PDF la deja como sugerencia. «Intentos de recuperación» se implementó como `Pressure`, `Ball Recovery`, `Duel Tackle` e `Interception`, con una variante de solo `Pressure`. ¿Cuál se usa?
6. **Cobertura mínima 360.** `Umbrales.pdf` pide «una cobertura mínima» sin valor. Provisional: actor visible y al menos 10 jugadores visibles. Se calibra con la distribución real de `visible_player_counts`.
7. **Pase corto del portero.** Sin valor en `Umbrales.pdf`. Provisional: 30 yardas.
8. **Contragolpe.** «Fuera del último tercio propio» se leyó como inicio en x ≥ 40 (el tercio más cercano a la propia portería es el primero). Confirmar.
9. **Progresivo y zona 14.** El umbral de 10% y los límites de la zona 14 son propuestas; no están en `Umbrales.pdf`.
10. **Transición.** Se mide con cambios de posesión en juego abierto y ventanas de 5 s. ¿Se quiere separar también por el tercio donde ocurre el cambio?
