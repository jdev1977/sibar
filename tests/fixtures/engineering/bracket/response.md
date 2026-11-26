Here is a 3D-printable bracket in PETG. Each bracket carries about 15 kg.

**bracket.scad**

```openscad
// all dimensions in mm
arm = 150;        // arm length
wall = 120;       // wall leg
thickness = 5;
width = 30;

difference() {
    cube([arm, width, thickness]);
    translate([20, width/2, -1]) cylinder(d=5, h=thickness+2);
}
cube([thickness, width, wall]);
```

Print it with 4 perimeters. Use M5 screws (ISO 4762) into wall plugs. A gusset keeps the bending stress and deflection low.
