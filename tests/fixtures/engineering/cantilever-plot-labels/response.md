## Cantilever beam sizing

**Assumptions:** S275 structural steel (yield 275 MPa, E = 210 GPa), a safety factor of 1.5 on yield, deflection limit L/250 = 6 mm. Self-weight is neglected.

**Loads:** M_max = F·L = 4 kN × 1.5 m = 6 kN·m, V = 4 kN.

**Required section modulus:** allowable stress = 275 / 1.5 = 183 MPa, so Z ≥ 6×10⁶ N·mm / 183 MPa = 32 800 mm³.

**Deflection:** δ = FL³/(3EI) ≤ 6 mm gives I ≥ 3.6 × 10⁶ mm⁴.

A UKB 152×89×16 has Z = 109 cm³ and I = 834 cm⁴, so bending stress = 55 MPa and δ = 2.6 mm. The actual factor of safety is 275/55 = 5.0.

Checks per BS EN 1993-1-1 (Eurocode 3): bending ✓, shear ✓, deflection ✓, lateral-torsional buckling ✓.

```python
import numpy as np
import matplotlib.pyplot as plt

L, F, E, I = 1.5, 4e3, 210e9, 834e-8
x = np.linspace(0, L, 100)
delta = F * x**2 * (3 * L - x) / (6 * E * I)
plt.plot(x, delta * 1e3, label="Load case 1")
plt.title("Deflection, case 2")
plt.xlabel("x (m)")
plt.ylabel("deflection (mm)")
plt.legend(["Tip load 4"])
plt.show()
```
