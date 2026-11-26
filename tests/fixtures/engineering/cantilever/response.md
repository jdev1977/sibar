# Cantilever sizing

**Assumptions:** structural steel S275 to EN 10025-2, yield strength 275 MPa, E = 210 GPa. I use a safety factor of 1.5 on yield, and EN 1993-1-1 (Eurocode 3) for the checks.

- Maximum moment: M = 4 kN × 1.5 m = 6 kN·m
- Allowable stress: 275 / 1.5 = 183 MPa
- Required section modulus: 32 800 mm³

Choose an IPE 100 (W = 34.2 cm³, I = 171 cm⁴).

| Check | Value | Limit |
|---|---|---|
| Bending stress | 175 MPa | 183 MPa |
| Shear stress | 11 MPa | 105 MPa |
| Tip deflection | 12.5 mm | 15 mm |

The achieved safety factor is 1.57. Lateral-torsional buckling should also be checked.
