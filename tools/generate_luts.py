#!/usr/bin/env python3
"""Genera LUTs .cube para material del iPhone 16 grabado en Apple Log.

Uso: python3 tools/generate_luts.py [--size 33]
Requiere numpy.

Apple Log (Apple Log Profile White Paper):
  gamut: Rec.2020 primaries, D65
  curva: segmento cuadratico en negros + logaritmica en el resto
"""
import argparse, os
import numpy as np

# --- Apple Log -> lineal de escena ---------------------------------------
R0, RT, C = -0.05641088, 0.01, 47.28711236
BETA, GAMMA, DELTA = 0.00964052, 0.08550479, 0.69336945
PT = C * (RT - R0) ** 2

M_2020_TO_709 = np.array([
    [1.660491, -0.587641, -0.072850],
    [-0.124550, 1.132900, -0.008349],
    [-0.018151, -0.100579, 1.118730],
])
LUMA = np.array([0.2126, 0.7152, 0.0722])


def apple_log_to_linear(p):
    p = np.asarray(p, dtype=np.float64)
    hi = 2 ** ((p - DELTA) / GAMMA) - BETA
    lo = np.sqrt(np.clip(p, 0, None) / C) + R0
    return np.where(p >= PT, hi, np.where(p <= 0, R0, lo))


def linear_to_apple_log(r):
    r = np.asarray(r, dtype=np.float64)
    hi = GAMMA * np.log2(np.clip(r + BETA, 1e-12, None)) + DELTA
    lo = C * (r - R0) ** 2
    return np.where(r >= RT, hi, np.where(r >= R0, lo, 0.0))


def shoulder(x, knee=0.55):
    """Lineal hasta 'knee', luego compresion suave hacia 1.0 (recupera altas luces)."""
    k = 1 - knee
    return np.where(x <= knee, x, knee + k * (1 - np.exp(-(x - knee) / k)))


def contrast(y, amount, pivot=0.49):
    """Curva S suave alrededor del gris medio de display (pivote 0.49 ~ 18% con gamma 2.4)."""
    if amount == 0:
        return y
    y = np.clip(y, 0.0, 1.0)
    return y + amount * (y - pivot) * y * (1 - y) * 2


def rec709_oetf(x):
    x = np.clip(x, 0, None)
    return np.where(x < 0.018, 4.5 * x, 1.099 * x ** 0.45 - 0.099)


def make_transform(exposure=0.0, contrast_amt=0.0, sat=1.0, oetf="gamma24", wb=(1.0, 1.0, 1.0)):
    """Devuelve f(rgb[...,3]) -> rgb[...,3] (Apple Log codigo -> Rec.709 display).

    wb: ganancias RGB en lineal (Rec.709) aplicadas antes de la exposicion.
    """
    gain = 2 ** exposure
    wb = np.asarray(wb, dtype=np.float64)

    def f(rgb):
        rgb = np.asarray(rgb, dtype=np.float64)
        lin = apple_log_to_linear(rgb) @ M_2020_TO_709.T
        lin = shoulder(np.clip(lin * wb * gain, 0.0, None))
        out = np.clip(lin, 0, None) ** (1 / 2.4) if oetf == "gamma24" else rec709_oetf(lin)
        out = contrast(out, contrast_amt)
        if sat != 1.0:
            l = (out @ LUMA)[..., None]
            out = l + (out - l) * sat
        return np.clip(out, 0.0, 1.0)

    return f


def write_cube(path, title, size, fn):
    n = size - 1
    # .cube: R varia mas rapido, luego G, luego B
    b, g, r = np.meshgrid(*(np.arange(size) / n,) * 3, indexing="ij")
    out = fn(np.stack([r, g, b], axis=-1).reshape(-1, 3))
    with open(path, "w") as fh:
        fh.write(f'TITLE "{title}"\nLUT_3D_SIZE {size}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n')
        np.savetxt(fh, out, fmt="%.6f")


LUTS = {
    "iPhone16_AppleLog_to_Rec709_Neutral": dict(exposure=0.0, contrast_amt=0.0, sat=1.0),
    "iPhone16_AppleLog_to_Rec709_Punchy": dict(exposure=0.0, contrast_amt=0.35, sat=1.12),
    "iPhone16_AppleLog_to_Rec709_Bright": dict(exposure=0.5, contrast_amt=0.15, sat=1.05),
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=33)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "luts"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for name, kw in LUTS.items():
        p = os.path.join(a.out, f"{name}.cube")
        write_cube(p, name, a.size, make_transform(**kw))
        print("escrito", p)
