"""The two conditional answers that the references give as a method in words
(``method``) in place of a formula. Both follow the text of the reference
files, and the tests hold them to the files' worked examples."""

import math

# Kinematic viscosity of water in m²/s by temperature in °C, from standard
# tables (pipe-and-pump assumptions and the roughness method's note).
VISCOSITY = {5: 1.519e-6, 10: 1.307e-6, 15: 1.139e-6, 20: 1.004e-6, 25: 0.893e-6,
             30: 0.801e-6}
PIPE_LENGTH, BORE, VELOCITY, GRAVITY = 35.0, 0.040, 1.19366, 9.81
ITERATIONS = 100


def friction_head_straight_pipe(inputs):
    """Darcy-Weisbach with the Colebrook factor, for 35 m of the pipe."""
    viscosity = VISCOSITY.get(inputs["temperature_c"])
    roughness = inputs["roughness_mm"] / 1000 / BORE
    if viscosity is None or not 0 <= roughness < 0.1:
        raise ValueError("a temperature or roughness outside the reference tables")
    reynolds = VELOCITY * BORE / viscosity
    factor = 0.02
    for _ in range(ITERATIONS):
        factor = (-2 * math.log10(roughness / 3.7
                                  + 2.51 / (reynolds * math.sqrt(factor)))) ** -2
    return factor * PIPE_LENGTH / BORE * VELOCITY ** 2 / (2 * GRAVITY)


def ph_at_volume(inputs):
    """pH from the charge balance, by bisection on the hydrogen ion
    concentration between 1e-15 and 1."""
    base_ml, ka, kw = inputs["base_ml"], inputs["ka"], inputs["kw"]
    if not (0 <= base_ml <= 1000 and 0 < ka < 1 and 0 < kw < 1e-10):
        raise ValueError("a volume or constant outside the range of the method")
    total = 25.0 + base_ml
    sodium, acid = 0.100 * base_ml / total, 0.100 * 25.0 / total
    low, high = -15.0, 0.0          # log10 of the concentration
    for _ in range(ITERATIONS):
        middle = (low + high) / 2
        h = 10 ** middle
        if h + sodium - kw / h - acid * ka / (ka + h) < 0:
            low = middle
        else:
            high = middle
    return -(low + high) / 2


METHODS = {
    ("pipe-and-pump", "friction_head_straight_pipe"): friction_head_straight_pipe,
    ("titration-curve", "ph_at_volume"): ph_at_volume,
}
