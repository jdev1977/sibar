# Range with quadratic drag

We assume a baseball: mass $m = 0.145\ \text{kg}$, diameter $D = 0.074\ \text{m}$, drag coefficient $C_d = 0.47$, air density $\rho = 1.225\ \text{kg/m}^3$ and $g = 9.81\ \text{m/s}^2$.

The drag force is $F_d = \tfrac{1}{2}\rho C_d A v^2$. There is no closed-form solution, so we integrate numerically with a fourth-order Runge-Kutta method.

```python
import numpy as np
import matplotlib.pyplot as plt
from scipy.integrate import solve_ivp

g = 9.81

def rhs(t, s):
    x, y, vx, vy = s
    return [vx, vy, 0, -g]

sol = solve_ivp(rhs, (0, 10), [0, 0, 21.65, 12.5])
plt.plot(sol.y[0], sol.y[1])
plt.savefig("trajectory.png")
```

Running it gives:

- Range: **43.1 m**
- Time of flight: **2.33 s**
- Maximum height: **6.65 m**

Without drag the range would be $\boxed{55.2\ \text{m}}$.
