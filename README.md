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

## Regenerar
`python3 tools/generate_luts.py --size 65` (sin dependencias).

## Notas
- Apple Log se decodifica con las constantes del *Apple Log Profile White Paper* y el gamut Rec.2020 se convierte a Rec.709 con recorte.
- Pendiente: Apple Log 2 y HLG/otros perfiles (ver abajo).
