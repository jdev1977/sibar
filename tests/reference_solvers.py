"""Recomputes the math and engineering reference answers from the givens (T2.3).

Plain Python with no third-party package. Each ``solve_*`` function takes no
argument, holds its task's givens as written in the prompts, and returns a
mapping of quantity id to value. An accepted alternative is keyed
``"<quantity id>@<alternative id>"``. tests/test_reference_solutions.py
compares every number in checker/references/ with these.

The functions under "Conditional answers" take the choices a model states
(a motor speed, a roughness, a screw spacing) and return the answer that
follows. They are written separately from the formula text in the reference
files, so a slip in either one shows up as a difference.

These are study data, not designs.
"""

import math
from decimal import ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction
from itertools import product

# --- shared numerics ----------------------------------------------------------


def student_t_two_sided_p(t, df):
    """Two-sided p-value of Student's t, by Simpson's rule on the density."""
    c = math.gamma((df + 1) / 2) / (math.sqrt(df * math.pi) * math.gamma(df / 2))

    def density(u):
        return c * (1 + u * u / df) ** (-(df + 1) / 2)

    steps = 20000
    width = abs(t) / steps
    total = density(0) + density(abs(t))
    total += sum((4 if j % 2 else 2) * density(j * width) for j in range(1, steps))
    return 1 - 2 * total * width / 3


def student_t_two_sided_p_closed_form(t, df):
    """The same p-value from the closed form for an odd number of degrees
    of freedom above 1 (a finite sum of powers of a cosine)."""
    assert df % 2 == 1 and df > 1
    angle = math.atan(abs(t) / math.sqrt(df))
    cosine = math.cos(angle)
    term, total = cosine, cosine
    for j in range(1, (df - 1) // 2):
        term *= 2 * j / (2 * j + 1) * cosine ** 2
        total += term
    return 1 - 2 / math.pi * (angle + math.sin(angle) * total)


def student_t_critical(df, two_sided_level):
    """The t with the given two-sided tail area (0.05 gives the 97.5% point)."""
    low, high = 0.0, 50.0
    for _ in range(80):
        mid = (low + high) / 2
        if student_t_two_sided_p(mid, df) > two_sided_level:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def normal_two_sided_p(z):
    return math.erfc(abs(z) / math.sqrt(2))


# --- math: loan amortization --------------------------------------------------

CENT = Decimal("0.01")


def loan_schedule(round_interest):
    """The L2 schedule: payment 178.21, the last payment clears the balance.

    ``round_interest`` true rounds each month's interest to the cent before
    it is applied (the reference convention); false carries exact interest
    and rounds only the last payment.
    """
    with localcontext() as context:
        context.prec = 50
        balance = Decimal(9000)
        rate = Decimal(7) / Decimal(100) / Decimal(12)
        payment = loan_payment_exact().quantize(CENT, ROUND_HALF_UP)
        rows = []
        for month in range(1, 61):
            interest = balance * rate
            if round_interest:
                interest = interest.quantize(CENT, ROUND_HALF_UP)
            paid = payment
            if month == 60:
                paid = (balance + interest).quantize(CENT, ROUND_HALF_UP)
            principal = paid - interest
            balance = balance - principal
            rows.append((month, paid, interest, principal, balance))
        return rows


def loan_payment_exact(monthly_rate=None):
    with localcontext() as context:
        context.prec = 50
        rate = Decimal(7) / Decimal(100) / Decimal(12) if monthly_rate is None else monthly_rate
        return Decimal(9000) * rate / (1 - (1 + rate) ** -60)


def solve_loan_amortization():
    with localcontext() as context:
        context.prec = 50
        exact = loan_payment_exact()
        effective_rate = (Decimal(107) / Decimal(100)) ** (Decimal(1) / Decimal(12)) - 1
        effective = loan_payment_exact(effective_rate)
        rows = loan_schedule(round_interest=True)
        exact_rows = loan_schedule(round_interest=False)
        paid = sum(row[1] for row in rows)
        # Month-by-month check of the payment: with exact arithmetic 178.21
        # leaves a little owed after 60 payments and 178.22 overpays.
        left = {}
        for cents in ("178.21", "178.22"):
            balance = Decimal(9000)
            for _ in range(60):
                balance = balance * (1 + Decimal(7) / Decimal(1200)) - Decimal(cents)
            left[cents] = balance
        assert left["178.21"] > 0 > left["178.22"]
        # Both interest conventions give the same last payment here.
        assert exact_rows[-1][1] == rows[-1][1]
        assert sum(row[1] for row in exact_rows) == paid
        return {
            "payment_count": 60,
            "monthly_rate_percent": float(Decimal(7) / Decimal(12)),
            "monthly_payment": float(exact),
            "monthly_payment@effective_annual_rate": float(effective),
            "total_interest": float(exact * 60 - 9000),
            "total_interest@effective_annual_rate": float(effective * 60 - 9000),
            "total_paid": float(exact * 60),
            "total_paid@effective_annual_rate": float(effective * 60),
            "regular_payment_l2": float(rows[0][1]),
            "final_payment": float(rows[-1][1]),
            "total_interest_l2": float(paid - 9000),
            "total_paid_l2": float(paid),
            "schedule_rows": len(rows),
            "first_interest": float(rows[0][2]),
            "first_principal": float(rows[0][3]),
            "balance_after_1": float(rows[0][4]),
            "balance_after_12": float(rows[11][4]),
            "balance_after_24": float(rows[23][4]),
            "balance_after_36": float(rows[35][4]),
            "balance_after_48": float(rows[47][4]),
            "balance_after_59": float(rows[58][4]),
            "balance_after_60": float(rows[59][4]),
            "last_interest": float(rows[59][2]),
            "final_payment_date": loan_payment_dates()[-1],
            "first_payment_date": loan_payment_dates()[0],
            # Spread between the two interest conventions, for the tolerances.
            "_largest_balance_gap": float(max(abs(a[4] - b[4])
                                              for a, b in zip(rows, exact_rows))),
            "_balance_left_at_178_21": float(left["178.21"]),
        }


def loan_payment_dates():
    """Sixty due dates: the first of each month, starting one month after
    the loan does on March 1, 2027."""
    dates = []
    year, month = 2027, 4
    for _ in range(60):
        dates.append(f"{year:04d}-{month:02d}-01")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return dates


# --- math: projectile with drag -----------------------------------------------

PROJECTILE = dict(speed=25.0, angle_deg=30.0, mass=0.43, diameter=0.22,
                  drag_coefficient=0.25, air_density=1.2, g=9.81, step=0.1)


def projectile_constant():
    p = PROJECTILE
    area = math.pi * p["diameter"] ** 2 / 4
    return area, 0.5 * p["air_density"] * p["drag_coefficient"] * area / p["mass"]


def projectile_derivative(state):
    _, k = projectile_constant()
    _, _, vx, vy = state
    speed = math.hypot(vx, vy)
    return (vx, vy, -k * speed * vx, -PROJECTILE["g"] - k * speed * vy)


def projectile_heun(step=None, positions_from_corrected_velocity=False):
    """Rows (t, x, y, vx, vy) up to the first step with y below zero."""
    step = PROJECTILE["step"] if step is None else step
    angle = math.radians(PROJECTILE["angle_deg"])
    state = (0.0, 0.0, PROJECTILE["speed"] * math.cos(angle),
             PROJECTILE["speed"] * math.sin(angle))
    rows = [(0.0,) + state]
    count = 0
    while state[1] >= 0:
        k1 = projectile_derivative(state)
        predicted = tuple(s + step * d for s, d in zip(state, k1))
        k2 = projectile_derivative(predicted)
        new = tuple(s + step / 2 * (a + b) for s, a, b in zip(state, k1, k2))
        if positions_from_corrected_velocity:
            new = (state[0] + step / 2 * (state[2] + new[2]),
                   state[1] + step / 2 * (state[3] + new[3]), new[2], new[3])
        state = new
        count += 1
        rows.append((count * step,) + state)
    return rows


def projectile_landing(rows):
    before, after = rows[-2], rows[-1]
    fraction = before[2] / (before[2] - after[2])
    return (before[1] + fraction * (after[1] - before[1]),
            before[0] + fraction * (after[0] - before[0]))


def projectile_peak_interpolated(rows):
    """Peak height from a parabola through the three highest table rows."""
    top = max(range(len(rows)), key=lambda j: rows[j][2])
    y0, y1, y2 = rows[top - 1][2], rows[top][2], rows[top + 1][2]
    return y1 - (y0 - y2) ** 2 / (8 * (y0 - 2 * y1 + y2))


def projectile_converged():
    """The same model with a fourth-order scheme and a very small step."""
    step = 1e-4
    angle = math.radians(PROJECTILE["angle_deg"])
    state = (0.0, 0.0, PROJECTILE["speed"] * math.cos(angle),
             PROJECTILE["speed"] * math.sin(angle))
    time, peak = 0.0, 0.0
    while True:
        k1 = projectile_derivative(state)
        k2 = projectile_derivative(tuple(s + step / 2 * d for s, d in zip(state, k1)))
        k3 = projectile_derivative(tuple(s + step / 2 * d for s, d in zip(state, k2)))
        k4 = projectile_derivative(tuple(s + step * d for s, d in zip(state, k3)))
        new = tuple(s + step / 6 * (a + 2 * b + 2 * c + d)
                    for s, a, b, c, d in zip(state, k1, k2, k3, k4))
        if new[1] < 0:
            fraction = state[1] / (state[1] - new[1])
            return (state[0] + fraction * (new[0] - state[0]),
                    time + fraction * step, peak)
        state, time, peak = new, time + step, max(peak, new[1])


def solve_projectile_drag():
    p = PROJECTILE
    angle = math.radians(p["angle_deg"])
    area, k = projectile_constant()
    rows = projectile_heun()
    reach, flight = projectile_landing(rows)
    variant = projectile_heun(positions_from_corrected_velocity=True)
    variant_reach, variant_flight = projectile_landing(variant)
    exact_reach, exact_flight, exact_peak = projectile_converged()
    first, last = rows[1], rows[-1]
    return {
        "range_no_air": p["speed"] ** 2 * math.sin(2 * angle) / p["g"],
        "range_no_air@g_10": p["speed"] ** 2 * math.sin(2 * angle) / 10.0,
        "flight_time_no_air": 2 * p["speed"] * math.sin(angle) / p["g"],
        "max_height_no_air": (p["speed"] * math.sin(angle)) ** 2 / (2 * p["g"]),
        "cross_section_area": area,
        "drag_constant": k,
        "terminal_speed": math.sqrt(p["g"] / k),
        "range": reach,
        "flight_time": flight,
        "max_height": max(row[2] for row in rows),
        "landing_step_count": len(rows) - 1,
        "step1_x": first[1], "step1_y": first[2],
        "step1_vx": first[3], "step1_vy": first[4],
        "last_row_time": last[0], "last_row_x": last[1], "last_row_y": last[2],
        # Spread between legitimate readings, for the tolerances.
        "_range_variant": variant_reach,
        "_flight_variant": variant_flight,
        "_height_variant": max(row[2] for row in variant),
        "_height_interpolated": projectile_peak_interpolated(rows),
        "_range_converged": exact_reach,
        "_flight_converged": exact_flight,
        "_height_converged": exact_peak,
        "_step1_x_variant": variant[1][1],
        "_step1_y_variant": variant[1][2],
    }


# --- math: hypothesis test ----------------------------------------------------

MEASUREMENTS = ("50.8", "51.6", "49.7", "52.3", "51.1", "50.4", "52.0", "51.5")
TARGET = 50


def solve_hypothesis_test():
    values = [Fraction(text) for text in MEASUREMENTS]
    n = len(values)
    mean = sum(values) / n
    differences = [value - TARGET for value in values]
    squares = sum((value - mean) ** 2 for value in values)
    sd = math.sqrt(squares / (n - 1))
    se = sd / math.sqrt(n)
    t = float(mean - TARGET) / se
    p_t = student_t_two_sided_p(t, n - 1)
    crit95 = student_t_critical(n - 1, 0.05)

    by_size = sorted(range(n), key=lambda j: abs(differences[j]))
    assert len({abs(d) for d in differences}) == n and 0 not in differences
    ranks = [0] * n
    for rank, index in enumerate(by_size, start=1):
        ranks[index] = rank
    w_plus = sum(r for r, d in zip(ranks, differences) if d > 0)
    w_minus = sum(r for r, d in zip(ranks, differences) if d < 0)
    smaller = min(w_plus, w_minus)
    # Exact null distribution: each rank is positive or negative with equal
    # chance, so every one of the 2^8 sign patterns is equally likely.
    counts = {}
    for signs in product((0, 1), repeat=n):
        total_rank = sum(r for r, s in zip(range(1, n + 1), signs) if s)
        counts[total_rank] = counts.get(total_rank, 0) + 1

    def two_sided(limit):
        """Twice the chance of a rank sum of at most ``limit``."""
        return Fraction(2 * sum(c for w, c in counts.items() if w <= limit), 2 ** n)

    p_exact = two_sided(smaller)
    # The largest smaller-rank-sum that is significant at 1%, two-sided.
    significant = [w for w in sorted(counts) if two_sided(w) <= Fraction(1, 100)]
    assert significant, "no rank sum is significant at 1% for this sample size"
    critical = max(significant)
    mu = n * (n + 1) / 4
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    z = (w_plus - mu) / sigma
    z_corrected = (w_plus - mu - 0.5) / sigma
    positives = sum(1 for d in differences if d > 0)
    sign_p = Fraction(2 * sum(math.comb(n, j) for j in range(n - positives + 1)), 2 ** n)
    total = abs(sum(differences))
    flips = sum(1 for signs in product((1, -1), repeat=n)
                if abs(sum(s * abs(d) for s, d in zip(signs, differences))) >= total)
    return {
        "sample_size": n,
        "sample_mean": float(mean),
        "sample_sd": sd,
        "standard_error": se,
        "t_statistic": t,
        "degrees_of_freedom": n - 1,
        "p_value": p_t,
        "p_value@wilcoxon_exact": float(p_exact),
        "p_value@wilcoxon_normal": normal_two_sided_p(z),
        "p_value@wilcoxon_normal_corrected": normal_two_sided_p(z_corrected),
        "p_value@sign_test": float(sign_p),
        "p_value@sign_flip_permutation": flips / 2 ** n,
        "t_critical_95": crit95,
        "ci95_low": float(mean) - crit95 * se,
        "ci95_high": float(mean) + crit95 * se,
        "differences": [float(d) for d in differences],
        "ranks": ranks,
        "w_plus": w_plus,
        "w_minus": w_minus,
        "p_value_exact": float(p_exact),
        "decision": "reject" if p_t < 0.05 else "do_not_reject",
        "decision_l2": "reject" if p_exact < Fraction(1, 100) else "do_not_reject",
        "_p_value_exact_fraction": p_exact,
        "sign_patterns": 2 ** n,
        "critical_w_1pct": critical,
        "_p_at_critical": float(two_sided(critical)),
        "_sample_sd_population": math.sqrt(squares / n),
    }


# --- math: titration curve ----------------------------------------------------

TITRATION_VOLUMES = (0, 5.0, 10.0, 12.5, 20.0, 24.0, 25.0, 26.0, 30.0, 40.0, 50.0)


def titration_ph(base_ml, ka=1.8e-5, kw=1.0e-14, acid_ml=25.0, acid_m=0.100,
                 base_m=0.100):
    """pH from the charge balance [H+] + [Na+] = [OH-] + [A-], by bisection."""
    volume = acid_ml + base_ml
    acid = acid_m * acid_ml / volume
    sodium = base_m * base_ml / volume

    def excess_positive(h):
        return h + sodium - kw / h - acid * ka / (ka + h)

    low, high = 1e-15, 1.0
    for _ in range(200):
        mid = math.sqrt(low * high)
        if excess_positive(mid) > 0:
            high = mid
        else:
            low = mid
    return -math.log10(math.sqrt(low * high))


def titration_key(volume):
    return "ph_" + f"{volume:g}".replace(".", "_") + "_ml"


def solve_titration_curve():
    result = {titration_key(v): titration_ph(v) for v in TITRATION_VOLUMES}
    result.update({
        "equivalence_volume": 0.100 * 25.0 / 0.100,
        "half_equivalence_volume": 0.100 * 25.0 / 0.100 / 2,
        "initial_ph": titration_ph(0),
        "half_equivalence_ph": titration_ph(12.5),
        "equivalence_ph": titration_ph(25.0),
        "pka": -math.log10(1.8e-5),
        # Spread from the acid constant and from shortcut formulas.
        "_initial_ph_ka_175": titration_ph(0, ka=1.75e-5),
        "_half_ph_ka_174": titration_ph(12.5, ka=1.74e-5),
        "_equivalence_ph_ka_174": titration_ph(25.0, ka=1.74e-5),
        "_initial_ph_shortcut": -math.log10(math.sqrt(1.8e-5 * 0.100)),
        "_equivalence_ph_shortcut": 14 + math.log10(math.sqrt(1.0e-14 / 1.8e-5 * 0.050)),
    })
    return result


# --- math: least-squares fit --------------------------------------------------

POINTS = ((1, "2.3"), (2, "4.1"), (3, "5.8"), (4, "8.2"), (5, "9.9"),
          (6, "11.6"), (7, "14.1"))


def solve_least_squares_fit():
    points = [(Fraction(x), Fraction(y)) for x, y in POINTS]
    n = len(points)
    x_mean = sum(x for x, _ in points) / n
    y_mean = sum(y for _, y in points) / n
    sxx = sum((x - x_mean) ** 2 for x, _ in points)
    sxy = sum((x - x_mean) * (y - y_mean) for x, y in points)
    syy = sum((y - y_mean) ** 2 for _, y in points)
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean
    residuals = [y - (intercept + slope * x) for x, y in points]
    sse = sum(r * r for r in residuals)
    assert sum(residuals) == 0 and sse == syy - slope * sxy
    assert sum(x * r for (x, _), r in zip(points, residuals)) == 0
    assert intercept + slope * x_mean == y_mean
    s = math.sqrt(sse / (n - 2))
    se_slope = s / math.sqrt(sxx)
    se_intercept = s * math.sqrt(Fraction(1, n) + x_mean ** 2 / sxx)
    crit = student_t_critical(n - 2, 0.05)
    r_squared = 1 - sse / syy
    stiffness = 1000 / float(slope)   # slope is mm per N; 1 N/mm = 1000 N/m
    return {
        "point_count": n,
        "x_mean": float(x_mean), "y_mean": float(y_mean),
        "sxx": float(sxx), "sxy": float(sxy), "syy": float(syy),
        "slope": float(slope), "_slope_fraction": slope,
        "intercept": float(intercept), "_intercept_fraction": intercept,
        "residuals": [float(r) for r in residuals],
        "residual_sum_of_squares": float(sse),
        "residual_sd": s,
        "se_slope": se_slope,
        "se_intercept": se_intercept,
        "t_critical_95": crit,
        "slope_ci95_low": float(slope) - crit * se_slope,
        "slope_ci95_high": float(slope) + crit * se_slope,
        "slope_ci95_half_width": crit * se_slope,
        "r_squared": float(r_squared),
        "correlation": math.sqrt(r_squared),
        "spring_constant": stiffness,
        "spring_constant_se": stiffness * se_slope / float(slope),
        "spring_constant_ci95_low": 1000 / (float(slope) + crit * se_slope),
        "spring_constant_ci95_high": 1000 / (float(slope) - crit * se_slope),
    }


# --- math: entropy explanation ------------------------------------------------


def ways_to_share(packets, atoms):
    """Ways to put identical packets on distinguishable atoms."""
    return math.comb(packets + atoms - 1, atoms - 1)


def solve_entropy_explanation():
    splits = {left: ways_to_share(left, 3) * ways_to_share(6 - left, 3)
              for left in range(7)}
    assert sum(splits.values()) == ways_to_share(6, 6)
    return {
        "ways_all_in_one_group": splits[6],
        "ways_three_each": splits[3],
        "ways_three_in_one_group": ways_to_share(3, 3),
        "ways_five_one": splits[5],
        "ways_four_two": splits[4],
        "ways_total": sum(splits.values()),
        "share_three_each_percent": 100 * splits[3] / sum(splits.values()),
    }


# --- engineering: cantilever beam ---------------------------------------------


def solve_cantilever_beam():
    load, length = 4000.0, 1500.0                 # N, mm
    modulus, yield_strength = 68900.0, 276.0      # MPa
    moment = load * length                        # N·mm
    allowable = yield_strength / 3
    modulus_needed = moment / allowable
    inertia_needed = load * length ** 3 / (3 * modulus * 15.0)
    # Section b by 2b: S = 2b³/3, I = 2b⁴/3.
    width_stress = (1.5 * modulus_needed) ** (1 / 3)
    width_deflection = (1.5 * inertia_needed) ** 0.25

    def section(width):
        depth = 2 * width
        return width * depth ** 2 / 6, width * depth ** 3 / 12

    width = 1
    while True:
        s, i = section(width)
        if moment / s <= allowable and load * length ** 3 / (3 * modulus * i) <= 15.0:
            break
        width += 1
    s, i = section(width)
    # Alternative: one millimeter less width with the same depth. It meets
    # both limits, but the depth is no longer twice the width.
    narrow = width - 1
    narrow_s = narrow * (2 * width) ** 2 / 6
    narrow_i = narrow * (2 * width) ** 3 / 12
    assert moment / narrow_s <= allowable
    assert load * length ** 3 / (3 * modulus * narrow_i) <= 15.0
    return {
        "width@depth_rounded_alone": float(narrow),
        "bending_stress@depth_rounded_alone": moment / narrow_s,
        "tip_deflection@depth_rounded_alone": load * length ** 3 / (3 * modulus * narrow_i),
        "reaction_force": load / 1000,
        "max_shear": load / 1000,
        "max_bending_moment": moment / 1e6,
        "allowable_stress": allowable,
        "required_section_modulus": modulus_needed,
        "required_second_moment": inertia_needed,
        "min_width_for_stress": width_stress,
        "min_width_for_deflection": width_deflection,
        "width": float(width),
        "depth": float(2 * width),
        "governing_limit": "deflection" if width_deflection > width_stress else "stress",
        "section_modulus_chosen": s,
        "second_moment_chosen": i,
        "bending_stress": moment / s,
        "tip_deflection": load * length ** 3 / (3 * modulus * i),
    }


# --- engineering: conveyor gear ratio -----------------------------------------

BELT_SPEED, DRUM_DIAMETER = 0.4, 0.150      # m/s, m


def drum_rpm():
    return BELT_SPEED / (math.pi * DRUM_DIAMETER) * 60


def conveyor_tooth_sets(motor_rpm=1725, low=12, high=72, tolerance=0.02):
    """Every (motor pulley, driven pulley, chain sprocket, drum sprocket)
    with tooth counts in range whose belt speed is within the tolerance."""
    exact = motor_rpm / drum_rpm()
    found = []
    for z1 in range(low, high + 1):
        for z2 in range(low, high + 1):
            for z3 in range(low, high + 1):
                # Only drum sprockets near the needed size can pass; the
                # speed test below is still the one that decides.
                near = exact * z1 * z3 / z2
                for z4 in range(max(low, int(near * 0.97)),
                                min(high, int(near * 1.03) + 1) + 1):
                    ratio = Fraction(z2 * z4, z1 * z3)
                    speed = math.pi * DRUM_DIAMETER * motor_rpm / 60 / float(ratio)
                    if abs(speed - BELT_SPEED) <= tolerance * BELT_SPEED:
                        found.append((z1, z2, z3, z4))
    return found


def solve_conveyor_gear_ratio():
    rpm = drum_rpm()
    exact = 1725 / rpm
    sets = conveyor_tooth_sets()
    stage_ratios = [z2 / z1 for z1, z2, _, _ in sets] + [z4 / z3 for _, _, z3, z4 in sets]
    return {
        "drum_speed": rpm,
        "drum_angular_speed": BELT_SPEED / (DRUM_DIAMETER / 2),
        "exact_ratio": exact,
        "ratio_window_low": exact / 1.02,
        "ratio_window_high": exact / 0.98,
        "valid_tooth_sets": sorted(sets),
        "valid_tooth_set_count": len(sets),
        "stage_ratio_low": min(stage_ratios),
        "stage_ratio_high": max(stage_ratios),
        "closest_ratio": min((Fraction(z2 * z4, z1 * z3) for z1, z2, z3, z4 in sets),
                             key=lambda r: abs(float(r) - exact)),
    }


# --- engineering: heat sink ---------------------------------------------------


def solve_heat_sink():
    power, junction_max, air, junction_case = 20.0, 125.0, 40.0, 1.0
    pad, coefficient = 0.3, 10.0
    total = (junction_max - air) / power
    plate = total - junction_case - pad
    area = 1 / (coefficient * plate)             # both faces together
    side = math.sqrt(area / 2) * 1000            # mm
    rounded = math.ceil(side / 5) * 5
    plate_actual = 1 / (coefficient * 2 * (rounded / 1000) ** 2)
    # Alternative: the four 3 mm edges counted as cooled surface as well.
    thickness = 0.003
    side_edges = (-4 * thickness + math.sqrt(16 * thickness ** 2 + 8 * area)) / 4 * 1000
    rounded_edges = math.ceil(side_edges / 5) * 5
    area_edges = 2 * (rounded_edges / 1000) ** 2 + 4 * (rounded_edges / 1000) * thickness
    return {
        "temperature_rise_allowed": junction_max - air,
        "total_resistance": total,
        "case_to_air_resistance": total - junction_case,
        "plate_resistance_limit": plate,
        "plate_area": area,
        "plate_area@one_face": area / 2,
        "square_side_exact": side,
        "square_side": float(rounded),
        "plate_resistance": plate_actual,
        "junction_temperature": air + power * (junction_case + pad + plate_actual),
        "plate_temperature": air + power * plate_actual,
        "case_temperature": air + power * (pad + plate_actual),
        "square_side_exact@edges_counted": side_edges,
        "square_side@edges_counted": float(rounded_edges),
        "junction_temperature@edges_counted":
            air + power * (junction_case + pad + 1 / (coefficient * area_edges)),
    }


# --- engineering: pipe and pump -----------------------------------------------

FLOW, LIFT, PIPE_LENGTH, BORE, GRAVITY = 1.5e-3, 6.0, 35.0, 0.040, 9.81

# Water at one atmosphere, from standard property tables:
# temperature °C -> (kinematic viscosity m²/s, density kg/m³).
WATER = {
    5: (1.519e-6, 999.97),
    10: (1.307e-6, 999.70),
    15: (1.139e-6, 999.10),
    20: (1.004e-6, 998.21),
    25: (0.893e-6, 997.05),
    30: (0.801e-6, 995.65),
}


def pipe_velocity():
    return FLOW / (math.pi * BORE ** 2 / 4)


def colebrook(reynolds, relative_roughness):
    factor = 0.02
    for _ in range(200):
        factor = (-2 * math.log10(relative_roughness / 3.7
                                  + 2.51 / (reynolds * math.sqrt(factor)))) ** -2
    return factor


def darcy_friction_head(roughness_mm, temperature_c, length=PIPE_LENGTH):
    velocity = pipe_velocity()
    viscosity, _ = WATER[temperature_c]
    factor = colebrook(velocity * BORE / viscosity, roughness_mm / 1000 / BORE)
    return factor * length / BORE * velocity ** 2 / (2 * GRAVITY)


def hazen_williams_head(length, coefficient):
    return (10.67 * length * FLOW ** 1.852
            / (coefficient ** 1.852 * BORE ** 4.8704))


def hazen_williams_variants(length, coefficient):
    """The same law as it is printed in other places: other constants, the
    velocity form, and the forms in US units. For the tolerance."""
    velocity = pipe_velocity()
    gpm = FLOW * 1000 * 60 / 3.785411784
    inches = BORE / 0.0254
    return {
        "si_10_67": hazen_williams_head(length, coefficient),
        "si_10_654": 10.654 * length * FLOW ** 1.852
                     / (coefficient ** 1.852 * BORE ** 4.8704),
        "si_10_583_4_87": 10.583 * length * FLOW ** 1.852
                          / (coefficient ** 1.852 * BORE ** 4.87),
        "velocity_form": (velocity / (0.849 * coefficient * (BORE / 4) ** 0.63))
                         ** (1 / 0.54) * length,
        "us_per_100_ft": 0.2083 * (100 / coefficient) ** 1.852 * gpm ** 1.852
                         / inches ** 4.8655 / 100 * length,
        "us_psi_per_ft": 4.52 * gpm ** 1.852 / (coefficient ** 1.852 * inches ** 4.8704)
                         * (length / 0.3048) * 6894.757 / (999.1 * GRAVITY),
    }


def solve_pipe_and_pump():
    velocity = pipe_velocity()
    viscosity20, density20 = WATER[20]
    viscosity15, density15 = WATER[15]
    friction = hazen_williams_head(PIPE_LENGTH + 8.0, 140)
    head = LIFT + friction
    hydraulic = density15 * GRAVITY * FLOW * head
    velocity_head = velocity ** 2 / (2 * GRAVITY)
    variants = hazen_williams_variants(PIPE_LENGTH + 8.0, 140)
    return {
        "flow_velocity": velocity,
        "velocity_head": velocity_head,
        "static_head": LIFT,
        "static_pressure": density20 * GRAVITY * LIFT / 1000,
        "reynolds_number": velocity * BORE / viscosity20,
        # Turbulent across the whole table of water temperatures.
        "flow_regime": "turbulent" if min(velocity * BORE / nu for nu, _ in WATER.values())
                       > 4000 else "not turbulent",
        "reynolds_number_l2": velocity * BORE / viscosity15,
        "friction_head_smooth_20c": darcy_friction_head(0.0, 20),
        "friction_head_steel_20c": darcy_friction_head(0.045, 20),
        "friction_head_low": darcy_friction_head(0.0, 25),
        "friction_head_high": darcy_friction_head(0.045, 15),
        "friction_loss": friction,
        "friction_pressure": density15 * GRAVITY * friction / 1000,
        "total_head": head,
        "total_head@with_velocity_head": head + velocity_head,
        "total_pressure": density15 * GRAVITY * head / 1000,
        "static_pressure_l2": density15 * GRAVITY * LIFT / 1000,
        "hydraulic_power": hydraulic,
        "electrical_power": hydraulic / 0.40,
        "battery_current": hydraulic / 0.40 / 12.0,
        "equivalent_length": PIPE_LENGTH + 8.0,
        "_friction_variant_low": min(variants.values()),
        "_friction_variant_high": max(variants.values()),
        "_hydraulic_power_density_1000": 1000.0 * GRAVITY * FLOW * head,
        "_head_per_kpa_15c": density15 * GRAVITY / 1000,
    }


# --- engineering: shelf bracket -----------------------------------------------

BRACKET_LOAD, SHELF_DEPTH, PLY = 40.0, 10.0, 0.25      # lb, in, in


def bracket_section_stress(radius, distance=0.0):
    """Bending stress (psi) in a quarter disc of the given radius at a
    vertical section ``distance`` from the wall, under the even shelf load."""
    per_inch = BRACKET_LOAD / SHELF_DEPTH
    moment = per_inch * (SHELF_DEPTH - distance) ** 2 / 2
    depth = math.sqrt(radius ** 2 - distance ** 2)
    return moment, depth, 6 * moment / (PLY * depth ** 2)


def solve_shelf_bracket():
    moment = BRACKET_LOAD * SHELF_DEPTH / 2
    _, _, stress10 = bracket_section_stress(10.0)
    stresses = [bracket_section_stress(10.0, x / 100)[2] for x in range(0, 1000)]
    assert max(stresses) == stresses[0]          # the wall section is the weakest
    return {
        "moment_at_wall": moment,
        "load_per_inch": BRACKET_LOAD / SHELF_DEPTH,
        "load_distance_from_wall": SHELF_DEPTH / 2,
        "screw_downward_force": BRACKET_LOAD / 2,
        "working_stress": 1000.0,
        "reference_radius": 10.0,
        "reference_section_modulus": PLY * 10.0 ** 2 / 6,
        "reference_stress": stress10,
        "reference_arc_length": math.pi * 10.0 / 2,
        "reference_area": math.pi * 10.0 ** 2 / 4,
    }


# --- engineering: compression spring ------------------------------------------

SPRING = dict(free=0.75, working=0.55, force=1.2, max_outside=0.27,
              shear_modulus=10.0e6, tensile=280000.0, stress_share=0.45)


def solve_compression_spring():
    s = SPRING
    travel = s["free"] - s["working"]
    rate = s["force"] / travel
    # The reference design: 0.030 in wire, 0.235 in mean diameter, 13 active
    # coils, ends squared and ground.
    wire, mean, active = 0.030, 0.235, 13
    made_rate = spring_rate(s["shear_modulus"], wire, mean, active)
    total = active + 2
    solid = wire * total
    index = mean / wire
    working_force = made_rate * travel
    solid_force = made_rate * (s["free"] - solid)
    return {
        "working_deflection": travel,
        "spring_rate": rate,
        "allowable_shear_stress": s["stress_share"] * s["tensile"],
        "reference_wire": wire,
        "reference_mean_diameter": mean,
        "reference_active_coils": active,
        "reference_total_coils": total,
        "reference_outside_diameter": mean + wire,
        "reference_index": index,
        "reference_rate": made_rate,
        "reference_solid_length": solid,
        "reference_wahl_factor": wahl_factor(index),
        "reference_working_force": working_force,
        "reference_working_stress": spring_stress(working_force, mean, wire,
                                                  wahl_factor(index)),
        "reference_solid_force": solid_force,
        "reference_solid_stress": spring_stress(solid_force, mean, wire,
                                                wahl_factor(index)),
    }


# --- conditional answers ------------------------------------------------------
# Each takes the choices a model states and returns what follows from them.


def spring_rate(shear_modulus, wire, mean, active):
    return shear_modulus * wire ** 4 / (8 * mean ** 3 * active)


def wahl_factor(index):
    return (4 * index - 1) / (4 * index - 4) + 0.615 / index


def bergstrasser_factor(index):
    return (4 * index + 2) / (4 * index - 3)


def direct_shear_factor(index):
    return 1 + 0.5 / index


def spring_stress(force, mean, wire, factor):
    return factor * 8 * force * mean / (math.pi * wire ** 3)


def cantilever_stress(moment_knm, section_modulus_mm3):
    return moment_knm * 1e6 / section_modulus_mm3


def cantilever_deflection(modulus_gpa, second_moment_mm4):
    return 4000.0 * 1500.0 ** 3 / (3 * modulus_gpa * 1000 * second_moment_mm4)


def bracket_screw_group(e, s):
    """Screw-group reading: the two screws alone hold the bracket."""
    sideways = BRACKET_LOAD * (SHELF_DEPTH / 2 - e) / s
    return sideways, math.hypot(sideways, BRACKET_LOAD / 2)


def bracket_bearing(e, a, s, p, both_screws, wall_moment=False):
    """Bearing reading: the wall edge presses on the wall at depth p below
    the shelf; the screws (at depths a and a + s) hold the top in. Returns
    the sideways force on the upper and on the lower screw.

    Moments about the bearing point: the load turns the bracket with
    40 × 5 lb·in and the screws' upward 40 lb, a distance e from the wall,
    turn it back with 40 × e. ``wall_moment`` leaves that second term out
    and uses the full 200 lb·in, as some answers do.
    """
    moment = BRACKET_LOAD * (SHELF_DEPTH / 2 - (0.0 if wall_moment else e))
    upper, lower = p - a, p - a - s
    if not both_screws:
        return moment / upper, 0.0
    return (moment * upper / (upper ** 2 + lower ** 2),
            moment * lower / (upper ** 2 + lower ** 2))


def screw_total(sideways):
    """Total force on a screw that carries half the load downward."""
    return math.hypot(sideways, BRACKET_LOAD / 2)


CONDITIONAL = {
    ("engineering", "cantilever-beam", "max_bending_moment@with_self_weight"):
        lambda weight_kn_per_m: 4.0 * 1.5 + weight_kn_per_m * 1.5 ** 2 / 2,
    ("engineering", "cantilever-beam", "reaction_force@with_self_weight"):
        lambda weight_kn_per_m: 4.0 + weight_kn_per_m * 1.5,
    ("engineering", "cantilever-beam", "max_bending_moment@factored_load"):
        lambda load_factor: 4.0 * 1.5 * load_factor,
    ("engineering", "cantilever-beam", "reaction_force@factored_load"):
        lambda load_factor: 4.0 * load_factor,
    ("engineering", "cantilever-beam", "stress_for_stated_section"):
        cantilever_stress,
    ("engineering", "cantilever-beam", "deflection_for_stated_section"):
        cantilever_deflection,
    ("engineering", "cantilever-beam", "section_modulus_for_stated_allowable"):
        lambda moment_knm, allowable_mpa: moment_knm * 1e6 / allowable_mpa,
    ("engineering", "conveyor-gear-ratio", "overall_ratio"):
        lambda motor_rpm: motor_rpm / drum_rpm(),
    ("engineering", "conveyor-gear-ratio", "belt_speed_for_stated_ratio"):
        lambda motor_rpm, ratio: math.pi * DRUM_DIAMETER * motor_rpm / ratio / 60,
    ("engineering", "conveyor-gear-ratio", "drum_speed@belt_thickness"):
        lambda belt_thickness_mm: BELT_SPEED * 60
        / (math.pi * (DRUM_DIAMETER + belt_thickness_mm / 1000)),
    ("engineering", "conveyor-gear-ratio", "tooth_ratio"):
        lambda z1, z2, z3, z4: (z2 / z1) * (z4 / z3),
    ("engineering", "conveyor-gear-ratio", "belt_speed_for_teeth"):
        lambda z1, z2, z3, z4: math.pi * DRUM_DIAMETER * 1725
        / ((z2 / z1) * (z4 / z3)) / 60,
    ("engineering", "heat-sink", "heat_sink_resistance_limit"):
        lambda junction_target_c, interface_resistance:
        (junction_target_c - 40.0) / 20.0 - 1.0 - interface_resistance,
    ("engineering", "heat-sink", "junction_temperature_for_stated_sink"):
        lambda interface_resistance, sink_resistance:
        40.0 + 20.0 * (1.0 + interface_resistance + sink_resistance),
    ("engineering", "pipe-and-pump", "reynolds_number"):
        lambda viscosity_mm2_per_s: pipe_velocity() * BORE / (viscosity_mm2_per_s * 1e-6),
    ("engineering", "pipe-and-pump", "friction_head_straight_pipe"):
        lambda roughness_mm, temperature_c: darcy_friction_head(roughness_mm,
                                                               temperature_c),
    ("engineering", "pipe-and-pump", "friction_head_straight_pipe@hazen_williams"):
        lambda c: hazen_williams_head(PIPE_LENGTH, c),
    ("engineering", "pipe-and-pump", "friction_head_from_factor"):
        lambda friction_factor, length_m: friction_factor * length_m / BORE
        * pipe_velocity() ** 2 / (2 * GRAVITY),
    ("engineering", "pipe-and-pump", "fitting_loss"):
        lambda k_total: k_total * pipe_velocity() ** 2 / (2 * GRAVITY),
    ("engineering", "pipe-and-pump", "total_head_for_stated_losses"):
        lambda losses_m: LIFT + losses_m,
    ("engineering", "pipe-and-pump", "hydraulic_power_for_stated_head"):
        lambda head_m: 998.2 * GRAVITY * FLOW * head_m,
    ("engineering", "pipe-and-pump", "input_power_for_stated_efficiency"):
        lambda hydraulic_w, efficiency: hydraulic_w / efficiency,
    ("engineering", "shelf-bracket", "screw_sideways_force"):
        lambda e, s: bracket_screw_group(e, s)[0],
    ("engineering", "shelf-bracket", "screw_resultant_force"):
        lambda e, s: bracket_screw_group(e, s)[1],
    ("engineering", "shelf-bracket", "moment_about_screws"):
        lambda e: BRACKET_LOAD * (SHELF_DEPTH / 2 - e),
    ("engineering", "shelf-bracket", "screw_sideways_force@bearing_upper_screw"):
        lambda e, a, p: bracket_bearing(e, a, 1.0, p, both_screws=False)[0],
    ("engineering", "shelf-bracket", "screw_sideways_force@bearing_upper_screw_wall_moment"):
        lambda a, p: BRACKET_LOAD * SHELF_DEPTH / 2 / (p - a),
    ("engineering", "shelf-bracket", "screw_sideways_force@bearing_both_screws"):
        lambda e, a, s, p: bracket_bearing(e, a, s, p, both_screws=True)[0],
    ("engineering", "shelf-bracket", "lower_screw_sideways_force_bearing"):
        lambda e, a, s, p: bracket_bearing(e, a, s, p, both_screws=True)[1],
    ("engineering", "shelf-bracket", "screw_sideways_force@bearing_both_screws_wall_moment"):
        lambda a, s, p: bracket_bearing(0, a, s, p, True, wall_moment=True)[0],
    ("engineering", "shelf-bracket", "lower_screw_sideways_force_bearing@wall_moment"):
        lambda a, s, p: bracket_bearing(0, a, s, p, True, wall_moment=True)[1],
    ("engineering", "shelf-bracket", "lower_screw_resultant_force_bearing"):
        lambda e, a, s, p: screw_total(bracket_bearing(e, a, s, p, True)[1]),
    ("engineering", "shelf-bracket", "lower_screw_resultant_force_bearing@wall_moment"):
        lambda a, s, p: screw_total(bracket_bearing(0, a, s, p, True, wall_moment=True)[1]),
    ("engineering", "shelf-bracket", "screw_resultant_force@bearing_upper_screw"):
        lambda e, a, p: screw_total(bracket_bearing(e, a, 1.0, p, False)[0]),
    ("engineering", "shelf-bracket", "screw_resultant_force@bearing_upper_screw_wall_moment"):
        lambda a, p: screw_total(bracket_bearing(0, a, 1.0, p, False, wall_moment=True)[0]),
    ("engineering", "shelf-bracket", "screw_resultant_force@bearing_both_screws"):
        lambda e, a, s, p: screw_total(bracket_bearing(e, a, s, p, True)[0]),
    ("engineering", "shelf-bracket", "screw_resultant_force@bearing_both_screws_wall_moment"):
        lambda a, s, p: screw_total(bracket_bearing(0, a, s, p, True, wall_moment=True)[0]),
    ("engineering", "shelf-bracket", "quarter_disc_stress_at_wall@net_section"):
        lambda moment_lb_in, net_depth_in: moment_lb_in / (PLY * net_depth_in ** 2 / 6),
    ("engineering", "shelf-bracket", "plywood_bending_stress"):
        lambda moment_lb_in, depth_in: 6 * moment_lb_in / (PLY * depth_in ** 2),
    ("engineering", "shelf-bracket", "quarter_disc_stress_at_wall"):
        lambda radius_in: bracket_section_stress(radius_in)[2],
    ("engineering", "shelf-bracket", "moment_from_stated_load"):
        lambda load, distance: load * distance,
    ("engineering", "compression-spring", "rate_from_geometry"):
        lambda d, D, Na: spring_rate(SPRING["shear_modulus"], d, D, Na),
    ("engineering", "compression-spring", "active_coils_for_exact_rate"):
        lambda d, D: SPRING["shear_modulus"] * d ** 4
        / (8 * D ** 3 * SPRING["force"] / (SPRING["free"] - SPRING["working"])),
    ("engineering", "compression-spring", "rate_from_stated_modulus"):
        lambda G, d, D, Na: spring_rate(G, d, D, Na),
    ("engineering", "compression-spring", "outside_diameter"):
        lambda d, D: D + d,
    ("engineering", "compression-spring", "shear_stress"):
        lambda F, d, D: spring_stress(F, D, d, wahl_factor(D / d)),
    ("engineering", "compression-spring", "shear_stress@bergstrasser"):
        lambda F, d, D: spring_stress(F, D, d, bergstrasser_factor(D / d)),
    ("engineering", "compression-spring", "shear_stress@direct_shear_only"):
        lambda F, d, D: spring_stress(F, D, d, direct_shear_factor(D / d)),
    ("engineering", "compression-spring", "shear_stress@uncorrected"):
        lambda F, d, D: spring_stress(F, D, d, 1.0),
    ("engineering", "compression-spring", "solid_length"):
        lambda d, Nt: d * Nt,
    ("engineering", "compression-spring", "solid_length@ends_not_ground"):
        lambda d, Nt: d * (Nt + 1),
    ("engineering", "compression-spring", "force_at_length"):
        lambda k, length: k * (SPRING["free"] - length),
    ("math", "titration-curve", "ph_at_volume"):
        lambda base_ml, ka, kw: titration_ph(base_ml, ka=ka, kw=kw),
}

SOLVERS = {
    ("math", "loan-amortization"): solve_loan_amortization,
    ("math", "projectile-drag"): solve_projectile_drag,
    ("math", "hypothesis-test"): solve_hypothesis_test,
    ("math", "titration-curve"): solve_titration_curve,
    ("math", "least-squares-fit"): solve_least_squares_fit,
    ("math", "entropy-explanation"): solve_entropy_explanation,
    ("engineering", "cantilever-beam"): solve_cantilever_beam,
    ("engineering", "conveyor-gear-ratio"): solve_conveyor_gear_ratio,
    ("engineering", "heat-sink"): solve_heat_sink,
    ("engineering", "pipe-and-pump"): solve_pipe_and_pump,
    ("engineering", "shelf-bracket"): solve_shelf_bracket,
    ("engineering", "compression-spring"): solve_compression_spring,
}
