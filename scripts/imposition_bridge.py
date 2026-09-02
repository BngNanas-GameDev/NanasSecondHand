"""
Bridge ke C:/ImpositionTool/ImpositionTool.exe — headless core.engine.impose_pdf
Dipakai AI untuk memilih file di Input dan impose ke Impose.
"""
import pathlib, sys, tempfile, types, traceback, json

TOOL = pathlib.Path("C:/ImpositionTool/ImpositionTool.exe")

def _load_engine():
    from PyInstaller.archive.readers import CArchiveReader
    from PyInstaller.loader.pyimod01_archive import ZlibArchiveReader as ZAR
    r = CArchiveReader(str(TOOL))
    data = r.extract("PYZ.pyz")
    tmp = pathlib.Path(tempfile.gettempdir()) / "nanas_pyz.pyz"
    tmp.write_bytes(data)
    z = ZAR(str(tmp))
    def load(name):
        if name in sys.modules:
            return sys.modules[name]
        try:
            code = z.extract(name)
        except KeyError:
            return None
        if code is None:
            m = types.ModuleType(name); m.__path__=[]; sys.modules[name]=m; return m
        m = types.ModuleType(name); m.__file__=f"<pyz:{name}>"
        par = name.rpartition(".")[0]
        if par and par not in sys.modules:
            load(par)
        sys.modules[name]=m
        try:
            exec(code, m.__dict__)
        except ModuleNotFoundError as e:
            miss = e.name
            if miss and miss not in sys.modules:
                try:
                    c2 = z.extract(miss)
                    if c2 is not None:
                        mm = types.ModuleType(miss); mm.__file__=f"<pyz:{miss}>"
                        p2 = miss.rpartition(".")[0]
                        if p2 and p2 not in sys.modules: load(p2)
                        sys.modules[miss]=mm
                        exec(c2, mm.__dict__)
                    else:
                        sys.modules[miss]=types.ModuleType(miss); sys.modules[miss].__path__=[]
                except: pass
                exec(code, m.__dict__)
        return m
    for n in ["config","config.constants","core","core.utils","ui","ui.labels","ui.log_panel","core.engine"]:
        load(n)
    return z

def get_presets():
    _load_engine()
    import config.constants as cc
    return cc.PRESET_SIZES

def impose_file(input_pdf, output_pdf, preset=None):
    preset = preset or {}
    _load_engine()
    import core.engine as eng, config.constants as cc
    sheet = preset.get("sheet", "A3+ Full (32.5x48.7cm)")
    # resolve sheet
    ps = cc.PRESET_SIZES
    if sheet in ps:
        sheet_cfg = ps[sheet]
        if sheet_cfg == "custom":
            sheet_cfg = ((320,480),(320,480))
    else:
        sheet_cfg = ps["A3+ Full (32.5x48.7cm)"]

    # handle env dev mode to bypass license
    import os
    if preset.get("dev_mode", True):
        os.environ["IMPOSITION_DEV_MODE"]="1"

    # label auto: pakai nama asli file full (jangan dipotong), auto hide jika full 32x48
    readable = preset.get("label", "")
    if not readable:
        readable = pathlib.Path(input_pdf).name  # nama asli full dengan .pdf, jangan dipotong
    # normalisasi repeat_mode: collate-cut(11) -> collate-cut-repeat + repeat_n=11
    rm = str(preset.get("repeat_mode","repeat")).lower().strip()
    repeat_n = 1
    import re as _re
    m_cc = _re.match(r"collate-cut\((\d+)\)", rm)
    if m_cc:
        repeat_n = int(m_cc.group(1))
        rm = "collate-cut-repeat" if repeat_n > 1 else "collate-cut"
    # map varian kapital
    _rm_map = {"repeat":"repeat","booklet":"booklet","collate-cut":"collate-cut","unique":"unique","repeat mode":"repeat","1":"repeat","repeat;":"repeat"}
    rm = _rm_map.get(rm, rm)
    if rm not in ("repeat","booklet","booklet-unique","unique","collate-cut","collate-cut-repeat","unique-repeat-n"):
        rm = "repeat"
    kwargs = dict(
        input_pdf=str(input_pdf),
        output_pdf=str(output_pdf),
        sheet_size_config=sheet_cfg,
        bleed_mm=float(preset.get("bleed_mm",3)),
        mark_len_mm=float(preset.get("mark_len_mm",5)),
        mode=str(preset.get("mode","crop" if preset.get("bleed_mm")==2 else "normal")).lower(),
        repeat_mode=rm,
        duplex=bool(preset.get("duplex","1s") in ("2s","dr")),
        label=readable,
        line_color=str(preset.get("line_color","gray" if preset.get("mode")=="crop" else "black")),
        line_width=0.25,
        inner_crop=bool(preset.get("inner_crop",True if preset.get("mode")=="crop" else False)),
        label_position=preset.get("label_position","auto"),
        repeat_n=repeat_n,
        repeat_sort="auto",
        page_flip=False,
        label_font_size=8,
        bleed_on=bool(preset.get("bleed_on",True)),
        allow_oversize=False,
        same_front_back=False,
        scale_type="normal",
        scale_target_w_mm=0,
        scale_target_h_mm=0,
        scale_pct=100,
        scale_orientation="auto",
        crop_margin_mm=0,
        progress_callback=lambda p: None,
        log_callback=lambda *a: print(a),
    )
    pathlib.Path(output_pdf).parent.mkdir(parents=True, exist_ok=True)
    print(f"[Bridge] repeat_mode={rm} repeat_n={repeat_n} duplex={kwargs.get('duplex')} mode={kwargs.get('mode')}")
    eng.impose_pdf(**kwargs)
    return True
