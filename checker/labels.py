"""What the extractor looks for in each task: the labels of quantities and of
conditional inputs, and the words that show an alternative may apply.

A label pattern must match the whole label, so "total interest" is not found
in "total interest if paid monthly in advance". Where a bare name could mean
something else (the resistance allowed and the resistance reached, a rate
asked for and a rate obtained), the pattern needs the qualifying word. A
quantity with no pattern is not extracted.
"""

import re

_EQUIVALENT_PH = {f"ph_{v}_ml": rf"pH (?:at|after|for) (?:V ?= ?)?{v}(?:\.0{{1,2}})? ?mL"
                  r"(?: of (?:NaOH|base)(?: added)?)?"
                  for v in (5, 10, 20, 24, 26, 30, 40, 50)}
_DRAG = r"(?: with (?:air )?(?:drag|resistance))?"
_NO_AIR = r"(?:with no|without|ignoring|with zero|neglecting) (?:air(?: resistance)?|drag)"
_ALLOWED = r"(?:max(?:imum|\.)?(?: allowable| allowed| permissible)?|allowable|allowed|required)"
_RATIO = (r"(?:required|exact|theoretical|ideal|needed|target) (?:overall |total )?"
          r"(?:gear |reduction |speed |transmission )?(?:ratio|reduction)(?: ratio)?"
          r"|(?:overall|total) (?:required|exact) (?:gear |reduction )?(?:ratio|reduction)")
_FINAL = r"(?:final|chosen|selected|specified)"
_P_VALUE = (r"(?:(?:two[- ](?:sided|tailed)|exact)(?: exact| two[- ](?:sided|tailed))? )?"
            r"p(?:[- ]value)?(?: \(two[- ](?:sided|tailed)\))?")
_INTEREST = (r"total (?:amount of )?interest(?: paid| cost| charged)?"
             r"(?: over (?:the )?(?:life of the )?(?:loan|term|5 years|five years))?")
_PAID = (r"total (?:amount )?(?:paid|repaid|repayment|payments|of (?:all )?payments)"
         r"(?: over (?:the )?(?:loan|term|5 years|five years))?")

QUANTITIES = {
    "loan-amortization": {
        "monthly_payment": r"(?:(?:required|equal|fixed|regular|standard) )?monthly "
                           r"(?:loan )?(?:payment|repayment|instal?lment)(?: amount)?",
        "total_interest": _INTEREST, "total_interest_l2": _INTEREST,
        "total_paid": _PAID, "total_paid_l2": _PAID,
        "payment_count": r"(?:total )?number of (?:monthly )?payments",
        "monthly_rate_percent": r"monthly (?:interest )?rate",
        "final_payment": r"(?:final|last)(?:,? adjusted)? (?:monthly )?payment(?: amount)?",
        "first_payment_date": r"first payment(?: date| due| due date)?(?: date)?",
        "final_payment_date": r"(?:final|last) payment (?:date|due|due date)",
    },
    "projectile-drag": {
        "range": r"(?:horizontal )?range" + _DRAG,
        "flight_time": r"(?:total )?(?:time of flight|flight time)" + _DRAG,
        "max_height": r"max(?:imum|\.)? height(?: reached)?" + _DRAG,
        "range_no_air": rf"(?:horizontal )?range {_NO_AIR}|(?:vacuum|no[- ]drag|drag[- ]free) "
                        r"range|range in (?:a )?vacuum",
    },
    "hypothesis-test": {
        "sample_mean": r"(?:sample )?mean|x̄",
        "sample_sd": r"(?:sample )?standard deviation|sample SD|s",
        "standard_error": r"standard error(?: of the mean)?|SEM?",
        "degrees_of_freedom": r"degrees of freedom|df",
        "t_statistic": r"t(?:[- ](?:statistic|stat|value))?",
        "t_critical_95": r"(?:two[- ](?:sided|tailed) )?(?:critical t(?:[- ]value)?|critical "
                         r"value|t[_ -]?crit(?:ical)?(?: value)?)",
        "p_value": _P_VALUE, "p_value_exact": _P_VALUE,
        "w_plus": r"W ?\^?\+|W_\+|T ?\^?\+|sum of (?:the )?positive ranks|positive[- ]rank sum",
        "w_minus": r"W ?\^?-|W_-|T ?\^?-|sum of (?:the )?negative ranks|negative[- ]rank sum",
    },
    "least-squares-fit": {
        "slope": r"(?:fitted |best[- ]fit )?slope(?: of the (?:fitted |best[- ]fit )?line)?",
        "intercept": r"(?:fitted |best[- ]fit )?(?:y[- ])?intercept",
        "r_squared": r"R\^2|r\^2|R²|coefficient of determination(?:,? R(?:\^2|²))?",
        "correlation": r"correlation coefficient|r",
        "se_slope": r"standard error (?:of|in|for) (?:the )?slope|slope standard error|"
                    r"SE ?\((?:b|m|slope)\)",
        "se_intercept": r"standard error (?:of|in|for) (?:the )?intercept|intercept standard "
                        r"error|SE ?\((?:a|c|intercept)\)",
        "spring_constant": r"spring (?:constant|stiffness)",
    },
    "titration-curve": {
        "equivalence_volume": r"(?:volume (?:of (?:NaOH|base) )?(?:needed )?(?:at|to reach) "
                              r"(?:the )?equivalence(?: point)?|equivalence(?:[- ]point)? "
                              r"volume|V_?\{?eq\}?)",
        "half_equivalence_volume": r"half[- ]equivalence(?:[- ]point)? volume",
        "pka": r"pK_?\{?a\}?",
        "ph_0_ml": r"initial pH|pH (?:before any (?:base|NaOH)(?: is added)?|at 0(?:\.0{1,2})? "
                   r"?mL|at the start)",
        "ph_12_5_ml": r"pH at (?:the )?half[- ]equivalence(?: point)?|pH (?:at|after) "
                      r"12\.50? ?mL",
        "ph_25_ml": r"pH at (?:the )?equivalence(?: point)?|pH (?:at|after) 25(?:\.0{1,2})? ?mL",
        **_EQUIVALENT_PH,
    },
    "entropy-explanation": {},
    "cantilever-beam": {
        "reaction_force": r"(?:vertical )?(?:support )?reaction(?: force)?(?: at (?:the )?"
                          r"(?:fixed end|wall|support))?",
        "max_shear": r"max(?:imum|\.)? shear(?: force)?",
        "max_bending_moment": r"max(?:imum|\.)? (?:bending )?moment(?: at (?:the )?(?:fixed "
                              r"end|wall|support))?|(?:bending )?moment at (?:the )?(?:fixed "
                              r"end|wall|support)|fixed[- ]end moment|M_?\{?max\}?",
        "allowable_stress": r"allowable (?:bending )?stress",
        "required_section_modulus": r"(?:minimum )?required (?:elastic )?section modulus|"
                                    r"section modulus required",
        "required_second_moment": r"(?:minimum )?required (?:second moment of area|moment of "
                                  r"inertia)",
        "width": rf"(?:{_FINAL}|required) (?:section )?width",
        "depth": rf"(?:{_FINAL}|required) (?:section )?depth",
        "bending_stress": r"(?:actual |max(?:imum|\.)? )?bending stress",
        "tip_deflection": r"(?:actual |calculated |max(?:imum|\.)? )?tip deflection|actual "
                          r"deflection",
    },
    "conveyor-gear-ratio": {
        "drum_speed": r"(?:required )?(?:(?:drive )?drum (?:rotational |rotation |shaft )?"
                      r"(?:speed|rpm)|output (?:shaft )?speed)",
        "drum_angular_speed": r"drum angular (?:speed|velocity)",
        "overall_ratio": _RATIO,
        "exact_ratio": _RATIO,
    },
    "heat-sink": {
        "total_resistance": rf"{_ALLOWED} total (?:thermal )?resistance|total {_ALLOWED} "
                            r"(?:thermal )?resistance",
        "case_to_air_resistance": rf"(?:{_ALLOWED}|available) case[- ]to[- ](?:air|ambient) "
                                  r"(?:thermal )?resistance",
        "plate_resistance_limit": rf"{_ALLOWED} (?:plate|heat ?sink)(?:[- ]to[- ](?:air|"
                                  r"ambient))? (?:thermal )?resistance",
        "plate_area": r"(?:required|minimum|needed)(?: total)?(?: plate| cooled| cooling| "
                      r"surface)? area",
        "square_side": rf"(?:{_FINAL}|rounded(?:[- ]up)?) (?:square )?(?:plate )?side"
                       r"(?: length)?",
        "junction_temperature": r"(?:resulting|actual|predicted|estimated|calculated|"
                                r"operating|final) junction temperature",
    },
    "pipe-and-pump": {
        "flow_velocity": r"(?:mean |average )?(?:flow )?velocity|flow speed",
        "velocity_head": r"velocity head",
        "static_head": r"static (?:head|lift)",
        "friction_loss": r"(?:pipe )?(?:friction(?:al)? (?:head )?loss(?:es)?|friction head)",
        "equivalent_length": r"(?:total )?equivalent (?:pipe )?length",
        "total_head": r"total (?:dynamic |pump(?:ing)? )?head(?: the pump must (?:deliver|"
                      r"supply))?|TDH|pump head",
        "hydraulic_power": r"hydraulic power|water power",
        "electrical_power": r"electric(?:al)? (?:input )?power(?: drawn| input)?|pump input "
                            r"power",
        "battery_current": r"(?:battery )?current(?: draw| drawn)?(?: from (?:the )?(?:12[- ]?V "
                           r")?battery)?",
    },
    "shelf-bracket": {
        "moment_at_wall": r"(?:max(?:imum|\.)? )?(?:bending )?moment (?:at|where the bracket "
                          r"meets) (?:the )?wall|wall moment",
        "quarter_disc_stress_at_wall": r"(?:max(?:imum|\.)? )?bending stress at (?:the )?wall"
                                       r"(?: section)?",
        "screw_downward_force": r"(?:downward|vertical|shear) (?:force|load) (?:on|per) (?:each )?"
                                r"screw",
        "screw_sideways_force": r"(?:sideways|horizontal|lateral) (?:force|load) (?:on|per) "
                                r"(?:each )?screw",
        "screw_resultant_force": r"(?:resultant|total|combined) (?:force|load) (?:on|per) "
                                 r"(?:each )?screw",
    },
    "compression-spring": {
        "spring_rate": r"(?:required|target|needed) (?:spring )?rate",
        "rate_from_geometry": r"(?:actual|resulting|achieved|calculated|design) (?:spring )?rate",
        "allowable_shear_stress": r"allowable (?:shear )?stress",
        "shear_stress": r"(?:corrected )?(?:shear )?stress at (?:the )?(?:working (?:length|load|"
                        r"height)|0\.55 ?in)",
        "solid_length": r"solid (?:length|height)",
    },
}

# Conditional inputs found by label: task -> input -> (label, unit).
LABELLED_INPUTS = {
    "compression-spring": {
        "d": (r"wire diameter", "in"),
        "D": (r"mean (?:coil )?diameter", "in"),
        "Na": (r"(?:number of )?active coils", "1"),
        "Nt": (r"total (?:number of )?coils", "1"),
    },
    "shelf-bracket": {"radius_in": (r"(?:bracket |quarter[- ]circle )?radius", "in")},
}
# Conditional inputs found anywhere in the text: task -> input -> patterns.
# Any speed of 500 rpm or more is taken as a motor's (the drum turns at about
# 51), so a second such speed leaves the motor speed undecided.
SEARCHED_INPUTS = {
    "conveyor-gear-ratio": {"motor_rpm": (
        r"(?<![\d.,])([5-9]\d\d|\d{4}) ?(?:rpm|r/min)",
    )},
}

# The words that show an alternative may apply. A response without them does
# not state it; with them, whether it does is not decided here. An
# alternative with no pattern is never ruled out.
MENTIONS = {
    "with_self_weight": r"self[- ]?weight|own weight|weight of the (?:beam|bar)",
    "factored_load": r"load factor|factored|dynamic factor|impact factor|design load",
    "effective_annual_rate": r"effective",
    "one_face": r"one (?:face|side)|single|per (?:face|side)|each (?:face|side)",
    "edges_counted": r"edge",
    "depth_rounded_alone": r"ratio|slightly|50 ?(?:mm)? ?(?:×|x|by) ?102",
    "belt_thickness": r"thick",
    "with_velocity_head": r"velocity head|dynamic head",
    "hazen_williams": r"hazen",
    "fitted_minus_measured": r"(?:fitted|predicted) ?(?:minus|-|−)|ŷ(?:_i)? ?- ?y",
    "symmetric_interval": r"±|\\pm|plus or minus",
    "g_10": r"g ?(?:=|≈|of) ?10(?![\d.])|10 ?m/s",
    "bergstrasser": r"bergstr",
    "direct_shear_only": r"direct[- ]shear|static",
    "uncorrected": r"uncorrected|(?:no|without) (?:a )?(?:curvature |stress )?correction",
    "ends_not_ground": r"not (?:be(?:ing)? )?ground|unground|plain",
    "bearing_upper_screw": r"bear", "bearing_upper_screw_wall_moment": r"bear",
    "bearing_both_screws": r"bear", "bearing_both_screws_wall_moment": r"bear",
    "wall_moment": r"bear", "net_section": r"net |through the (?:screw )?holes",
}

# A mention of these means a mismatch of these quantities is not called wrong.
DOUBTS = {
    "heat-sink": (r"margin|derat|(?:target|design|limit(?:ing)?) junction",
                  ("total_resistance", "case_to_air_resistance",
                   "plate_resistance_limit"),
                  "the answer may size for a lower junction temperature"),
}


def compiled(pattern):
    return re.compile(pattern, re.IGNORECASE)
