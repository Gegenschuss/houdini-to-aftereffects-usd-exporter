```
       _____                          __
      / ___/__ ___ ____ ___  ___ ____/ /  __ _____ ___
     / (_ / -_) _ `/ -_) _ \(_-</ __/ _ \/ // (_-<(_-<
     \___/\__/\_, /\__/_//_/___/\__/_//_/\_,_/___/___/
             /___/
```

# Houdini → After Effects USD Exporter

> 🚧 Early release — coordinates, hierarchy, cameras and nulls are
> exercised against synthetic stages.  Lights, footage materials, and
> animation passes have not yet been round-tripped end-to-end against
> a real AE preview.  Open an issue if you hit something off.

A Solaris LOP HDA that walks a USD stage and writes an After Effects
`.jsx` script.  When the script is run in AE, it creates a comp and
populates it with cameras, lights, nulls, solids, and footage layers —
preserving hierarchy and per-frame animation.

This is the **reverse** of [`ae-usd-exporter`](https://github.com/Gegenschuss/ae-usd-exporter)
and uses the same TresSims AE↔Houdini convention applied in inverse.

## Why

Round-trip Houdini Solaris ↔ After Effects without going through C4D /
Alembic.  Smaller files, no per-layer Z stacking, no fps drift.  The
`.jsx` is plain text and human-readable.

## Conventions

```
USD position (ux, uy, uz)        →  AE position (ux,  -uy, -uz) * scale
USD rotation matrix (row-vector) →  AE column-vector form, S·R^T·S, S = diag(1, -1, -1)
```

Identity USD → identity AE for every prim type.  Same convention as the
forward exporter; the bilateral conjugation is involutive so the exact
same matrix function maps either direction.

## Prim mapping

| USD                               | AE                                                |
|-----------------------------------|---------------------------------------------------|
| `Camera`                          | Camera (1-node, focal length keyed)               |
| `DomeLight`                       | Ambient light                                     |
| `DistantLight`                    | Parallel light                                    |
| `SphereLight`                     | Point light                                       |
| `SphereLight` + `ShapingAPI`      | Spot light (cone angle / softness keyed)          |
| `Xform` (no `geo` child)          | Null                                              |
| `Xform` + `Mesh "geo"` + displayColor | Solid (color + size from quad bounds)         |
| `Xform` + `Mesh "geo"` + `UsdPreviewSurface` | Footage (texture file imported by absolute path) |

Hierarchy is preserved — nested USD prims become parented AE layers.
Animation `timeSamples` become AE keyframes (one key per frame across
the export range; static channels collapse to a single `setValue`).

## Install

1. Clone the repo, or download `gegenschuss_solaris_ae_export.py` and
   `install_hda.py` into a folder on disk.
2. In Houdini, open the Python Source Editor:
   ```python
   exec(open("/path/to/install_hda.py").read())
   install_hda("/path/to/repo/otls/gegenschuss_ae_export.hda")
   ```
   This builds the HDA and installs it in the current session.
3. To make the HDA load on every Houdini start, add the repo's `otls/`
   directory to `HOUDINI_OTLSCAN_PATH`, or use
   `File → Install Asset Library`.

The Python module is loaded fresh on every cook, so you can edit
`gegenschuss_solaris_ae_export.py` without rebuilding the HDA.

## Usage

1. Build a Solaris graph that produces the USD stage you want to export
   (`sopimport`, `karma`, file `usd_import`, etc.).
2. Drop a **Gegenschuss AE Export** node and wire your stage into its
   single input.
3. Set the parameters:
   - **Output JSX** — where to write the script (defaults to `$HIP/<node>.jsx`)
   - **Comp name** — leave blank to use the stage's `defaultPrim` name
   - **Comp width / height** — defaults 1920×1080.  Height of 0 derives
     from the first Camera prim's aperture ratio.
   - **FPS** — 0 = read from stage metadata
   - **Scale** — must match the AE-side exporter's Scale (default 100,
     so 1 USD unit = 100 AE px = 1 m at default Houdini scale)
   - **Frame range** — defaults to the stage's start/end timecodes
   - **Unwrap AE_Scene wrapper** — strips the centre-comp parent the
     AE-side exporter adds, so round-trips stay identity
4. Hit **Save JSX**.  A confirmation dialog reports the prim counts.
5. In After Effects: `File → Scripts → Run Script File…` → pick the JSX.
   It creates a new comp and populates it.

## What's verified vs not

End-to-end against synthetic USD stages:
- ✅ Coordinate inversion (identity USD → identity AE)
- ✅ Translation, scale, hierarchy
- ✅ Static + animated transforms (timeSamples → AE keyframes)
- ✅ Camera focal length conversion (USD → AE zoom)
- ✅ Static-value optimisation (single `setValue` instead of per-frame keys)
- ✅ AE_Scene wrapper unwrap

Not yet visually verified end-to-end:
- ⚠️ Round-trip identity (export from AE → import into Houdini → export
  back to AE → compare).  Pending real AE-side test.
- ⚠️ All four light types in AE preview.  Data is converted; intensity
  scaling matches the forward direction's per-type factor.
- ⚠️ Footage import — absolute paths from the Houdini side; AE relinking
  may be needed if assets moved.
- ⚠️ Visibility timeSamples → AE in/out points.
- ⚠️ Spot-light cone angle / softness conversion.

## Known limitations

- **1-node cameras only** — 2-node POI cameras are flattened to keyed
  rotation.  The world-space matrix is preserved but the camera no
  longer aims at a point of interest.
- **Orientation = (0, 0, 0)** — all rotation goes into individual X/Y/Z
  Rotation channels (ZYX order).  If the original AE used keyed
  Orientation, the matrix is still right but the channel split differs.
- **Anchor points** — non-default AVLayer anchor points are not yet
  reconstructed; rotation/scale pivots default to layer centre.
- **Text and shape layers** — exported as Solid layers (the forward
  exporter writes them as Mesh quads with displayColor; we can't tell
  them apart from solids on import).
- **Mesh geometry** — only quad-`geo` meshes are recognised as
  AVLayers.  Arbitrary USD meshes are skipped.
- **Footage paths** — absolute, relative to the Houdini host filesystem.
  Cross-machine projects will need manual relinking.

## Files

- `gegenschuss_solaris_ae_export.py` — core USD → JSX module.  Pure
  Python; uses `pxr` (USD bindings).  Importable standalone for tests.
- `install_hda.py` — run inside Houdini once to build the HDA.
- `otls/` — built HDAs land here.

## Companion repos

- [`ae-usd-exporter`](https://github.com/Gegenschuss/ae-usd-exporter) —
  forward direction (AE → USD).  Same TresSims convention.

## Licence

MIT.
