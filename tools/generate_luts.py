#!/usr/bin/env python3
"""Genera LUTs .cube para material del iPhone 16 grabado en Apple Log.

Sin dependencias externas. Uso: python3 tools/generate_luts.py [--size 33]

Apple Log (Apple Log Profile White Paper):
  gamut: Rec.2020 primaries, D65
  curva: segmento cuadratico en negros + logaritmica en el resto
"""
import argparse, math, os

# --- Apple Log -> lineal de escena ---------------------------------------
R0, RT, C = -0.05641088, 0.01, 47.28711236
BETA, GAMMA, DELTA = 0.00964052, 0.08550479, 0.69336945
PT = C * (RT - R0) ** 2


def apple_log_to_linear(p):
    if p >= PT:
        return 2 ** ((p - DELTA) / GAMMA) - BETA
    if p <= 0:
        return R0
    return math.sqrt(p / C) + R0


# --- Gamut Rec.2020 -> Rec.709 (lineal) ----------------------------------
M_2020_TO_709 = (
    (1.660491, -0.587641, -0.072850),
    (-0.124550, 1.132900, -0.008349),
    (-0.018151, -0.100579, 1.118730),
)


def mat(m, v):
    return tuple(sum(m[i][j] * v[j] for j in range(3)) for i in range(3))


# --- Tone mapping + OETF de salida ---------------------------------------
def shoulder(x, knee=0.55):
    """Lineal hasta 'knee', luego compresion suave hacia 1.0 (recupera altas luces)."""
    if x <= knee:
        return x
    k = 1 - knee
    return knee + k * (1 - math.exp(-(x - knee) / k))


def contrast(y, amount):
    """Curva S suave alrededor del gris medio de display (pivote 0.49 ~ 18% con gamma 2.4)."""
    if amount == 0:
        return y
    pivot = 0.49
    y = min(max(y, 0.0), 1.0)
    return y + amount * (y - pivot) * y * (1 - y) * 4 * 0.5


def gamma_encode(x, g=2.4):
    return max(x, 0.0) ** (1 / g)


def rec709_oetf(x):
    return 4.5 * x if x < 0.018 else 1.099 * x ** 0.45 - 0.099


def make_transform(exposure=0.0, contrast_amt=0.0, sat=1.0, oetf="gamma24"):
    gain = 2 ** exposure
    enc = gamma_encode if oetf == "gamma24" else rec709_oetf

    def f(rgb):
        lin = mat(M_2020_TO_709, tuple(apple_log_to_linear(c) for c in rgb))
        lin = tuple(shoulder(max(c * gain, 0.0)) for c in lin)
        out = tuple(contrast(enc(c), contrast_amt) for c in lin)
        if sat != 1.0:
            l = 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]
            out = tuple(l + (c - l) * sat for c in out)
        return tuple(min(max(c, 0.0), 1.0) for c in out)

    return f


def write_cube(path, title, size, fn):
    with open(path, "w") as fh:
        fh.write(f'TITLE "{title}"\nLUT_3D_SIZE {size}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n')
        n = size - 1
        for b in range(size):          # .cube: R varia mas rapido, luego G, luego B
            for g in range(size):
                for r in range(size):
                    o = fn((r / n, g / n, b / n))
                    fh.write(f"{o[0]:.6f} {o[1]:.6f} {o[2]:.6f}\n")


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
