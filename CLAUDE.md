# CLAUDE.md

Guidance for Claude (and contributors) working on this exporter.  Read
this BEFORE editing the math or the JSX format -- the conventions here
are the inverse of `aftereffects-to-houdini-usd-exporter` and need to stay paired.

## What this is

A Solaris LOP HDA that walks a USD stage and writes an After Effects
.jsx that recreates the scene as a comp.  Reverse of
`aftereffects-to-houdini-usd-exporter`'s `GegenschussAeUsdExporter.jsx`.  Same TresSims
convention, applied in inverse.

## Repo orientation

- `gegenschuss_solaris_ae_export.py` -- the core converter.  Pure
  Python; uses `pxr` (USD bindings, available inside Houdini's hython).
  Importable standalone for tests.  Public entry: `usd_to_jsx(stage,
  out_path, **opts)`.
- `install_hda.py` -- run inside Houdini once to build the HDA from the
  module.  The HDA's PythonModule delegates to the sibling `.py` file
  and reloads it on each cook, so module edits don't need an HDA
  rebuild.
- `otls/` -- built HDAs.  Add to `HOUDINI_OTLSCAN_PATH` to auto-load.

## Coordinate convention (TresSims, inverse)

Forward (AE -> USD), from `aftereffects-to-houdini-usd-exporter`:

```
position:  ( px / s, -py / s, -pz / s)        s = scale (default 100)
rotation:  M_usd_row = S * R_ae^T * S          S = diag(1, -1, -1)
```

Reverse (USD -> AE):

```
position:  ( ux * s, -uy * s, -uz * s)
rotation:  same conjugation -- the function is involutive
```

Identity USD -> identity AE for every prim type.  Don't add per-prim
sign flips.  If decomposition looks off for one prim type only, you've
probably misdiagnosed something else.

### Why the same matrix function works in both directions

`S * A^T * S` is involutive when applied twice:
`S * (S * A^T * S)^T * S = S * S * A * S * S = I * A * I = A`.

So `usd_to_ae_rot3` and the exporter's `toUSDMat3` are the same code.

## Euler decomposition

We write all rotation into AE's individual X/Y/Z Rotation channels in
ZYX order, leaving Orientation at (0, 0, 0).  This is **lossy** when the
original AE scene used keyed Orientation -- the world-space matrix is
preserved but the channel split won't match what was originally typed.

Round-trip is still identity at the matrix level.  Anyone keyframing
Orientation back from a USD round-trip needs to know that.

`euler_zyx_from_matrix` has a gimbal-lock branch at `|sin(yr)| > 0.99999`
that pins `xr = 0` and recovers `zr` from the remaining cells.  Standard;
verified algebraically in the source comments.

## Camera focal length

Forward: `focal_usd = FILM_WIDTH_MM * zoom_px / comp_width * MM_TO_USD`
with `FILM_WIDTH_MM = 36`, `MM_TO_USD = 0.01`.

Reverse: `zoom_px = focal_usd * comp_width / (FILM_WIDTH_MM * MM_TO_USD)`.

The reverse needs `comp_width`, which the user provides as an HDA
parameter.  USD apertureH/V give the aspect ratio so we can derive
`comp_height` from `comp_width` if the user requests auto-height.

## Light intensity

Per-type scale factor used in forward, divided out in reverse:

| USD type      | Forward (AE % -> USD) | Reverse (USD -> AE %) |
|---------------|-----------------------|------------------------|
| DomeLight     | * 0.01                | / 0.01                 |
| DistantLight  | * 0.05                | / 0.05                 |
| SphereLight   | * 1.0                 | / 1.0                  |

Spot light cone angle: USD half-angle * 2 = AE full angle.
Spot light cone softness: USD 0-1 * 100 = AE percent.

## Animation sampling

The walker reads one sample per frame across the export range.  Static
attributes collapse to a single `setValue` call in the JSX; animated
attributes emit `setValueAtTime(t, v)` per frame.  No keyframe
interpolation modes are preserved -- AE re-interpolates linearly between
samples, which matches USD's default linear timeSample interp.

## Verifying

For matrix correctness, the simplest sanity check is **identity USD ->
identity AE**:

1. Build a synthetic stage with a single Xform at translate (1, 2, 3),
   no rotation.
2. Run the export.
3. The resulting JSX should set the layer's position to (100, -200, -300)
   at default scale=100.

For round-trip, the gold standard is: AE -> USD via `aftereffects-to-houdini-usd-exporter` ->
USD -> AE via this tool -> compare the second AE comp's transform values
to the first.  Any drift > 1e-4 on translation or rotation (in degrees)
is a bug.

## Pending follow-ups

- **End-to-end round-trip test.**  The forward exporter has a `test/`
  folder with a `test.hiplc` and backup `.usda` files.  Running those
  through the reverse path and comparing to a fresh AE comp would
  validate the whole chain.
- **2-node POI camera reconstruction.**  Currently flattens to keyed
  rotation.  A future pass could detect a USD camera with a constant
  pos -> POI direction and emit it as a 2-node camera with
  `pointOfInterest` set.
- **AVLayer anchor point.**  Forward direction ignores anchors; reverse
  defaults to layer centre.  When the forward side learns to round-trip
  anchors, mirror that here.
- **Visibility round-trip.**  Currently extracts in/out frames from
  `visibility.timeSamples`.  Untested against real AE preview.
- **Text/Shape layer round-trip.**  Forward writes them as Mesh quads
  with displayColor.  We could read the prim's `documentation`
  metadata (`[Text]` / `[Shape]` / `[Solid]`) to re-classify on import,
  but the geometry is still a bounding-box quad, so the visual result
  is the same.

## How to resume a session

1. Re-read this section first; tick off anything the user has confirmed
   since.
2. For the README: keep the early-release warning, the conventions
   block, and the prim-mapping table in sync with the code.  Lift the
   tone from `aftereffects-to-houdini-usd-exporter/README.md`.
3. For functional gaps: write a small synthetic USD test stage in
   Python first (see `Verifying` above), then iterate.
4. **Never auto-commit.**  Make the edit, save, tell the user briefly
   what changed, wait for `ship`.
