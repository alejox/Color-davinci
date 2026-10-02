# Color DaVinci – LUTs para iPhone 16

LUTs `.cube` para llevar material del iPhone 16 grabado en **Apple Log** a Rec.709.

| LUT | Uso |
|---|---|
| `Neutral` | Transformación técnica: Apple Log/Rec.2020 → Rec.709 gamma 2.4, con hombro suave en altas luces. Punto de partida para corregir. |
| `Punchy` | Neutral + curva S y +12 % de saturación. |
| `Bright` | Neutral con +0.5 EV, para tomas subexpuestas. |

## Uso en DaVinci Resolve
1. Copia los `.cube` a la carpeta de LUTs (Resolve: *Preferencias › Sistema › Color › Abrir carpeta de LUT*) y actualiza la lista.
2. Línea de tiempo en Rec.709 gamma 2.4 (sin Color Management). Aplica la LUT en un nodo, o en *Clip LUT*.
3. Si usas Resolve Color Management, no uses estas LUTs: elige Apple Log como espacio de entrada.

## Interfaz gráfica
Abre `app/index.html` en cualquier navegador (también en el celular). Carga un fotograma (PNG recomendado) o un video, o usa la escena de ejemplo. Muestra original y corregido con histogramas, el análisis, presets, sliders de exposición, temperatura, tinte, contraste y saturación, y exporta el `.cube` con tus ajustes. Todo corre en el navegador; las LUTs que genera coinciden con las de `tools/generate_luts.py`.

## Analizador de clips (sugerencia de corrección)
```
pip install -r requirements.txt          # y tener ffmpeg instalado
python3 tools/analyze_clip.py mi_clip.mov            # análisis + LUT propia del clip
python3 tools/analyze_clip.py mi_clip.mov --ai       # + sugerencia de look con Claude
```
Muestrea fotogramas, los decodifica de Apple Log a luz lineal y mide exposición, dominante de color, rango dinámico (stops), saturación y recortes. Con eso calcula exposición (EV), balance de blancos, contraste y saturación, y escribe en `analysis/<clip>/`: `report.json`, `<clip>_Suggested.cube` y `preview.jpg` (ya en Rec.709).

- Las reglas son heurísticas: son un punto de partida, no sustituyen al ojo del colorista. El balance de blancos (gray-world) falla con escenas dominadas por un solo color; `--wb-strength 0` lo desactiva.
- `--ai` requiere `ANTHROPIC_API_KEY`; envía a Claude una tira de fotogramas en Rec.709 y las medidas, y devuelve diagnóstico, look y consejos para Resolve.
- Solo para material en Apple Log.

## Regenerar las LUTs base
`python3 tools/generate_luts.py --size 65`

## Notas
- Apple Log se decodifica con las constantes del *Apple Log Profile White Paper* y el gamut Rec.2020 se convierte a Rec.709 con recorte.
- Pendiente: Apple Log 2 y HLG/otros perfiles (ver abajo).
