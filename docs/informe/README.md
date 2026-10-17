# Informe tipo paper (PLAN §13)

| Archivo | Contenido |
|---|---|
| `informe.md` | Fuente del informe en Markdown, en español. Fórmulas con `$...$` y `$$...$$` (KaTeX); figuras como `../figures/<nombre>.png` |
| `render_pdf.py` | Markdown → HTML con KaTeX → PDF con Chrome headless |
| `figura_escenario.py` | Figura 1 (`docs/figures/escenario_corredor.png`), dibujada desde `env/net/reforma.net.xml` sin simular |
| `informe.pdf` | PDF de entrega (`--pdf --final`), versionado |
| `informe.html` | Salida intermedia (ignorada por git) |

## Estado del borrador

- Todas las secciones están escritas con los resultados finales de E1 a E8. Cada número de las secciones 7 y 8 (y del resumen y las conclusiones) sale de `analysis/results/*.md`, generados con `python -m analysis.make_all` desde `runs/`, y cada figura de `docs/figures/`.
- Los conteos, el ciclo de tiempo fijo y la referencia de validación siguen siendo **sintéticos o provisionales**, y el informe lo dice explícitamente (secciones 4.3–4.5 y 9.2). Si se consiguen datos de campo, hay que actualizar esas secciones, quitar las advertencias y volver a correr la matriz.
- Falta que el equipo complete a mano: integrantes, enlace al repositorio y fecha; el dato con fuente sobre el tráfico en Guatemala (`DATO`, sección 1.1); los `COMPLETAR` de datos de campo (secciones 4.3–4.5) y de otras herramientas de IA; la verificación manual y la tabla de ejemplos de uso de IA (sección 11), y la revisión de las referencias (`PENDIENTE`).

## Cómo llenar los resultados

```bash
source scripts/env.sh
python -m analysis.make_all          # figuras en docs/figures/, tablas en analysis/results/*.md
```
Además de las de abajo, `make_all` genera `resumen_demora_total`, `E7_degradation`, `E8_tradeoff_<escenario>`, `CO2_reforma_pico`, `seleccion_validacion_marl` y `seleccion_validacion_agente_unico`; `analysis/results/RESUMEN.md` lista todas con su descripción y las respuestas de E1 a E8. Los nombres de figura que espera el informe son los que genera `analysis/plots.py`: `E{1..6}_eval_bars.png`, `E{2..6}_learning_curves.png`, `E7_robustness.png`, `E8_fairness_reforma_pico.png` y `E8_fairness_cruce_pico.png`. La Figura 1 (`escenario_corredor.png`, la red con los 5 semáforos) se genera con `python docs/informe/figura_escenario.py`. Las tablas del informe se copiaron (redondeadas) desde `analysis/results/E*.md`; si se vuelve a correr la matriz hay que actualizarlas a mano.

## Cómo generar el PDF en esta Mac

En esta máquina no hay LaTeX ni pandoc. El script convierte el Markdown en HTML con el paquete `markdown` de Python (si no está instalado, usa un conversor mínimo incluido en el script), carga KaTeX 0.16.9 desde cdnjs para renderizar las fórmulas e imprime el HTML a PDF con Google Chrome en modo headless. La única dependencia de red es el CDN de KaTeX, que resuelve Chrome al abrir el HTML.

```bash
source scripts/env.sh
python docs/informe/render_pdf.py            # escribe docs/informe/informe.html e imprime el comando de Chrome
python docs/informe/render_pdf.py --pdf      # además ejecuta Chrome y deja docs/informe/informe.pdf
python docs/informe/render_pdf.py --pdf --final   # versión de entrega: oculta los marcadores RESULTADOS/COMPLETAR
```

- **Borrador vs. entrega.** Sin `--final`, los comentarios que empiezan con `RESULTADOS`, `COMPLETAR`, `FIGURA`, `DATO`, `PENDIENTE`, `INSTRUCCIONES` o `BORRADOR` se muestran como recuadros amarillos, para revisar qué falta. Con `--final` desaparecen. Las figuras que todavía no existen se dibujan como un recuadro con su nombre.
- **Chrome no siempre termina solo** en headless en esta Mac: escribe el PDF y se queda abierto. Con `--pdf`, el script espera a que el archivo tenga un tamaño estable y luego cierra el proceso. Si se corre a mano el comando que imprime el script, hay que cerrarlo con Ctrl-C cuando aparezca el PDF.
- **Sin Chrome.** Se puede abrir `informe.html` en cualquier navegador e imprimir a PDF (tamaño carta, sin encabezados ni pies de página).
- El HTML se escribe junto a `informe.md` para que las rutas `../figures/` resuelvan bien.

Reglas al editar `informe.md`:
- Fórmulas en línea con `$...$` (sin espacio justo después del `$` inicial ni antes del final) y en bloque con `$$` en líneas propias. Se protegen antes de convertir el Markdown, así que `_`, `*` y `\` dentro de ellas no necesitan escaparse.
- No usar `|` dentro de fórmulas que estén en tablas (usar `\mid` o `\lvert ... \rvert`).
- Los marcadores para el equipo van en comentarios HTML que empiezan con una de las palabras clave de arriba. No anidar comentarios.
- Los textos `<completar>` se muestran tal cual (el script los escapa).
