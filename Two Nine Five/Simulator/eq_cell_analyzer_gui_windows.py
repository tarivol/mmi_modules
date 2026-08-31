#!/usr/bin/env python3
"""
EQ cell analyzer for Windows Python.

Backend / GUI stack:
    - tkinter (GUI)
    - matplotlib FigureCanvasTkAgg (plot embedding)

Features:
    * component entry fields
    * VR11 / VR12 sliders (0..100% of nominal values)
    * Bode magnitude and phase plots
    * numerical peak frequency / gain calculation
    * optimizer for R34, R35, C25, C26, C27 with fixed VR11/VR12 nominal
      values and fixed slider positions
    * component locking for optimizer
    * scrollable left-side control pane for smaller screens
    * selectable resistor/capacitor snap series (None, E6, E12, E24, E48, E96)

Model assumptions:
    R1 = R34
    C1 = C26
    C2 = C27
    C3 = C25
    R2 = R35 + VR11_eff
    R3 = VR12_eff
"""

from __future__ import annotations

import cmath
import math
import os
import random
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    import tkinter as tk
    from tkinter import ttk
except Exception as exc:
    raise SystemExit(f"tkinter is required to run this GUI: {exc}")

try:
    import matplotlib
    matplotlib.use("TkAgg", force=True)
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    from matplotlib.figure import Figure
except Exception as exc:
    raise SystemExit(f"matplotlib with TkAgg backend is required: {exc}")


def configure_windows_runtime() -> None:
    if os.name != 'nt':
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Parsing / formatting helpers
# -----------------------------------------------------------------------------

_ENG_RE = re.compile(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([pnumkMG]?)$")

_SERIES_TABLE: Dict[str, np.ndarray] = {
    'None': np.array([], dtype=float),
    'E6': np.array([1.0, 1.5, 2.2, 3.3, 4.7, 6.8], dtype=float),
    'E12': np.array([1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2], dtype=float),
    'E24': np.array([
        1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
        3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1,
    ], dtype=float),
    'E48': np.array([
        1.00, 1.05, 1.10, 1.15, 1.21, 1.27, 1.33, 1.40, 1.47, 1.54, 1.62, 1.69,
        1.78, 1.87, 1.96, 2.05, 2.15, 2.26, 2.37, 2.49, 2.61, 2.74, 2.87, 3.01,
        3.16, 3.32, 3.48, 3.65, 3.83, 4.02, 4.22, 4.42, 4.64, 4.87, 5.11, 5.36,
        5.62, 5.90, 6.19, 6.49, 6.81, 7.15, 7.50, 7.87, 8.25, 8.66, 9.09, 9.53,
    ], dtype=float),
    'E96': np.array([
        1.00, 1.02, 1.05, 1.07, 1.10, 1.13, 1.15, 1.18, 1.21, 1.24, 1.27, 1.30,
        1.33, 1.37, 1.40, 1.43, 1.47, 1.50, 1.54, 1.58, 1.62, 1.65, 1.69, 1.74,
        1.78, 1.82, 1.87, 1.91, 1.96, 2.00, 2.05, 2.10, 2.15, 2.21, 2.26, 2.32,
        2.37, 2.43, 2.49, 2.55, 2.61, 2.67, 2.74, 2.80, 2.87, 2.94, 3.01, 3.09,
        3.16, 3.24, 3.32, 3.40, 3.48, 3.57, 3.65, 3.74, 3.83, 3.92, 4.02, 4.12,
        4.22, 4.32, 4.42, 4.53, 4.64, 4.75, 4.87, 4.99, 5.11, 5.23, 5.36, 5.49,
        5.62, 5.76, 5.90, 6.04, 6.19, 6.34, 6.49, 6.65, 6.81, 6.98, 7.15, 7.32,
        7.50, 7.68, 7.87, 8.06, 8.25, 8.45, 8.66, 8.87, 9.09, 9.31, 9.53, 9.76,
    ], dtype=float),
}
_SERIES_OPTIONS = list(_SERIES_TABLE.keys())
_RESISTOR_NAMES = ['R34', 'R35']
_CAPACITOR_NAMES = ['C25', 'C26', 'C27']


def parse_eng_value(text: str) -> float:
    if text is None:
        raise ValueError("Missing value")
    s = text.strip()
    if not s:
        raise ValueError("Empty value")
    s = s.replace("Ω", "ohm").replace("µ", "u").replace("μ", "u")
    s = re.sub(r"(?i)(ohms?|farads?|farad|f)$", "", s).strip()
    m = _ENG_RE.fullmatch(s)
    if not m:
        raise ValueError(f"Cannot parse value: {text!r}")
    value = float(m.group(1))
    suffix = m.group(2)
    scale = {
        "": 1.0,
        "p": 1e-12,
        "n": 1e-9,
        "u": 1e-6,
        "m": 1e-3,
        "k": 1e3,
        "M": 1e6,
        "G": 1e9,
    }[suffix]
    return value * scale


def require_positive(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number, got {value!r}")


def format_eng(value: float, kind: str) -> str:
    if not math.isfinite(value):
        return str(value)
    if value == 0:
        return "0"
    if kind == 'R':
        units = [(1e9, 'GΩ'), (1e6, 'MΩ'), (1e3, 'kΩ'), (1.0, 'Ω'), (1e-3, 'mΩ')]
    elif kind == 'C':
        units = [(1.0, 'F'), (1e-3, 'mF'), (1e-6, 'uF'), (1e-9, 'nF'), (1e-12, 'pF')]
    elif kind == 'FREQ':
        units = [(1e9, 'GHz'), (1e6, 'MHz'), (1e3, 'kHz'), (1.0, 'Hz')]
    else:
        return f"{value:g}"
    aval = abs(value)
    for scale, suffix in units:
        if aval >= scale:
            return f"{value/scale:.6g} {suffix}"
    scale, suffix = units[-1]
    return f"{value/scale:.6g} {suffix}"


def format_token(value: float, kind: str) -> str:
    if not math.isfinite(value) or value <= 0:
        return str(value)
    if kind == 'R':
        units = [(1e9, 'G'), (1e6, 'M'), (1e3, 'k'), (1.0, ''), (1e-3, 'm')]
    elif kind == 'C':
        units = [(1.0, ''), (1e-3, 'm'), (1e-6, 'u'), (1e-9, 'n'), (1e-12, 'p')]
    elif kind == 'FREQ':
        units = [(1e9, 'G'), (1e6, 'M'), (1e3, 'k'), (1.0, '')]
    else:
        return f"{value:.6g}"
    aval = abs(value)
    for scale, suffix in units:
        if aval >= scale:
            return f"{value/scale:.6g}{suffix}"
    scale, suffix = units[-1]
    return f"{value/scale:.6g}{suffix}"


def snap_to_series(value: float, series_name: str) -> float:
    require_positive('value', value)
    series = _SERIES_TABLE.get(series_name)
    if series is None:
        raise ValueError(f"Unknown series: {series_name}")
    if series.size == 0:
        return value

    exponent = math.floor(math.log10(value))
    mantissa = value / (10 ** exponent)
    while mantissa < 1.0:
        mantissa *= 10.0
        exponent -= 1
    while mantissa >= 10.0:
        mantissa /= 10.0
        exponent += 1

    candidates = []
    for exp_shift in (-1, 0, 1):
        exp = exponent + exp_shift
        scale = 10 ** exp
        for base in series:
            candidates.append(float(base * scale))
    return min(candidates, key=lambda x: abs(math.log(x / value)))


# -----------------------------------------------------------------------------
# Electrical model
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class EQCellParams:
    R1: float
    R2: float
    R3: float
    C1: float
    C2: float
    C3: float

    @property
    def a(self) -> float:
        return self.C1 * (self.R2 + self.R3) + self.C3 * self.R3

    @property
    def b(self) -> float:
        return self.C3 * self.R3 * (self.C1 * (self.R1 + self.R2) + self.C2 * self.R1)

    @property
    def c(self) -> float:
        return self.R1 * (self.C1 + self.C2)

    @property
    def d(self) -> float:
        return self.C1 * self.C2 * self.R1 * (self.R2 + self.R3)

    @property
    def e(self) -> float:
        return self.C1 * self.C2 * self.C3 * self.R1 * self.R2 * self.R3

    @property
    def rough_fc_hz(self) -> float:
        if self.d <= 0:
            return float('nan')
        return 1.0 / (2.0 * math.pi * math.sqrt(self.d))


def H_of_jw(params: EQCellParams, freq_hz):
    w = 2.0 * math.pi * np.asarray(freq_hz, dtype=float)
    s = 1j * w
    num = -s * (params.a + params.b * s)
    den = 1.0 + params.c * s + params.d * (s ** 2) + params.e * (s ** 3)
    return num / den


def magnitude_db(H):
    mag = np.abs(H)
    with np.errstate(divide='ignore'):
        return 20.0 * np.log10(mag)


def phase_deg(H):
    return np.rad2deg(np.unwrap(np.angle(H)))


def golden_section_max(f, lo: float, hi: float, tol: float = 1e-12, max_iter: int = 200) -> Tuple[float, float]:
    invphi = (math.sqrt(5.0) - 1.0) / 2.0
    invphi2 = (3.0 - math.sqrt(5.0)) / 2.0
    a, b = lo, hi
    h = b - a
    if h <= tol:
        x = (a + b) / 2.0
        return x, f(x)
    c = a + invphi2 * h
    d = a + invphi * h
    yc = f(c)
    yd = f(d)
    for _ in range(max_iter):
        if abs(b - a) <= tol:
            break
        if yc > yd:
            b, d, yd = d, c, yc
            h = invphi * h
            c = a + invphi2 * h
            yc = f(c)
        else:
            a, c, yc = c, d, yd
            h = invphi * h
            d = a + invphi * h
            yd = f(d)
    x = (a + b) / 2.0
    return x, f(x)


def find_peak_frequency(params: EQCellParams, fmin: float, fmax: float, points_per_decade: int = 300) -> Tuple[float, complex]:
    require_positive('fmin', fmin)
    require_positive('fmax', fmax)
    if fmax <= fmin:
        raise ValueError('fmax must be greater than fmin')
    decades = math.log10(fmax) - math.log10(fmin)
    n = max(1000, int(decades * points_per_decade))
    freqs = np.logspace(math.log10(fmin), math.log10(fmax), num=n)
    H = H_of_jw(params, freqs)
    mags = np.abs(H)
    idx = int(np.argmax(mags))
    if idx == 0:
        left, right = freqs[0], freqs[1]
    elif idx == len(freqs) - 1:
        left, right = freqs[-2], freqs[-1]
    else:
        left, right = freqs[idx - 1], freqs[idx + 1]
    log_left = math.log10(left)
    log_right = math.log10(right)
    log_peak, _ = golden_section_max(lambda lf: abs(complex(H_of_jw(params, 10.0 ** lf))), log_left, log_right)
    f_peak = 10.0 ** log_peak
    return f_peak, complex(H_of_jw(params, f_peak))


def evaluate_peak_metrics(params: EQCellParams, fmin: float, fmax: float, points_per_decade: int = 220) -> Tuple[float, float, float]:
    f_peak, H_peak = find_peak_frequency(params, fmin, fmax, points_per_decade)
    gain_linear = abs(H_peak)
    gain_db = 20.0 * math.log10(gain_linear) if gain_linear > 0 else float('-inf')
    return f_peak, gain_linear, gain_db


# -----------------------------------------------------------------------------
# Optimizer
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ComponentSolution:
    R34: float
    R35: float
    C25: float
    C26: float
    C27: float
    fc_hz: float
    gain_linear: float
    gain_db: float
    score: float
    resistor_series: str = 'None'
    capacitor_series: str = 'None'


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


def _build_component_dict(solution: ComponentSolution) -> Dict[str, float]:
    return {
        'R34': solution.R34,
        'R35': solution.R35,
        'C25': solution.C25,
        'C26': solution.C26,
        'C27': solution.C27,
    }


def optimize_fixed_components(
    start_components: Dict[str, float],
    vr11_nom: float,
    vr12_nom: float,
    vr11_pct: float,
    vr12_pct: float,
    target_fc_hz: float,
    target_gain_db: float,
    fmin: float,
    fmax: float,
    locked_names: Sequence[str],
    search_low_mult: float = 0.25,
    search_high_mult: float = 4.0,
    random_samples: int = 400,
    points_per_decade: int = 220,
    seed: int = 12345,
) -> ComponentSolution:
    all_names = ['R34', 'R35', 'C25', 'C26', 'C27']
    locked_set = set(locked_names)
    free_names: List[str] = [name for name in all_names if name not in locked_set]

    for name in all_names:
        require_positive(name, start_components[name])
    for name, value in [
        ('vr11_nom', vr11_nom), ('vr12_nom', vr12_nom), ('target_fc_hz', target_fc_hz),
        ('fmin', fmin), ('fmax', fmax), ('search_low_mult', search_low_mult), ('search_high_mult', search_high_mult),
    ]:
        require_positive(name, value)
    if fmax <= fmin:
        raise ValueError('fmax must be greater than fmin')
    if search_high_mult <= search_low_mult:
        raise ValueError('search_high_mult must be greater than search_low_mult')
    if random_samples < 20:
        raise ValueError('random_samples must be >= 20')

    if not free_names:
        current_params = EQCellParams(
            R1=float(start_components['R34']),
            R2=float(start_components['R35'] + vr11_nom * _clamp(vr11_pct / 100.0, 0.0, 1.0)),
            R3=float(vr12_nom * _clamp(vr12_pct / 100.0, 0.0, 1.0)),
            C1=float(start_components['C26']),
            C2=float(start_components['C27']),
            C3=float(start_components['C25']),
        )
        fc_hz, gain_linear, gain_db = evaluate_peak_metrics(current_params, fmin, fmax, points_per_decade)
        freq_err = math.log(fc_hz / target_fc_hz)
        gain_err = (gain_db - target_gain_db) / 12.0
        score = freq_err * freq_err + gain_err * gain_err
        return ComponentSolution(
            R34=start_components['R34'], R35=start_components['R35'], C25=start_components['C25'],
            C26=start_components['C26'], C27=start_components['C27'],
            fc_hz=fc_hz, gain_linear=gain_linear, gain_db=gain_db, score=score,
            resistor_series='None', capacitor_series='None',
        )

    slider11 = _clamp(vr11_pct / 100.0, 0.0, 1.0)
    slider12 = _clamp(vr12_pct / 100.0, 0.0, 1.0)
    vr11_eff = vr11_nom * slider11
    vr12_eff = vr12_nom * slider12

    starts = np.array([start_components[name] for name in free_names], dtype=float)
    lows = starts * search_low_mult
    highs = starts * search_high_mult
    log_lows = np.log(lows)
    log_highs = np.log(highs)
    x0 = np.log(starts)
    span = max(math.log(search_high_mult / search_low_mult), 1e-6)
    rng = random.Random(seed)

    def component_map_from_x(x: np.ndarray) -> Dict[str, float]:
        values = dict(start_components)
        vals = np.exp(np.minimum(np.maximum(x, log_lows), log_highs))
        for i, name in enumerate(free_names):
            values[name] = float(vals[i])
        return values

    def params_from_components(values: Dict[str, float]) -> EQCellParams:
        return EQCellParams(
            R1=float(values['R34']),
            R2=float(values['R35'] + vr11_eff),
            R3=float(vr12_eff),
            C1=float(values['C26']),
            C2=float(values['C27']),
            C3=float(values['C25']),
        )

    def score_x(x: np.ndarray) -> Tuple[float, float, float, float]:
        values = component_map_from_x(x)
        params = params_from_components(values)
        fc_hz, gain_linear, gain_db = evaluate_peak_metrics(params, fmin, fmax, points_per_decade)
        freq_err = math.log(fc_hz / target_fc_hz)
        gain_err = (gain_db - target_gain_db) / 12.0
        regularization = 0.02 * float(np.mean(((x - x0) / span) ** 2))
        score = freq_err * freq_err + gain_err * gain_err + regularization
        return score, fc_hz, gain_linear, gain_db

    candidates = [x0.copy(), 0.5 * (log_lows + log_highs)]
    for _ in range(random_samples):
        candidates.append(np.array([rng.uniform(lo, hi) for lo, hi in zip(log_lows, log_highs)], dtype=float))

    best = None
    for cand in candidates:
        try:
            result = score_x(cand)
        except Exception:
            continue
        if best is None or result[0] < best[0]:
            best = (result[0], cand.copy(), result[1], result[2], result[3])

    if best is None:
        raise RuntimeError('Optimization failed to find any valid candidate')

    best_score, best_x, best_fc, best_gain_lin, best_gain_db = best
    step = max(0.55 * (log_highs - log_lows).mean(), 0.06)
    no_improve = 0

    while step > 0.003 and no_improve < 8:
        improved = False
        for idx in range(len(free_names)):
            for direction in (-1.0, 1.0):
                trial = best_x.copy()
                trial[idx] = _clamp(trial[idx] + direction * step, log_lows[idx], log_highs[idx])
                try:
                    score, fc_hz, gain_lin, gain_db = score_x(trial)
                except Exception:
                    continue
                if score < best_score:
                    best_score, best_x, best_fc, best_gain_lin, best_gain_db = score, trial.copy(), fc_hz, gain_lin, gain_db
                    improved = True
        for _ in range(6):
            signs = np.array([rng.choice([-1.0, 1.0]) for _ in free_names], dtype=float)
            trial = np.minimum(np.maximum(best_x + 0.45 * step * signs, log_lows), log_highs)
            try:
                score, fc_hz, gain_lin, gain_db = score_x(trial)
            except Exception:
                continue
            if score < best_score:
                best_score, best_x, best_fc, best_gain_lin, best_gain_db = score, trial.copy(), fc_hz, gain_lin, gain_db
                improved = True
        if improved:
            no_improve = 0
            step *= 0.78
        else:
            no_improve += 1
            step *= 0.55

    final_values = component_map_from_x(best_x)
    return ComponentSolution(
        R34=final_values['R34'], R35=final_values['R35'], C25=final_values['C25'],
        C26=final_values['C26'], C27=final_values['C27'],
        fc_hz=float(best_fc), gain_linear=float(best_gain_lin), gain_db=float(best_gain_db), score=float(best_score),
        resistor_series='None', capacitor_series='None',
    )


def evaluate_solution_components(
    values: Dict[str, float],
    vr11_nom: float,
    vr12_nom: float,
    vr11_pct: float,
    vr12_pct: float,
    fmin: float,
    fmax: float,
    points_per_decade: int,
) -> Tuple[float, float, float]:
    params = EQCellParams(
        R1=float(values['R34']),
        R2=float(values['R35'] + vr11_nom * _clamp(vr11_pct / 100.0, 0.0, 1.0)),
        R3=float(vr12_nom * _clamp(vr12_pct / 100.0, 0.0, 1.0)),
        C1=float(values['C26']),
        C2=float(values['C27']),
        C3=float(values['C25']),
    )
    return evaluate_peak_metrics(params, fmin, fmax, points_per_decade)


def score_solution(target_fc_hz: float, target_gain_db: float, achieved_fc_hz: float, achieved_gain_db: float) -> float:
    freq_err = math.log(achieved_fc_hz / target_fc_hz)
    gain_err = (achieved_gain_db - target_gain_db) / 12.0
    return freq_err * freq_err + gain_err * gain_err


def snap_solution_to_selected_series(
    solution: ComponentSolution,
    locked_names: Sequence[str],
    resistor_series: str,
    capacitor_series: str,
    vr11_nom: float,
    vr12_nom: float,
    vr11_pct: float,
    vr12_pct: float,
    target_fc_hz: float,
    target_gain_db: float,
    fmin: float,
    fmax: float,
    points_per_decade: int,
) -> ComponentSolution:
    values = _build_component_dict(solution)
    locked = set(locked_names)

    for name in _RESISTOR_NAMES:
        if name not in locked:
            values[name] = snap_to_series(values[name], resistor_series)
    for name in _CAPACITOR_NAMES:
        if name not in locked:
            values[name] = snap_to_series(values[name], capacitor_series)

    achieved_fc, achieved_gain_lin, achieved_gain_db = evaluate_solution_components(
        values, vr11_nom, vr12_nom, vr11_pct, vr12_pct, fmin, fmax, points_per_decade
    )
    score = score_solution(target_fc_hz, target_gain_db, achieved_fc, achieved_gain_db)
    return ComponentSolution(
        R34=values['R34'], R35=values['R35'], C25=values['C25'], C26=values['C26'], C27=values['C27'],
        fc_hz=achieved_fc, gain_linear=achieved_gain_lin, gain_db=achieved_gain_db, score=score,
        resistor_series=resistor_series, capacitor_series=capacitor_series,
    )


# -----------------------------------------------------------------------------
# GUI helpers
# -----------------------------------------------------------------------------

class ScrollableFrame(ttk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.v_scroll = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        self.canvas.configure(yscrollcommand=self.v_scroll.set)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.v_scroll.grid(row=0, column=1, sticky='ns')
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.inner.bind('<Configure>', self._on_inner_configure)
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        self.canvas.bind('<Enter>', self._bind_mousewheel)
        self.canvas.bind('<Leave>', self._unbind_mousewheel)

    def _on_inner_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _on_mousewheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-event.delta / 120), 'units')
        else:
            if getattr(event, 'num', None) == 4:
                self.canvas.yview_scroll(-1, 'units')
            elif getattr(event, 'num', None) == 5:
                self.canvas.yview_scroll(1, 'units')

    def _bind_mousewheel(self, _event=None):
        self.canvas.bind_all('<MouseWheel>', self._on_mousewheel)
        self.canvas.bind_all('<Button-4>', self._on_mousewheel)
        self.canvas.bind_all('<Button-5>', self._on_mousewheel)

    def _unbind_mousewheel(self, _event=None):
        self.canvas.unbind_all('<MouseWheel>')
        self.canvas.unbind_all('<Button-4>')
        self.canvas.unbind_all('<Button-5>')


# -----------------------------------------------------------------------------
# GUI
# -----------------------------------------------------------------------------

class EQCellAnalyzerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title('EQ Cell Analyzer (Windows Tkinter)')
        self.root.geometry('1500x980')
        self.last_optimized_solution: Optional[ComponentSolution] = None
        self._build_style()
        self._build_layout()
        self._set_defaults()
        self.update_analysis()

    def _build_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('TLabelframe', padding=8)
        style.configure('TButton', padding=6)
        style.configure('Header.TLabel', font=('TkDefaultFont', 11, 'bold'))
        style.configure('Value.TLabel', font=('TkDefaultFont', 10, 'bold'))

    def _build_layout(self):
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        controls_outer = ScrollableFrame(self.root)
        controls_outer.grid(row=0, column=0, sticky='nsw')
        controls = controls_outer.inner

        plot_frame = ttk.Frame(self.root, padding=8)
        plot_frame.grid(row=0, column=1, sticky='nsew')
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(1, weight=1)

        row = 0
        comp_frame = ttk.LabelFrame(controls, text='Component values')
        comp_frame.grid(row=row, column=0, sticky='new', padx=6, pady=4)
        comp_frame.columnconfigure(1, weight=1)
        self.entries: Dict[str, tk.StringVar] = {}
        main_fields = [
            ('R34', '15k'), ('R35', '150k'), ('C25', '4.7n'), ('C26', '910p'), ('C27', '47n'),
            ('VR11_nom', '100k'), ('VR12_nom', '20k'), ('fmin', '10'), ('fmax', '100k'), ('points_per_decade', '300'),
        ]
        for idx, (name, default) in enumerate(main_fields):
            ttk.Label(comp_frame, text=name).grid(row=idx, column=0, sticky='w', padx=(0, 8), pady=2)
            var = tk.StringVar(value=default)
            entry = ttk.Entry(comp_frame, textvariable=var, width=18)
            entry.grid(row=idx, column=1, sticky='ew', pady=2)
            entry.bind('<Return>', lambda _e: self.update_analysis())
            self.entries[name] = var

        row += 1
        slider_frame = ttk.LabelFrame(controls, text='Rheostat positions')
        slider_frame.grid(row=row, column=0, sticky='new', padx=6, pady=4)
        slider_frame.columnconfigure(0, weight=1)
        self.vr11_pct = tk.DoubleVar(value=50.0)
        self.vr12_pct = tk.DoubleVar(value=50.0)
        ttk.Label(slider_frame, text='VR11 position (% of nominal), added in series with R35').grid(row=0, column=0, sticky='w')
        ttk.Scale(slider_frame, from_=0.0, to=100.0, variable=self.vr11_pct, command=self._on_slider).grid(row=1, column=0, sticky='ew', pady=(2, 6))
        self.vr11_value_label = ttk.Label(slider_frame, text='')
        self.vr11_value_label.grid(row=2, column=0, sticky='w', pady=(0, 6))
        ttk.Label(slider_frame, text='VR12 position (% of nominal), used as output rheostat').grid(row=3, column=0, sticky='w')
        ttk.Scale(slider_frame, from_=0.0, to=100.0, variable=self.vr12_pct, command=self._on_slider).grid(row=4, column=0, sticky='ew', pady=(2, 6))
        self.vr12_value_label = ttk.Label(slider_frame, text='')
        self.vr12_value_label.grid(row=5, column=0, sticky='w')

        row += 1
        result_frame = ttk.LabelFrame(controls, text='Current response')
        result_frame.grid(row=row, column=0, sticky='new', padx=6, pady=4)
        result_frame.columnconfigure(1, weight=1)
        self.result_vars = {k: tk.StringVar(value='-') for k in ['R2_eff', 'R3_eff', 'fc_exact', 'gain_peak_linear', 'gain_peak_db', 'phase_peak', 'fc_rough']}
        result_labels = [
            ('R2 effective', 'R2_eff'), ('R3 effective', 'R3_eff'), ('Peak / center frequency', 'fc_exact'),
            ('Peak gain (linear)', 'gain_peak_linear'), ('Peak gain (dB)', 'gain_peak_db'),
            ('Phase at peak', 'phase_peak'), ('Rough f_c', 'fc_rough'),
        ]
        for idx, (label, key) in enumerate(result_labels):
            ttk.Label(result_frame, text=label).grid(row=idx, column=0, sticky='w', padx=(0, 8), pady=1)
            ttk.Label(result_frame, textvariable=self.result_vars[key], style='Value.TLabel').grid(row=idx, column=1, sticky='w', pady=1)

        row += 1
        snap_frame = ttk.LabelFrame(controls, text='Optimizer locks and snapping')
        snap_frame.grid(row=row, column=0, sticky='new', padx=6, pady=4)
        snap_frame.columnconfigure(1, weight=1)
        self.lock_vars = {name: tk.BooleanVar(value=False) for name in ['R34', 'R35', 'C25', 'C26', 'C27']}
        ttk.Label(snap_frame, text='Locked components stay fixed during optimization.').grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 6))
        ck_container = ttk.Frame(snap_frame)
        ck_container.grid(row=1, column=0, columnspan=2, sticky='w')
        for idx, name in enumerate(['R34', 'R35', 'C25', 'C26', 'C27']):
            ttk.Checkbutton(ck_container, text=f'Lock {name}', variable=self.lock_vars[name]).grid(row=idx // 2, column=idx % 2, sticky='w', padx=(0, 18), pady=2)

        self.resistor_series_var = tk.StringVar(value='E24')
        self.capacitor_series_var = tk.StringVar(value='E24')
        ttk.Label(snap_frame, text='Resistor snap series').grid(row=2, column=0, sticky='w', pady=(10, 2))
        r_combo = ttk.Combobox(snap_frame, textvariable=self.resistor_series_var, values=_SERIES_OPTIONS, width=12, state='readonly')
        r_combo.grid(row=2, column=1, sticky='w', pady=(10, 2))
        ttk.Label(snap_frame, text='Capacitor snap series').grid(row=3, column=0, sticky='w', pady=2)
        c_combo = ttk.Combobox(snap_frame, textvariable=self.capacitor_series_var, values=_SERIES_OPTIONS, width=12, state='readonly')
        c_combo.grid(row=3, column=1, sticky='w', pady=2)
        ttk.Label(snap_frame, text='Choose "None" to disable snapping for that component type.').grid(row=4, column=0, columnspan=2, sticky='w', pady=(6, 0))

        row += 1
        opt_frame = ttk.LabelFrame(controls, text='Optimizer')
        opt_frame.grid(row=row, column=0, sticky='new', padx=6, pady=4)
        opt_frame.columnconfigure(1, weight=1)
        self.opt_entries: Dict[str, tk.StringVar] = {}
        opt_fields = [
            ('target_fc', '1k', 'Target center/peak frequency'),
            ('target_gain_db', '-6', 'Target peak gain [dB]'),
            ('search_low_mult', '0.25', 'Lower multiplier around current component values'),
            ('search_high_mult', '4.0', 'Upper multiplier around current component values'),
            ('random_samples', '450', 'Random candidate count'),
        ]
        for idx, (key, default, label) in enumerate(opt_fields):
            ttk.Label(opt_frame, text=label).grid(row=idx, column=0, sticky='w', padx=(0, 8), pady=2)
            var = tk.StringVar(value=default)
            entry = ttk.Entry(opt_frame, textvariable=var, width=18)
            entry.grid(row=idx, column=1, sticky='ew', pady=2)
            entry.bind('<Return>', lambda _e: self.optimize_components())
            self.opt_entries[key] = var
        ttk.Button(opt_frame, text='Optimize components', command=self.optimize_components).grid(row=5, column=0, columnspan=2, sticky='ew', pady=(8, 4))
        ttk.Button(opt_frame, text='Apply optimized values', command=self.apply_optimized_values).grid(row=6, column=0, columnspan=2, sticky='ew', pady=(0, 4))
        self.optimizer_status = tk.StringVar(value='No optimization run yet.')
        ttk.Label(opt_frame, textvariable=self.optimizer_status, wraplength=390, justify='left').grid(row=7, column=0, columnspan=2, sticky='w', pady=(4, 2))
        self.opt_result_vars = {k: tk.StringVar(value='-') for k in ['R34', 'R35', 'C25', 'C26', 'C27', 'fc', 'gain_db', 'score', 'series']}
        opt_grid = ttk.Frame(opt_frame)
        opt_grid.grid(row=8, column=0, columnspan=2, sticky='ew', pady=(4, 0))
        for idx, (label, key) in enumerate([
            ('R34', 'R34'), ('R35', 'R35'), ('C25', 'C25'), ('C26', 'C26'), ('C27', 'C27'),
            ('Achieved f_peak', 'fc'), ('Achieved gain', 'gain_db'), ('Score', 'score'), ('Applied series', 'series'),
        ]):
            ttk.Label(opt_grid, text=label).grid(row=idx, column=0, sticky='w', padx=(0, 8), pady=1)
            ttk.Label(opt_grid, textvariable=self.opt_result_vars[key], style='Value.TLabel').grid(row=idx, column=1, sticky='w', pady=1)

        row += 1
        btn_frame = ttk.Frame(controls)
        btn_frame.grid(row=row, column=0, sticky='ew', padx=6, pady=8)
        ttk.Button(btn_frame, text='Update plot', command=self.update_analysis).grid(row=0, column=0, sticky='ew')
        ttk.Button(btn_frame, text='Reset defaults', command=self._set_defaults).grid(row=1, column=0, sticky='ew', pady=(6, 0))
        ttk.Button(btn_frame, text='Quit', command=self.root.destroy).grid(row=2, column=0, sticky='ew', pady=(6, 0))

        row += 1
        note_frame = ttk.LabelFrame(controls, text='Notes')
        note_frame.grid(row=row, column=0, sticky='new', padx=6, pady=4)
        note = (
            'Enter values like 15k, 100k, 910p, 4.7n, 0.047u.\n'
            'VR11 slider = 0..100% of VR11 nominal value, then R2 = R35 + VR11_eff.\n'
            'VR12 slider = 0..100% of VR12 nominal value, then R3 = VR12_eff.\n'
            'Lock any of R34, R35, C25, C26, C27 to keep them fixed during optimization.\n'
            'Select separate snap series for resistors and capacitors; choose None to disable snapping.\n'
            'Windows: run this script with:  py eq_cell_analyzer_gui_windows.py'
        )
        ttk.Label(note_frame, text=note, justify='left', wraplength=390).grid(row=0, column=0, sticky='w')

        ttk.Label(plot_frame, text='Bode Plot', style='Header.TLabel').grid(row=0, column=0, sticky='w', pady=(0, 4))
        self.figure = Figure(figsize=(9.2, 7.4), dpi=100)
        self.ax_mag = self.figure.add_subplot(211)
        self.ax_phase = self.figure.add_subplot(212, sharex=self.ax_mag)
        self.figure.tight_layout(pad=2.4)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky='nsew')
        toolbar = NavigationToolbar2Tk(self.canvas, plot_frame, pack_toolbar=False)
        toolbar.update()
        toolbar.grid(row=2, column=0, sticky='ew')

    def _set_defaults(self):
        defaults = {
            'R34': '15k', 'R35': '150k', 'C25': '4.7n', 'C26': '910p', 'C27': '47n',
            'VR11_nom': '100k', 'VR12_nom': '20k', 'fmin': '10', 'fmax': '100k', 'points_per_decade': '300',
        }
        for key, value in defaults.items():
            self.entries[key].set(value)
        opt_defaults = {'target_fc': '1k', 'target_gain_db': '-6', 'search_low_mult': '0.25', 'search_high_mult': '4.0', 'random_samples': '450'}
        for key, value in opt_defaults.items():
            self.opt_entries[key].set(value)
        for var in self.lock_vars.values():
            var.set(False)
        self.resistor_series_var.set('E24')
        self.capacitor_series_var.set('E24')
        self.vr11_pct.set(50.0)
        self.vr12_pct.set(50.0)
        self.last_optimized_solution = None
        self.optimizer_status.set('No optimization run yet.')
        for var in self.opt_result_vars.values():
            var.set('-')
        self._refresh_slider_labels()
        if hasattr(self, 'canvas'):
            self.update_analysis()

    def _on_slider(self, _value=None):
        self._refresh_slider_labels()
        self.update_analysis()

    def _refresh_slider_labels(self):
        try:
            vr11_nom = parse_eng_value(self.entries['VR11_nom'].get())
            vr12_nom = parse_eng_value(self.entries['VR12_nom'].get())
            vr11_eff = vr11_nom * self.vr11_pct.get() / 100.0
            vr12_eff = vr12_nom * self.vr12_pct.get() / 100.0
            self.vr11_value_label.configure(text=f"VR11 effective: {format_eng(vr11_eff, 'R')}  ({self.vr11_pct.get():.1f}%)")
            self.vr12_value_label.configure(text=f"VR12 effective: {format_eng(vr12_eff, 'R')}  ({self.vr12_pct.get():.1f}%)")
        except Exception:
            self.vr11_value_label.configure(text='VR11 effective: invalid nominal value')
            self.vr12_value_label.configure(text='VR12 effective: invalid nominal value')

    def _read_params(self):
        R34 = parse_eng_value(self.entries['R34'].get())
        R35 = parse_eng_value(self.entries['R35'].get())
        C25 = parse_eng_value(self.entries['C25'].get())
        C26 = parse_eng_value(self.entries['C26'].get())
        C27 = parse_eng_value(self.entries['C27'].get())
        VR11_nom = parse_eng_value(self.entries['VR11_nom'].get())
        VR12_nom = parse_eng_value(self.entries['VR12_nom'].get())
        fmin = parse_eng_value(self.entries['fmin'].get())
        fmax = parse_eng_value(self.entries['fmax'].get())
        ppd = int(float(self.entries['points_per_decade'].get()))
        for name, value in [('R34', R34), ('R35', R35), ('C25', C25), ('C26', C26), ('C27', C27), ('VR11_nom', VR11_nom), ('VR12_nom', VR12_nom), ('fmin', fmin), ('fmax', fmax)]:
            require_positive(name, value)
        if fmax <= fmin:
            raise ValueError('fmax must be greater than fmin')
        if ppd < 20:
            raise ValueError('points_per_decade must be >= 20')
        vr11_eff = VR11_nom * self.vr11_pct.get() / 100.0
        vr12_eff = VR12_nom * self.vr12_pct.get() / 100.0
        params = EQCellParams(R1=R34, R2=R35 + vr11_eff, R3=vr12_eff, C1=C26, C2=C27, C3=C25)
        return params, VR11_nom, VR12_nom, fmin, fmax, ppd

    def _current_component_values(self) -> Dict[str, float]:
        return {
            'R34': parse_eng_value(self.entries['R34'].get()),
            'R35': parse_eng_value(self.entries['R35'].get()),
            'C25': parse_eng_value(self.entries['C25'].get()),
            'C26': parse_eng_value(self.entries['C26'].get()),
            'C27': parse_eng_value(self.entries['C27'].get()),
        }

    def _locked_names(self) -> List[str]:
        return [name for name, var in self.lock_vars.items() if var.get()]

    def update_analysis(self):
        try:
            params, _, _, fmin, fmax, ppd = self._read_params()
            f_peak, H_peak = find_peak_frequency(params, fmin, fmax, ppd)
            peak_gain = abs(H_peak)
            peak_db = 20.0 * math.log10(peak_gain) if peak_gain > 0 else float('-inf')
            peak_phase = math.degrees(cmath.phase(H_peak))
            self.result_vars['R2_eff'].set(format_eng(params.R2, 'R'))
            self.result_vars['R3_eff'].set(format_eng(params.R3, 'R'))
            self.result_vars['fc_exact'].set(format_eng(f_peak, 'FREQ'))
            self.result_vars['gain_peak_linear'].set(f'{peak_gain:.6g}')
            self.result_vars['gain_peak_db'].set(f'{peak_db:.6f} dB')
            self.result_vars['phase_peak'].set(f'{peak_phase:.4f}°')
            self.result_vars['fc_rough'].set(format_eng(params.rough_fc_hz, 'FREQ'))
            self._draw_bode(params, fmin, fmax, ppd, f_peak, peak_db)
            self._refresh_slider_labels()
        except Exception as exc:
            for v in self.result_vars.values():
                v.set('-')
            self.ax_mag.clear(); self.ax_phase.clear()
            self.ax_mag.text(0.02, 0.5, f'Input / calculation error:\n{exc}', transform=self.ax_mag.transAxes, ha='left', va='center', fontsize=11)
            self.ax_mag.set_axis_off(); self.ax_phase.set_axis_off()
            self.canvas.draw_idle()

    def _draw_bode(self, params: EQCellParams, fmin: float, fmax: float, ppd: int, f_peak: float, peak_db: float):
        decades = math.log10(fmax) - math.log10(fmin)
        n = max(1000, int(decades * ppd))
        freqs = np.logspace(math.log10(fmin), math.log10(fmax), num=n)
        H = H_of_jw(params, freqs)
        mag = magnitude_db(H)
        ph = phase_deg(H)
        self.ax_mag.clear(); self.ax_phase.clear()
        self.ax_mag.set_axis_on(); self.ax_phase.set_axis_on()
        self.ax_mag.semilogx(freqs, mag, linewidth=1.8)
        self.ax_phase.semilogx(freqs, ph, linewidth=1.5)
        self.ax_mag.axvline(f_peak, linestyle='--', linewidth=1.0)
        self.ax_mag.axhline(peak_db, linestyle=':', linewidth=1.0)
        self.ax_phase.axvline(f_peak, linestyle='--', linewidth=1.0)
        self.ax_mag.set_title('Magnitude')
        self.ax_mag.set_ylabel('Gain [dB]')
        self.ax_mag.grid(True, which='both')
        self.ax_phase.set_title('Phase')
        self.ax_phase.set_xlabel('Frequency [Hz]')
        self.ax_phase.set_ylabel('Phase [deg]')
        self.ax_phase.grid(True, which='both')
        info = f"Peak = {format_eng(f_peak, 'FREQ')}\nGain = {peak_db:.3f} dB\nR2 = {format_eng(params.R2, 'R')}\nR3 = {format_eng(params.R3, 'R')}"
        self.ax_mag.text(0.02, 0.98, info, transform=self.ax_mag.transAxes, va='top', ha='left', bbox=dict(boxstyle='round', facecolor='white', alpha=0.85))
        self.figure.tight_layout(pad=2.0)
        self.canvas.draw_idle()

    def optimize_components(self):
        try:
            _, vr11_nom, vr12_nom, fmin, fmax, ppd = self._read_params()
            target_fc = parse_eng_value(self.opt_entries['target_fc'].get())
            target_gain_db = float(self.opt_entries['target_gain_db'].get())
            search_low_mult = float(self.opt_entries['search_low_mult'].get())
            search_high_mult = float(self.opt_entries['search_high_mult'].get())
            random_samples = int(float(self.opt_entries['random_samples'].get()))
            require_positive('target_fc', target_fc)
            require_positive('search_low_mult', search_low_mult)
            require_positive('search_high_mult', search_high_mult)
            if search_high_mult <= search_low_mult:
                raise ValueError('search_high_mult must be greater than search_low_mult')
            if random_samples < 20:
                raise ValueError('random_samples must be >= 20')

            resistor_series = self.resistor_series_var.get()
            capacitor_series = self.capacitor_series_var.get()
            if resistor_series not in _SERIES_TABLE:
                raise ValueError('Invalid resistor series selection')
            if capacitor_series not in _SERIES_TABLE:
                raise ValueError('Invalid capacitor series selection')

            start_components = self._current_component_values()
            locked_names = self._locked_names()
            self.optimizer_status.set('Optimization running... please wait.')
            self.root.update_idletasks()

            solution = optimize_fixed_components(
                start_components=start_components,
                vr11_nom=vr11_nom,
                vr12_nom=vr12_nom,
                vr11_pct=self.vr11_pct.get(),
                vr12_pct=self.vr12_pct.get(),
                target_fc_hz=target_fc,
                target_gain_db=target_gain_db,
                fmin=fmin,
                fmax=fmax,
                locked_names=locked_names,
                search_low_mult=search_low_mult,
                search_high_mult=search_high_mult,
                random_samples=random_samples,
                points_per_decade=max(120, min(ppd, 260)),
            )

            if resistor_series != 'None' or capacitor_series != 'None':
                solution = snap_solution_to_selected_series(
                    solution=solution,
                    locked_names=locked_names,
                    resistor_series=resistor_series,
                    capacitor_series=capacitor_series,
                    vr11_nom=vr11_nom,
                    vr12_nom=vr12_nom,
                    vr11_pct=self.vr11_pct.get(),
                    vr12_pct=self.vr12_pct.get(),
                    target_fc_hz=target_fc,
                    target_gain_db=target_gain_db,
                    fmin=fmin,
                    fmax=fmax,
                    points_per_decade=max(120, min(ppd, 260)),
                )
            else:
                solution = ComponentSolution(
                    R34=solution.R34, R35=solution.R35, C25=solution.C25, C26=solution.C26, C27=solution.C27,
                    fc_hz=solution.fc_hz, gain_linear=solution.gain_linear, gain_db=solution.gain_db, score=solution.score,
                    resistor_series='None', capacitor_series='None',
                )

            self.last_optimized_solution = solution
            self.opt_result_vars['R34'].set(format_eng(solution.R34, 'R'))
            self.opt_result_vars['R35'].set(format_eng(solution.R35, 'R'))
            self.opt_result_vars['C25'].set(format_eng(solution.C25, 'C'))
            self.opt_result_vars['C26'].set(format_eng(solution.C26, 'C'))
            self.opt_result_vars['C27'].set(format_eng(solution.C27, 'C'))
            self.opt_result_vars['fc'].set(format_eng(solution.fc_hz, 'FREQ'))
            self.opt_result_vars['gain_db'].set(f'{solution.gain_db:.4f} dB')
            self.opt_result_vars['score'].set(f'{solution.score:.6g}')
            self.opt_result_vars['series'].set(f"R: {solution.resistor_series} | C: {solution.capacitor_series}")

            locked_text = ', '.join(locked_names) if locked_names else 'none'
            freq_pct_err = 100.0 * (solution.fc_hz / target_fc - 1.0)
            gain_err_db = solution.gain_db - target_gain_db
            self.optimizer_status.set(
                f'Optimization complete. Locked: {locked_text}. '
                f'Series -> R: {solution.resistor_series}, C: {solution.capacitor_series}. '
                f'Frequency error = {freq_pct_err:+.3f}% | Gain error = {gain_err_db:+.3f} dB. '
                'Click "Apply optimized values" to load them.'
            )
        except Exception as exc:
            self.last_optimized_solution = None
            for v in self.opt_result_vars.values():
                v.set('-')
            self.optimizer_status.set(f'Optimization error: {exc}')

    def apply_optimized_values(self):
        sol = self.last_optimized_solution
        if sol is None:
            self.optimizer_status.set('Nothing to apply yet. Run optimization first.')
            return
        self.entries['R34'].set(format_token(sol.R34, 'R'))
        self.entries['R35'].set(format_token(sol.R35, 'R'))
        self.entries['C25'].set(format_token(sol.C25, 'C'))
        self.entries['C26'].set(format_token(sol.C26, 'C'))
        self.entries['C27'].set(format_token(sol.C27, 'C'))
        self.update_analysis()
        self.optimizer_status.set('Optimized values applied to R34, R35, C25, C26, and C27.')


def main() -> int:
    configure_windows_runtime()
    root = tk.Tk()
    EQCellAnalyzerApp(root)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
