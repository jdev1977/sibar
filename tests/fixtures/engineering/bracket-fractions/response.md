Here's a simple steel L-bracket for a shelf 10" deep carrying 50 lb. I've used 1/8" thick mild steel, which is easy to bend.

Bending at the corner: M = 50 lb × 5 in = 250 lb·in; with a 1.5 in wide strap, S = bt²/6 = 0.0039 in³, σ = 64,000 psi — too high, so I added a gusset. With the gusset, the stress drops to about 9,000 psi, a safety factor of about 4 against 36 ksi yield.

Use two #10 wood screws into a stud per leg.

**bracket.scad**
```openscad
thickness = 3.2;   // mm (1/8 in)
width = 38;
leg = 250;
module leg_plate() { cube([leg, width, thickness]); }
union() {
  leg_plate();
  rotate([0, -90, 0]) leg_plate();
  translate([0, width/2 - thickness/2, 0])
    linear_extrude(thickness) polygon([[0,0],[100,0],[0,100]]);
}
```
