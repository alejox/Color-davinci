#!/usr/bin/env python3
"""Analiza un clip/foto del iPhone 16 en Apple Log y sugiere una correccion de color.

  python3 tools/analyze_clip.py clip.mov                 # analisis + LUT del clip
  python3 tools/analyze_clip.py clip.mov --ai            # ademas: sugerencia de look con Claude
  python3 tools/analyze_clip.py foto.png --frames 1

Salidas (carpeta --out, por defecto ./analysis/<nombre>):
  report.json, <nombre>_Suggested.cube, preview.jpg (fotogramas ya en Rec.709)

Requiere: ffmpeg/ffprobe, numpy, pillow (y `anthropic` + ANTHROPIC_API_KEY para --ai).
Solo es valido para material grabado en Apple Log (no HLG / Rec.709 normal).
"""
import argparse, base64, io, json, os, subprocess, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from generate_luts import (apple_log_to_linear, M_2020_TO_709, LUMA, make_transform, write_cube)

WIDTH = 640
TARGET_MEDIAN = 0.16        # luminancia lineal de escena objetivo para el valor medio
MAX_EV = 1.5                # limite de correccion de exposicion
SPREAD_COLORFUL = 0.5       # dispersion de color a partir de la cual se considera escena colorida
SPREAD_MAX_WB = 0.9         # a partir de aqui no se corrige el balance de blancos


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True).stdout


def probe_duration(path):
    try:
        out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                   "-of", "default=nw=1:nk=1", path])
        return float(out.decode().strip())
    except Exception:
        return 0.0


def extract_frames(path, n):
    """Devuelve array (n, h, w, 3) float en [0,1] con los codigos Apple Log (sin tocar la curva)."""
    dur = probe_duration(path)
    fps = f"fps={n / dur:.6f}" if dur > 0.5 and n > 1 else "fps=1"
    vf = f"{fps},scale={WIDTH}:-2"
    first = run(["ffmpeg", "-v", "error", "-i", path, "-vf", vf, "-frames:v", "1",
                 "-f", "image2pipe", "-vcodec", "png", "-"])
    w, h = Image.open(io.BytesIO(first)).size
    raw = run(["ffmpeg", "-v", "error", "-i", path, "-vf", vf, "-frames:v", str(n),
               "-pix_fmt", "rgb48le", "-f", "rawvideo", "-"])
    frames = np.frombuffer(raw, dtype="<u2").reshape(-1, h, w, 3).astype(np.float64) / 65535.0
    if len(frames) == 0:
        sys.exit("No se pudieron extraer fotogramas.")
    return frames


def stats(frames):
    lin = apple_log_to_linear(frames) @ M_2020_TO_709.T          # lineal Rec.709
    y = (lin @ LUMA).ravel()
    p = lambda q: float(np.percentile(y, q))
    mid = (y > 0.03) & (y < 0.5)
    px = lin.reshape(-1, 3)[mid]
    mean_rgb = np.exp(np.log(np.clip(px, 1e-4, None)).mean(axis=0))  # media geometrica de medios
    chroma = np.abs(px - px.mean(axis=1, keepdims=True)).mean() / max(px.mean(), 1e-6)
    lg = np.log2(np.clip(px, 1e-4, None))
    ca, cb = lg[:, 0] - lg[:, 1], lg[:, 2] - lg[:, 1]      # cromaticidad en stops
    spread = float(np.hypot(ca - ca.mean(), cb - cb.mean()).mean())
    return dict(
        color_spread=spread,
        median=p(50), p1=p(1), p5=p(5), p95=p(95), p99=p(99),
        stops_range=float(np.log2(max(p(95), 1e-4) / max(p(5), 1e-4))),
        code_clip_hi=float((frames.max(axis=-1) > 0.98).mean()),
        code_clip_lo=float((frames.max(axis=-1) < 0.02).mean()),
        mid_rgb=mean_rgb.tolist(), chroma=float(chroma),
    ), lin


def suggest(s, wb_strength):
    notes = []
    # Exposicion: llevar la mediana a TARGET_MEDIAN, sin quemar altas luces
    ev = float(np.clip(np.log2(TARGET_MEDIAN / max(s["median"], 1e-4)), -MAX_EV, MAX_EV))
    hi_cap = float(np.log2(1.5 / max(s["p99"], 1e-4)))        # p99 <= 1.5 lineal (~5 stops sobre gris)
    if ev > hi_cap:
        ev = max(hi_cap, -MAX_EV)
        notes.append("Exposicion limitada para proteger altas luces.")
    ev = round(ev, 2)
    if abs(ev) < 0.15:
        ev = 0.0
    else:
        notes.append(f"{'Subir' if ev > 0 else 'Bajar'} exposicion {abs(ev):+.2f} EV".replace("+", ""))

    # Balance de blancos: gray-world sobre medios tonos, atenuado
    m = np.array(s["mid_rgb"])
    full = m.mean() / m
    # Con mucho color (luces de colores, objetos vivos) gray-world engaña: se atenua
    spread = s["color_spread"]
    colorful = spread > SPREAD_COLORFUL
    wb = full ** (wb_strength * float(np.clip((SPREAD_MAX_WB - spread) / (SPREAD_MAX_WB - SPREAD_COLORFUL), 0, 1)))
    wb = wb / wb[1]
    if colorful:
        notes.append(f"Escena con mucho color (dispersion {spread:.2f}): se atenua el balance de blancos automatico y no se sube la saturacion. Ajusta la piel a mano.")
    if np.abs(wb - 1).max() > 0.04:
        side = "calida" if wb[0] < wb[2] else "fria"
        notes.append(f"Dominante {side} detectada; ganancias RGB {wb.round(3).tolist()}.")
    else:
        wb = np.ones(3)

    # Contraste por rango dinamico en pantalla
    sr = s["stops_range"]
    c = 0.0 if sr >= 6.5 else float(np.clip((6.5 - sr) * 0.12, 0, 0.45))
    c = round(c, 2)
    if c:
        notes.append(f"Imagen plana ({sr:.1f} stops entre p5 y p95): contraste +{c}.")

    # Saturacion
    sat = round(float(np.clip(0.30 / max(s["chroma"], 1e-3), 0.9, 1.25)), 2) if s["chroma"] < 0.27 and not colorful else 1.0
    if s["chroma"] < 0.27 and not colorful and sat > 1.02:
        notes.append(f"Colores apagados: saturacion x{sat}.")
    else:
        sat = 1.0

    if s["code_clip_hi"] > 0.01:
        notes.append(f"{s['code_clip_hi']*100:.1f}% de pixeles cerca del tope del log: posibles altas luces recortadas en origen.")
    if s["code_clip_lo"] > 0.05:
        notes.append(f"{s['code_clip_lo']*100:.1f}% de pixeles en negro profundo: revisar sombras/ruido.")
    if not notes:
        notes.append("Exposicion y color correctos; la LUT Neutral basta.")
    return dict(exposure=ev, contrast_amt=c, sat=sat, wb=[round(float(x), 4) for x in wb]), notes


def contact_sheet(frames, params, max_frames=4):
    f = make_transform(**params)
    idx = np.linspace(0, len(frames) - 1, min(max_frames, len(frames))).astype(int)
    tiles = [(f(frames[i]) * 255).round().astype(np.uint8) for i in idx]
    return Image.fromarray(np.concatenate(tiles, axis=1))


AI_PROMPT = """Eres colorista profesional (DaVinci Resolve). Te paso fotogramas de un clip grabado con iPhone 16 \
en Apple Log, ya convertidos a Rec.709 con una correccion tecnica base, y las medidas objetivas del analisis.
Medidas: {stats}
Correccion base aplicada: {params}
Responde SOLO con JSON valido: {{"diagnostico": str, "look": str, "ajustes": {{"exposicion_ev": float, \
"contraste": float (-0.5..0.5), "saturacion": float (0.8..1.3), "temperatura": "mas calida|mas fria|ninguna", \
"tinte": "mas verde|mas magenta|ninguno"}}, "consejos_resolve": [str, ...]}}. Se concreto y en espanol."""


def ai_suggestion(sheet, s, params, model):
    try:
        import anthropic
    except ImportError:
        sys.exit("Falta el paquete: pip install anthropic")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Define ANTHROPIC_API_KEY para usar --ai")
    buf = io.BytesIO(); sheet.save(buf, "JPEG", quality=88)
    msg = anthropic.Anthropic().messages.create(
        model=model, max_tokens=1200,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(buf.getvalue()).decode()}},
            {"type": "text", "text": AI_PROMPT.format(stats=json.dumps(s), params=json.dumps(params))}]}])
    text = msg.content[0].text.strip()
    text = text[text.find("{"): text.rfind("}") + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"respuesta_sin_formato": text}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--frames", type=int, default=8, help="fotogramas a muestrear")
    ap.add_argument("--out", help="carpeta de salida")
    ap.add_argument("--size", type=int, default=33, help="tamano de la LUT")
    ap.add_argument("--wb-strength", type=float, default=0.6, help="0=sin correccion de blancos, 1=gray-world completo")
    ap.add_argument("--ai", action="store_true", help="pedir sugerencia de look a Claude")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    a = ap.parse_args()

    name = os.path.splitext(os.path.basename(a.input))[0]
    out = a.out or os.path.join("analysis", name)
    os.makedirs(out, exist_ok=True)

    frames = extract_frames(a.input, a.frames)
    s, _ = stats(frames)
    params, notes = suggest(s, a.wb_strength)

    lut = os.path.join(out, f"{name}_Suggested.cube")
    write_cube(lut, f"{name} suggested", a.size, make_transform(**params))
    sheet = contact_sheet(frames, params)
    sheet.save(os.path.join(out, "preview.jpg"), quality=90)

    report = dict(input=a.input, frames=len(frames), stats=s, suggested=params, notes=notes, lut=lut)
    if a.ai:
        report["ai"] = ai_suggestion(sheet, s, params, a.model)
    with open(os.path.join(out, "report.json"), "w") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print(f"\n== {name} ({len(frames)} fotogramas) ==")
    print(f"Mediana lineal {s['median']:.3f} | rango {s['stops_range']:.1f} stops | croma {s['chroma']:.2f}")
    print("Sugerido:", params)
    for n in notes:
        print(" -", n)
    if "ai" in report:
        print("\nIA:", json.dumps(report["ai"], indent=2, ensure_ascii=False))
    print(f"\nLUT: {lut}\nVista previa: {os.path.join(out, 'preview.jpg')}")


if __name__ == "__main__":
    main()
