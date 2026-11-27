"""What the extractor looks for in each task: the labels of quantities and of
conditional inputs, and the words that show an alternative may apply.

A label pattern must match the whole label, so "total interest" is not found
in "total interest if paid monthly in advance". Where a bare name could mean
something else (the resistance allowed and the resistance reached, a rate
asked for and a rate obtained), the pattern needs the qualifying word. A
quantity with no pattern is not extracted.
"""

_EQUIVALENT_PH = {f"ph_{v}_ml": rf"pH (?:at|after|for) (?:V ?= ?)?{v}(?:\.0{{1,2}})? ?mL"
                  r"(?: of (?:NaOH|base)(?: added)?)?"
                  for v in (5, 10, 20, 24, 26, 30, 40, 50)}
_DRAG = r"(?: with (?:air )?(?:drag|resistance))?"
_NO_AIR = r"(?:with no|without|ignoring|with zero|neglecting) (?:air(?: resistance)?|drag)"
_ALLOWED = r"(?:max(?:imum|\.)?(?: allowable| allowed| permissible)?|allowable|allowed|required)"
_TO_AIR = r"(?:,? \(?junction[- ]to[- ](?:air|ambient)\)?)?"
_RATIO = (r"(?:required|exact|theoretical|ideal|needed|target) (?:overall |total )?"
          r"(?:gear |reduction |speed |transmission )?(?:ratio|reduction)(?: ratio)?"
          r"|(?:overall|total) (?:required|exact) (?:gear |reduction )?(?:ratio|reduction)")
_FINAL = r"(?:final|chosen|selected|specified)"
_P_VALUE = (r"(?:(?:two[- ](?:sided|tailed)|exact)(?: exact| two[- ](?:sided|tailed))? )?"
            r"p(?:[- ]value)?(?: \(two[- ](?:sided|tailed)\))?")
_INTEREST = (r"total (?:amount of )?interest(?: paid| cost| charged)?"
             r"(?: over (?:the )?(?:life of the )?(?:loan|term|5 years|five years))?")
_PAID = (r"total (?:amount (?:paid|repaid)|paid|repaid|repayment|of (?:all )?payments)"
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
        "ph_12_5_ml": r"pH at (?:the )?half[- ]equivalence(?: point)?(?: 12\.50? ?mL)?|"
                      r"pH (?:at|after) 12\.50? ?mL",
        "ph_25_ml": r"pH at (?:the )?equivalence(?: point)?(?: 25(?:\.0{1,2})? ?mL)?|"
                    r"pH (?:at|after) 25(?:\.0{1,2})? ?mL",
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
        "drum_speed": r"(?:required )?(?:drive )?drum (?:rotational |rotation |shaft )?"
                      r"(?:speed|rpm)",
        "drum_angular_speed": r"drum angular (?:speed|velocity)",
        "overall_ratio": _RATIO,
        "exact_ratio": _RATIO,
    },
    "heat-sink": {
        "total_resistance": rf"(?:{_ALLOWED} total (?:thermal )?resistance|total {_ALLOWED} "
                            r"(?:thermal )?resistance)" + _TO_AIR,
        "case_to_air_resistance": rf"(?:{_ALLOWED}|available) case[- ]to[- ](?:air|ambient) "
                                  r"(?:thermal )?resistance",
        "plate_resistance_limit": rf"{_ALLOWED} (?:plate|heat ?sink)(?:[- ]to[- ](?:air|"
                                  r"ambient))? (?:thermal )?resistance",
        "plate_area": r"(?:required|minimum|needed)(?: total)?(?: plate| cooled| cooling| "
                      r"surface)? area(?: \(both faces\))?",
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
        r"(?<![\d.,])(\d,\d{3}|[5-9]\d\d|\d{4}) ?(?:rpm|r/min)",
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

# A statement of these means the response may work from an assumption of its
# own, so a mismatch of the quantities that follow from it is not called
# wrong: task -> (pattern, quantities or None for all, reason). A doubt only
# ever turns "wrong" into "could_not_determine", so a broad pattern hides
# wrong answers while right ones stay correct: each pattern asks for the
# assumption itself (an amount, an act, a value other than the dictated one),
# not for the word alone.
_GAP = r"(?:[^.\n]|\.(?=\d)){0,30}?"        # within one sentence
_NOT_ZERO = r"(?!0(?:\.0{1,4})?(?!\.?\d))"
_AMOUNT = r"\d ?(?:%|percent\b|per cent\b|°C|K\b|mm\b|m\b|kN\b|lbf?\b|N\b|W\b|rpm\b|psi\b)"
_MARGIN_WORD = r"(?:margin|contingency|headroom|derating|service factor)"
_ANY_MARGIN = rf"(?:{_MARGIN_WORD}|allowance)"
_MARGIN = "|".join((
    r"\b(?:safety|design) (?:margin|allowance)",
    rf"{_AMOUNT}{_GAP}\b{_ANY_MARGIN}",
    rf"\b{_ANY_MARGIN}(?: of| =| is|:)? ?(?:about |roughly |at least |~ ?)?\d",
    r"\b(?:add|includ|appl|keep|kept|allow|leave|reserv|maintain|build in|built[- ]in|siz)"
    rf"\w{{0,4}}\b{_GAP}\b{_MARGIN_WORD}",
    rf"\boversiz\w{{0,3}}\b{_GAP}\d|\b(?:I|we) (?:\w{{1,15}} )?oversize",
    r"\b(?:take|took|assum|use|using|chose|choos|adopt)\w{0,4}\b" + _GAP + r"\bconservativ",
    r"\bconservatively (?:take|assum|use|choos|adopt)",
    r"\bfor (?:extra |some |added )?(?:margin|headroom)\b",
    r"\bderat\w{0,4} (?:\w{1,15} ){0,3}(?:by|to) \d",
))
# Phrases that name a margin only to deny it, or as what a result happens to
# leave: cut before the patterns are applied.
_NO_MARGIN = (
    r"\b(?:no|without|zero|not (?:add|includ|appl|keep|allow)\w{0,4})(?: [\w-]{1,15}){0,3}? "
    r"(?:margins?|contingency|allowance|headroom|safety factor|factor of safety|derating)\b"
    r"|\b(?:margin|factor|allowance|contingency) (?:is|are|was|were|has been|have been) not\b"
    r"|\b(?:leaves|leaving|gives|giving|provides|providing|yields|offers|round\w{0,4}|within)"
    rf"\b{_GAP}\b(?:margins?|headroom|allowance)\b"
    r"|\bmargin(?: of [\d.]{1,8} ?[\w°/%]{0,8})? (?:below|under|against)\b"
)
_LOAD = "|".join((
    r"\b(?:load|dynamic|impact) factor(?: of| =| is|:)? ?(?:γ\w{0,3} ?=? ?)?"
    r"(?!1(?:\.0{1,4})?(?!\.?\d))\d",
    r"\d[- ]?(?:×)? ?(?:load|dynamic|impact) factor",
    rf"\b(?:appl|includ|us|add|with)\w{{0,4}}\b{_GAP}\b(?:load|dynamic|impact) factor",
    r"\bfactored (?:load|moment|shear|force)",
    r"\bdesign load(?: of| =| is|:)? ?(?!4(?:\.0{1,4})? ?kN|40(?:\.0{1,4})? ?lb)\d",
    r"\b(?:load|moment|force) ?[×x*] ?1\.[1-9]",
    rf"\b(?:includ|add)\w{{0,4}}\b{_GAP}\b(?:self[- ]?weight|own weight)",
    r"(?:self[- ]?weight|own weight)(?: of)?" + _GAP
    + r"(?:\d ?(?:kN|N\b|kg|lb)|\b(?:(?:is|are) )?(?:included|added))",
    r"(?:\bwith|\bplus|\+) (?:the |its |the beam'?s )?(?:self[- ]?weight|own weight)",
))
_NO_LOAD = (
    r"|\b(?:no|without|not (?:add|includ|appl|us)\w{0,4})(?: [\w-]{1,15}){0,3}? "
    r"(?:load|dynamic|impact) factor\b|\b(?:not|never) factored\b"
    r"|\b(?:no|without|ignor\w{0,4}|neglect\w{0,4}|exclud\w{0,4}|omit\w{0,6}|"
    r"not includ\w{0,4})(?: [\w'-]{1,15}){0,3}? (?:self[- ]?weight|own weight)"
    rf"(?:{_GAP}\d ?(?:kN/m|kN|N\b|kg|lb))?"
    r"|\b(?:self[- ]?weight|own weight) (?:(?:is|are|was) )?(?:ignored|neglected|omitted|"
    r"excluded|not \w{1,15})"
)
_SAFETY = r"(?:safety factor|factor of safety)"
# A safety factor the answer works with: applied, or small enough to be one it
# chose rather than one its result happens to reach.
_APPLIED_SAFETY = "|".join((
    rf"\b(?:appl|includ|add|us)\w{{0,4}} (?:a |an )?{_SAFETY} of \d",
    rf"(?<!actual )(?<!resulting )(?<!achieved ){_SAFETY}(?: of| =|:)? ?"
    r"(?:1(?:\.\d{1,2})?|[2-4](?:\.[05])?)(?!\.?\d)",
))
_FEE = r"(?:fees?|insurance|tax(?:es)?|deposit|down payment|extra payments?|overpay\w{0,4})"
_LOAN = "|".join((
    rf"\b{_FEE}(?: of| is| by| at| costs?| adds?| =|:)? ?(?:about |roughly |~ ?)?[$€£]? ?\d",
    r"(?:[$€£] ?\d[\d,.]{0,12}|\d ?%|\d{2,7})(?: [\w-]{1,15}){0,3}? " + _FEE + r"\b",
))
_NO_FEE = (
    r"\b(?:no|not|without|exclud(?:es?|ed|ing)|before|ignor\w{0,4}|neglect\w{0,4})"
    rf"(?: [\w-]{{1,15}}){{0,3}}? {_FEE}\b"
    rf"(?:(?:,? and|,? or|,? nor|,|/) ?(?:\w{{1,15}} )?{_FEE}\b){{0,4}}"
)
_ACTIVITY = r"(?:activit(?:y|ies) coefficients?|ionic strength|debye(?:[- ]h\w{1,8})?|davies)"
_NO_ACTIVITY = (
    r"\b(?:no|without|ignor\w{0,4}|neglect\w{0,4}|not (?:includ|consider|appl|us)\w{0,4})"
    rf"(?: [\w-]{{1,15}}){{0,3}}? {_ACTIVITY}(?: effects?| corrections?)?"
    rf"|{_ACTIVITY}(?: effects?| corrections?)? (?:(?:is|are|was|were) )?"
    r"(?:ignored|neglected|omitted|not \w{1,15})"
)
_POINT = r"(?:point|value|observation|outlier|measurement|reading|datum)s?"
_DROP = r"(?:exclud|omit|discard|remov|dropp?)"
_LEFT_OUT = "|".join((
    # leaving out a point, an outlier or a measured value (not "excludes 50")
    rf"\b{_DROP}\w{{0,5}} (?:(?:the|this|that|these|one|an?|any|both|first|last) ){{0,2}}"
    r"(?:(?!(?:target|null|hypothesi|reference|nominal|claimed|specified))[\w.-]{1,15} ){0,2}?"
    rf"(?:{_POINT}\b(?! (?:of )?50(?!\.?0{{0,4}}[1-9]))|x ?= ?\d"
    r"|(?!50(?:\.0{1,4})?(?!\.?\d))\d\d\.\d)",
    rf"\b{_POINT}\b(?:[^.\n]|\.(?=\d)){{0,40}}?\b(?:is|was|are|were|been|be) (?:\w{{1,12}}ly )?"
    r"(?:excluded|omitted|discarded|removed|dropped)",
    r"\b(?:fit\w{0,4}|test\w{0,4}|analysis|mean) without (?:the |this |that )?"
    rf"(?:\w{{1,15}} )?{_POINT}",
    r"\bweighted (?:least[- ]squares|fit|regression)|\bweighted by\b",
))
_NOT_LEFT_OUT = (
    rf"\b(?:no|none of the|neither)(?: [\w-]{{1,15}}){{0,4}}? {_DROP}\w{{0,5}}"
    rf"|\b(?:not|never|without)(?: been)? {_DROP}\w{{0,5}}"
    r"|(?:interval|\bCI\b)(?:[^.\n]|\.(?=\d)){0,60}?\bexclud\w{0,4}"
    r"|\b50(?:\.0{1,4})?\b[^.\n]{0,20}?\bexclud\w{0,4}"
    r"|\b(?:no|not(?: a| an)?|without) weighted"
    r"|\bweighted (?:least[- ]squares|fit|regression) (?:is|was) not\b"
)
# Working on the differences from 50, not any mention of a difference.
_DIFFERENCES = "|".join((
    r"\bdifferences? (?:from (?:the )?(?:\w{1,15} ){0,2}(?:of )?50\b|d(?:_\{?i\}?)?\b|"
    r"[-−] ?50\b)",
    r"\bdifferences ?(?:\(|:|=)",
    r"\b(?:comput|calculat|form|tak|list|us|work\w{0,3} (?:on|with)|test\w{0,3} (?:on)?)"
    r"\w{0,4} (?:the |these )?(?:signed )?differences\b",
    r"\bmean (?:of (?:the )?)?(?:signed )?differences?\b",
    r"\|[ *]{0,4}(?:signed )?differences?(?: ?\([^)|\n]{0,30}\))? ?\|",
    r"\bsubtract\w{0,3}(?: [\w-]{1,15}){0,3}? 50\b|\b50 (?:is )?subtracted\b",
    r"\bdeviations? from (?:the )?(?:\w{1,15} ){0,2}(?:of )?50\b",
    r"d̄|\\bar\{ ?d ?\}|\bd(?:_\{?i\}?)? ?= ?x|\bx(?:_\{?i\}?)? ?(?:-|−|–) ?50\b",
))
_HEIGHT = (
    r"(?:launch|initial|release|starting) height"
    r"(?:\s|of\b|is\b|=|≈|:|\(|about\b|taken\b|as\b|[hy]_?\{?0\}?(?!\w)){0,6}"
)
_LAUNCHED = r"\b(?:launch|kick|thrown|fired|releas)\w{0,3} from"
_PROJECTILE = "|".join((
    rf"{_HEIGHT}{_NOT_ZERO}\d",
    rf"(?<![\d.]){_NOT_ZERO}\d{{1,3}}(?:\.\d{{1,3}})?[- ]?m (?:launch|release|initial|starting) "
    r"height",
    rf"{_LAUNCHED} (?:a height of )?{_NOT_ZERO}\d{{1,3}}(?:\.\d{{1,3}})? ?m(?:et(?:er|re)s?)? "
    r"(?:above|high|up)",
    rf"{_LAUNCHED} a height(?: of)? ?{_NOT_ZERO}\d",
    rf"\by_?\{{?0\}}? ?= ?{_NOT_ZERO}\d",
    rf"\bwind(?: speed| velocity)?(?: of| is| =|:)? ?{_NOT_ZERO}\d",
    rf"(?<![\d.]){_NOT_ZERO}\d{{1,3}}(?:\.\d{{1,3}})? ?m/s (?:head|tail|cross)?[- ]?wind",
    r"\b(?:includ|add|assum|with|account\w{0,3} for)\w{0,4} (?:a |the )?(?:\w{1,15} )?"
    r"(?:head|tail|cross)[- ]?wind",
    r"\b(?:includ|add|account\w{0,3} for)\w{0,4} (?:the )?(?:effect of )?(?:back|top)?spin\b",
    r"\bspin(?: rate)?(?: of| =|:) ?[1-9]|\bmagnus (?:force|lift)(?: coefficient)?(?: of| =) ?"
    r"[\d.]{0,6}[1-9]",
))
_NO_WIND = r"\b(?:no|without|ignor\w{0,4}|neglect\w{0,4})(?: [\w-]{1,15}){0,3}? (?:wind|spin)\b"

# Cut from the text before the doubts are looked for: denials, and mentions
# that name an assumption without making one.
NOT_DOUBTS = {
    "heat-sink": _NO_MARGIN + r"|\b(?:resistance|thermal|temperature(?:[- ]rise)?)[- ]allowance",
    # the allowance for fittings is dictated, not a margin
    "pipe-and-pump": _NO_MARGIN + (
        r"|(?:\d{1,3}(?:\.\d{1,3})? ?m (?:\w{1,15} ){0,2})?(?:fittings?|equivalent[- ]length)"
        r"[- ]allowance"
        r"|\ballowance(?: of ?\d{1,3}(?:\.\d{1,3})? ?m)? for (?:the )?(?:\w{1,15} )?"
        r"(?:fittings|elbows|strainer|valves?)"),
    "cantilever-beam": _NO_MARGIN + _NO_LOAD,
    "conveyor-gear-ratio": _NO_MARGIN + (
        r"|\b(?:no|without|neglect\w{0,4}|ignor\w{0,4}|not (?:account|allow|includ)\w{0,4}"
        r"(?: for)?)(?: [\w-]{1,15}){0,3}? (?:slip|creep)\b"),
    "shelf-bracket": _NO_MARGIN + _NO_LOAD,
    "compression-spring": _NO_MARGIN
    + r"|\b(?:no|without|zero)(?: [\w-]{1,15}){0,2}? pre[- ]?load",
    "loan-amortization": _NO_FEE,
    "titration-curve": _NO_ACTIVITY,
    "least-squares-fit": _NOT_LEFT_OUT,
    "hypothesis-test": _NOT_LEFT_OUT,
    "projectile-drag": _NO_WIND,
}

_OWN = "the response states an assumption or margin of its own"
DOUBTS = {
    "heat-sink": ((
        _MARGIN + r"|\bsafety factor"
        r"|\b(?:target|design|limit(?:ing)?) junction(?: temperature)?(?: T_?\{?j\}?)?"
        r"(?: of| is| =|:|,)? ?(?:about )?(?!125(?!\d))\d{2,3}"
        r"|\b(?:design|siz|aim|target)\w{0,4}\b" + _GAP + r"\bjunction[^.\n\d]{0,25}?"
        r"(?<!\d)(?!125(?!\d))\d{2,3} ?°C",
        ("total_resistance", "case_to_air_resistance", "plate_resistance_limit",
         "temperature_rise_allowed", "plate_area", "square_side", "square_side_exact",
         "junction_temperature", "plate_resistance", "plate_temperature",
         "case_temperature"), _OWN),),
    "pipe-and-pump": ((
        _MARGIN + r"|\bsafety factor",
        ("friction_loss", "equivalent_length", "total_head", "hydraulic_power",
         "electrical_power", "battery_current"), _OWN),),
    # The brief dictates a safety factor of 3 on the yield strength.
    "cantilever-beam": ((
        "|".join((
            _MARGIN, _LOAD,
            rf"{_SAFETY}[^.\n]{{0,20}}?(?:on|to) the (?:load|moment|deflection)",
            rf"(?<!actual )(?<!resulting )(?<!achieved ){_SAFETY}(?: of| =| is|:)? ?"
            r"(?!3(?:\.0{1,4})?(?!\.?\d))(?!\d{1,4}(?:\.\d{1,4})? ?[/>≥])\d",
        )), None, _OWN),),
    "conveyor-gear-ratio": ((
        "|".join((
            _MARGIN,
            r"\d ?%[^.\n]{0,20}?\b(?:slip|creep)",
            r"\b(?:slip|creep)(?: factor)?(?: of| =| is|:)? ?(?:about )?" + _NOT_ZERO + r"\d",
            r"\b(?:allow|account|compensat|correct|includ)\w{0,4}(?: for)?[^.\n]{0,20}?"
            r"\b(?:slip|creep)\b",
            r"(?:belt thickness|thickness of the belt|\blagging)[^.\n]{0,20}?\d ?mm",
            r"\d ?mm[- ](?:thick\b|(?:thick )?(?:belt|lagging)\b(?! speed))",
            r"\b(?:includ|add|account\w{0,3} for)\w{0,4}[^.\n]{0,20}?(?:belt thickness|lagging)",
            r"\b(?:effective|drum pitch)(?: drum)? diameter(?: of| =| is|:)? ?"
            r"(?!150(?!\.?\d))\d{3}",
        )),
        ("drum_speed", "drum_angular_speed", "overall_ratio", "exact_ratio",
         "ratio_window_low", "ratio_window_high"), _OWN),),
    "shelf-bracket": ((
        "|".join((
            _MARGIN, _LOAD, _APPLIED_SAFETY,
            rf"{_SAFETY}{_GAP}\b(?:on|to) (?:the )?(?:\w{{1,15}} )?"
            r"(?:load|force|weight|moment|shelf)",
        )), None, _OWN),),
    "compression-spring": ((
        "|".join((
            _MARGIN, _APPLIED_SAFETY,
            rf"{_SAFETY}{_GAP}\b(?:on|to) (?:the )?(?:\w{{1,15}} )?"
            r"(?:load|force|stress|strength)",
            r"\bpre[- ]?load(?:ed)?(?: of| =| is|:| by)? ?(?:about )?" + _NOT_ZERO + r"\d",
            r"(?<![\d.])" + _NOT_ZERO + r"\d{1,4}(?:\.\d{1,3})? ?(?:lbf?|N|in) (?:of )?"
            r"pre[- ]?load",
            r"\b(?:add|includ|appl|assum|us|with)\w{0,4} [^.\n]{0,20}?pre[- ]?load",
        )), None, _OWN),),
    "loan-amortization": ((_LOAN, None, _OWN),),
    "titration-curve": ((
        _ACTIVITY + r"|(?:\bat|temperature(?: of| =| is|:)?|\bT ?=) ?(?<![\d.])"
        r"(?!25(?!\d))\d{1,2}(?:\.\d)? ?°C", None, _OWN),),
    "least-squares-fit": ((_LEFT_OUT, None, _OWN),),
    "hypothesis-test": (
        (_LEFT_OUT, None, _OWN),
        (_DIFFERENCES, ("sample_mean", "ci95_low", "ci95_high"),
         "the response works on differences from 50")),
    "projectile-drag": ((_PROJECTILE, None, _OWN),),
}
