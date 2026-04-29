"""
install_hda.py

Run *inside Houdini* (Python Source Editor or `hython -c`) to build the
Solaris LOP HDA that wraps gegenschuss_solaris_ae_export.

Why this lives outside the HDA itself: the wrapper is short and rarely
changes, but the core Python module is large and iterates often.  Keeping
the module as a sibling .py file means edits don't require re-saving the
HDA, and the module can be imported and unit-tested standalone outside
Houdini.

Usage (inside Houdini, Python Source Editor):

    exec(open("/path/to/install_hda.py").read())
    install_hda("/path/to/output.hda")     # creates the HDA on disk

The repo's `otls/` folder is the canonical install target.  After saving,
add `otls/` to HOUDINI_OTLSCAN_PATH (or `File > Install Asset Library`)
so Houdini picks the HDA up on next launch.
"""

import os

HDA_TYPE_NAME    = "gegenschuss::ae_export::1.0"
HDA_LABEL        = "Gegenschuss AE Export"
HDA_CONTEXT      = "Lop"           # Solaris LOP network
HDA_DESCRIPTION  = (
    "Walks the input USD stage and writes an After Effects .jsx that "
    "recreates the scene as a comp.  Reverse of GegenschussAeUsdExporter.jsx."
)


PYTHON_MODULE_TEMPLATE = '''\
"""HDA backing module -- delegates to gegenschuss_solaris_ae_export.

The core converter lives in a sibling .py file alongside this HDA.  We
locate it relative to the HDA's library file so edits don't need a
reinstall.  The path is overridable via the `module_path` parameter on
the HDA in case the user keeps the module somewhere unusual.
"""

import os
import sys
import importlib

MODULE_NAME = "gegenschuss_solaris_ae_export"


def _resolve_module(node):
    explicit = node.parm("module_path").evalAsString().strip() if node.parm("module_path") else ""
    if explicit:
        candidates = [explicit]
    else:
        # Try relative to the HDA's library file.
        candidates = []
        defn = node.type().definition()
        if defn:
            lib = defn.libraryFilePath()
            if lib:
                d = os.path.dirname(lib)
                # otls/ -> ../module.py
                candidates.append(os.path.join(d, "..", MODULE_NAME + ".py"))
                candidates.append(os.path.join(d, MODULE_NAME + ".py"))
        # Also try $HIP and the user's hou.session search path.
        for d in (hou.expandString("$HIP"), hou.expandString("$HOUDINI_USER_PREF_DIR")):
            if d:
                candidates.append(os.path.join(d, MODULE_NAME + ".py"))

    for path in candidates:
        path = os.path.normpath(path)
        if os.path.isfile(path):
            d = os.path.dirname(path)
            if d not in sys.path:
                sys.path.insert(0, d)
            if MODULE_NAME in sys.modules:
                # Force reload so the user can edit the module without restarting Houdini.
                importlib.reload(sys.modules[MODULE_NAME])
            return importlib.import_module(MODULE_NAME)
    raise RuntimeError(
        "Could not find {}.py.  Set the `module_path` parameter on the "
        "HDA, or place the file alongside the HDA's otls folder.  Tried:\\n  {}"
        .format(MODULE_NAME, "\\n  ".join(candidates))
    )


def export_jsx(node):
    """Run the export.  Bound to the `execute` button callback."""
    in_node = node.input(0)
    if in_node is None:
        raise hou.NodeError("Connect a USD stage to the input first.")
    stage = in_node.stage()
    if stage is None:
        raise hou.NodeError("Input did not produce a USD stage.")

    out_path = node.parm("output_jsx").evalAsString().strip()
    if not out_path:
        raise hou.NodeError("Output JSX path is empty.")

    # Resolve and call the core module.
    mod = _resolve_module(node)

    kwargs = {
        "scale":              node.parm("scale").evalAsFloat(),
        "comp_width":         node.parm("comp_width").evalAsInt(),
        "comp_height":        node.parm("comp_height").evalAsInt(),
        "fps":                node.parm("fps").evalAsFloat(),
        "unwrap_ae_scene":    node.parm("unwrap_ae_scene").evalAsInt() == 1,
    }
    name = node.parm("comp_name").evalAsString().strip()
    if name:
        kwargs["comp_name"] = name
    if node.parm("frame_range_use").evalAsInt() == 1:
        kwargs["start_frame"] = node.parm("frame_range1").evalAsInt()
        kwargs["end_frame"]   = node.parm("frame_range2").evalAsInt()
    if node.parm("duration_override").evalAsFloat() > 0:
        kwargs["duration_s"] = node.parm("duration_override").evalAsFloat()

    summary = mod.usd_to_jsx(stage, out_path, **kwargs)

    msg = (
        "Wrote {out_path}\\n"
        "  {n_cams} cam, {n_lights} light, {n_nulls} null, "
        "{n_solids} solid, {n_footage} footage\\n"
        "  Frames {fr0}-{fr1} @ {fps} fps  ({w} x {h})"
    ).format(
        out_path=summary["out_path"],
        n_cams=summary["n_cams"], n_lights=summary["n_lights"],
        n_nulls=summary["n_nulls"], n_solids=summary["n_solids"],
        n_footage=summary["n_footage"],
        fr0=summary["frame_range"][0], fr1=summary["frame_range"][1],
        fps=summary["fps"], w=summary["comp_w"], h=summary["comp_h"],
    )
    hou.ui.displayMessage(msg, title="AE Export")
'''


def _build_param_template_group():
    """Define the LOP HDA's parameter UI."""
    import hou
    g = hou.ParmTemplateGroup()

    g.append(hou.StringParmTemplate(
        "output_jsx", "Output JSX", 1,
        default_value=("$HIP/$OS.jsx",),
        string_type=hou.stringParmType.FileReference,
        file_type=hou.fileType.Any,
        tags={"filechooser_pattern": "*.jsx", "filechooser_mode": "write"},
    ))

    g.append(hou.StringParmTemplate(
        "comp_name", "Comp name", 1, default_value=("",),
        help="Override comp name.  Empty = use stage's defaultPrim name, or output filename.",
    ))

    g.append(hou.IntParmTemplate(
        "comp_width", "Comp width (px)", 1, default_value=(1920,), min=1, max=16384,
    ))
    g.append(hou.IntParmTemplate(
        "comp_height", "Comp height (px)", 1, default_value=(1080,), min=1, max=16384,
        help="If 0, derived from the first Camera's apertureV/apertureH ratio.",
    ))
    g.append(hou.FloatParmTemplate(
        "fps", "FPS", 1, default_value=(0.0,), min=0.0, max=240.0,
        help="0 = read from stage metadata.",
    ))
    g.append(hou.FloatParmTemplate(
        "scale", "Scale (AE px / USD unit)", 1,
        default_value=(100.0,), min=0.0001, max=10000.0,
        help="Must match the AE-side exporter's Scale; default 100 = 1 m -> 100 px.",
    ))
    g.append(hou.FloatParmTemplate(
        "duration_override", "Comp duration (s)", 1, default_value=(0.0,), min=0.0,
        help="0 = derived from frame range / FPS.",
    ))

    folder = hou.FolderParmTemplate("frame_range_folder", "Frame range")
    folder.addParmTemplate(hou.ToggleParmTemplate(
        "frame_range_use", "Override stage range", default_value=False,
    ))
    folder.addParmTemplate(hou.IntParmTemplate(
        "frame_range", "Range", 2, default_value=(1, 240),
        disable_when="{ frame_range_use == 0 }",
    ))
    g.append(folder)

    g.append(hou.ToggleParmTemplate(
        "unwrap_ae_scene", "Unwrap AE_Scene wrapper", default_value=True,
        help="If the stage's top-level prim is named AE_Scene with a single translate "
             "(the exporter's centre-comp wrapper), strip it on import to keep "
             "round-trips identity.",
    ))

    g.append(hou.StringParmTemplate(
        "module_path", "Python module path", 1, default_value=("",),
        string_type=hou.stringParmType.FileReference,
        help="Override path to gegenschuss_solaris_ae_export.py.  "
             "Empty = look alongside the HDA's library file.",
    ))

    g.append(hou.SeparatorParmTemplate("sep1"))
    g.append(hou.ButtonParmTemplate(
        "execute", "Save JSX",
        script_callback="hou.phm().export_jsx(kwargs['node'])",
        script_callback_language=hou.scriptLanguage.Python,
        join_with_next=False,
    ))

    return g


def install_hda(out_hda_path):
    """Create the HDA file at `out_hda_path` and load it in this Houdini session."""
    import hou

    out_hda_path = os.path.abspath(out_hda_path)
    out_dir = os.path.dirname(out_hda_path)
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    # Use a throwaway Python LOP as the seed -- gives us a working LOP node we
    # can promote to an HDA via createDigitalAsset.  Created in /stage and
    # deleted after.
    stage_root = hou.node("/stage")
    if stage_root is None:
        raise RuntimeError("/stage network not present.  Open a Houdini scene with Solaris support.")

    seed = stage_root.createNode("pythonscript", "ae_export_seed")
    try:
        # Promote to HDA: 1 input, 0 outputs (this is an exporter, not a stage modifier).
        hda_node = seed.createDigitalAsset(
            name=HDA_TYPE_NAME,
            hda_file_name=out_hda_path,
            description=HDA_LABEL,
            min_num_inputs=1,
            max_num_inputs=1,
            ignore_external_references=True,
            change_node_type=True,
            create_backup=False,
        )
        defn = hda_node.type().definition()
        # Wire up parameters and Python module.
        defn.setParmTemplateGroup(_build_param_template_group())
        defn.addSection("PythonModule", PYTHON_MODULE_TEMPLATE)
        defn.setExtraInfo(HDA_DESCRIPTION)
        # Make the PythonModule accessible via hou.phm() inside callbacks.
        opts = defn.options()
        opts.setSaveCachedCode(False)
        defn.setOptions(opts)
        defn.save(out_hda_path, hda_node, opts)
    finally:
        try:
            hda_node.destroy()
        except Exception:
            pass
        try:
            seed.destroy()
        except Exception:
            pass

    # Reinstall so the rest of the session can use it immediately.
    hou.hda.installFile(out_hda_path)
    return out_hda_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: hython install_hda.py /path/to/output.hda")
        sys.exit(1)
    p = install_hda(sys.argv[1])
    print("Installed HDA: {}".format(p))
