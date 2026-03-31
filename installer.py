#!/usr/bin/env python3
"""
Setup wizard: download whisper.cpp binaries (Windows) or locate a local build,
download GGML models, and write config.ini (only when the user finishes the final step).

URLs mirror upstream:
  https://github.com/ggml-org/whisper.cpp/blob/master/models/download-ggml-model.sh
Releases API: https://github.com/ggml-org/whisper.cpp/releases
"""

from __future__ import annotations

import configparser
import os
import platform
import shutil
import sys
import tempfile
import threading
import zipfile
from typing import Callable, Optional

import requests

# GGML model IDs (same set as upstream download-ggml-model.sh)
GGML_MODELS = """
tiny tiny.en tiny-q5_1 tiny.en-q5_1 tiny-q8_0
base base.en base-q5_1 base.en-q5_1 base-q8_0
small small.en small.en-tdrz small-q5_1 small.en-q5_1 small-q8_0
medium medium.en medium-q5_0 medium.en-q5_0 medium-q8_0
large-v1 large-v2 large-v2-q5_0 large-v2-q8_0
large-v3 large-v3-q5_0 large-v3-turbo large-v3-turbo-q5_0 large-v3-turbo-q8_0
""".split()

HF_GGML_BASE = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
HF_TDRZ_BASE = "https://huggingface.co/akashmjn/tinydiarize-whisper.cpp/resolve/main"

GITHUB_RELEASES_API = "https://api.github.com/repos/ggml-org/whisper.cpp/releases"

WHISPER_MODELS_README = (
    "https://github.com/ggml-org/whisper.cpp/blob/master/models/README.md"
)


INTRO_TEXT = (
    "This wizard finishes first-time setup for WhisperType.\n\n"
    "You need (1) a whisper.cpp server binary (whisper-server), and "
    "(2) at least one GGML model file (.bin) on disk.\n\n"
    "Step 1: choose how to get the binary (Windows can download a release zip). "
    "Step 2: set the models folder; download models here if needed, or skip if you already have .bin files. "
    "Step 3: pick the default model WhisperType starts with. "
    "Nothing is written to config.ini until you click Save on the last step — when every requirement is met."
)


MODEL_GUIDE_TEXT = (
    "Whisper.cpp loads OpenAI Whisper weights converted to GGML format (files named "
    "ggml-<variant>.bin).\n\n"
    "If you speak only English, ggml-small.en.bin or ggml-base.en.bin are good starting points: "
    "reasonable speed on CPU with good quality. Multilingual checkpoints drop the .en part "
    "(e.g. ggml-small.bin).\n\n"
    "Quantized builds (suffixes like -q5_0, -q5_1, -q8_0) are smaller and use less memory; "
    "expect a small accuracy hit versus full-precision models. They run on the same CPU/GPU "
    "backends as non-quantized GGML models—no special hardware is required for the quantization "
    "format itself.\n\n"
    "More detail: " + WHISPER_MODELS_README
)


def config_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def default_models_dir_near_exe(exe_path: str) -> str:
    """`<parent of whisper-server>/models` regardless of whether the exe exists yet."""
    if not exe_path:
        return ""
    resolved = shutil.which(exe_path) or exe_path
    return os.path.join(os.path.dirname(os.path.abspath(resolved)), "models")


def default_install_root() -> str:
    sysname = platform.system().lower()
    if sysname == "windows":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "whisper.cpp")
    if sysname == "darwin":
        return os.path.expanduser("~/Library/Application Support/whisper.cpp")
    return os.path.expanduser("~/.local/share/whisper.cpp")


def list_bin_models(models_dir: str) -> list[str]:
    """Filenames of .bin present in models_dir (sorted)."""
    if not models_dir or not os.path.isdir(models_dir):
        return []
    try:
        return sorted(
            f for f in os.listdir(models_dir) if f.endswith(".bin") and os.path.isfile(os.path.join(models_dir, f))
        )
    except OSError:
        return []


def pick_suggested_default(bins: list[str], previous: str) -> str:
    if previous in bins:
        return previous
    for candidate in (
        "ggml-base.en.bin",
        "ggml-small.en.bin",
        "ggml-tiny.en.bin",
        "ggml-base.bin",
        "ggml-small.bin",
    ):
        if candidate in bins:
            return candidate
    return bins[0] if bins else ""


def parse_server_command(cmd_template: str) -> Optional[str]:
    """First token of expanded command = server executable path."""
    import shlex

    try:
        filled = cmd_template.format(
            model_path="__model__",
            language="en",
            port="7777",
        )
    except (KeyError, ValueError):
        return None
    expanded = os.path.expanduser(os.path.expandvars(filled))
    posix = os.name != "nt"
    try:
        parts = shlex.split(expanded, posix=posix)
    except ValueError:
        return None
    if not parts:
        return None
    return parts[0]


def server_executable_ok(cmd_template: str) -> bool:
    path = parse_server_command(cmd_template)
    if not path:
        return False
    if os.path.isfile(path):
        return True
    return shutil.which(path) is not None


def models_environment_ok(cfg: configparser.ConfigParser) -> bool:
    raw = cfg.get("Models", "models_dir", fallback="", raw=True).strip()
    models_dir = os.path.expanduser(os.path.expandvars(raw))
    if not models_dir or not os.path.isdir(models_dir):
        return False
    default_model = cfg.get("Models", "default_model", fallback="").strip()
    if not default_model:
        return False
    return os.path.isfile(os.path.join(models_dir, default_model))


def environment_ok(cfg: configparser.ConfigParser) -> bool:
    if not cfg.has_section("Server") or not cfg.has_section("Models"):
        return False
    cmd = cfg.get("Server", "command", fallback="", raw=True).strip()
    if not cmd or not server_executable_ok(cmd):
        return False
    return models_environment_ok(cfg)


def describe_environment_gaps(cfg: configparser.ConfigParser) -> list[str]:
    """Human-readable reasons setup is incomplete (mirrors :func:`environment_ok`)."""
    msgs: list[str] = []
    if not cfg.has_section("Server"):
        msgs.append("config has no [Server] section")
        return msgs
    cmd = cfg.get("Server", "command", fallback="", raw=True).strip()
    if not cmd:
        msgs.append("Server.command is empty")
    elif not server_executable_ok(cmd):
        msgs.append("whisper-server from Server.command is missing or not on PATH")
    if not cfg.has_section("Models"):
        msgs.append("config has no [Models] section")
        return msgs
    raw = cfg.get("Models", "models_dir", fallback="", raw=True).strip()
    models_dir = os.path.expanduser(os.path.expandvars(raw))
    if not models_dir:
        msgs.append("Models.models_dir is not set")
    elif not os.path.isdir(models_dir):
        msgs.append("Models.models_dir is not an existing directory")
    else:
        bins = list_bin_models(models_dir)
        if not bins:
            msgs.append("no .bin model files in Models.models_dir")
        else:
            dm = cfg.get("Models", "default_model", fallback="", raw=True).strip()
            if not dm:
                msgs.append("Models.default_model is not set")
            elif not os.path.isfile(os.path.join(models_dir, dm)):
                msgs.append(f"Models.default_model not found ({dm})")
    return msgs


def hf_ggml_url(model: str) -> str:
    if "tdrz" in model:
        return f"{HF_TDRZ_BASE}/ggml-{model}.bin"
    return f"{HF_GGML_BASE}/ggml-{model}.bin"


def fetch_latest_releases(max_releases: int = 8) -> list[dict]:
    r = requests.get(
        GITHUB_RELEASES_API,
        params={"per_page": max_releases},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def pick_windows_asset(assets: list[dict], prefer_blas: bool) -> Optional[dict]:
    """Prefer whisper-bin-x64.zip or whisper-blas-bin-x64.zip."""
    is_64 = sys.maxsize > 2**32
    if platform.system().lower() != "windows":
        return None
    if is_64:
        preferred = "whisper-blas-bin-x64.zip" if prefer_blas else "whisper-bin-x64.zip"
        alt = "whisper-bin-x64.zip" if prefer_blas else "whisper-blas-bin-x64.zip"
    else:
        preferred = "whisper-blas-bin-Win32.zip" if prefer_blas else "whisper-bin-Win32.zip"
        alt = "whisper-bin-Win32.zip" if prefer_blas else "whisper-blas-bin-Win32.zip"
    for n in (preferred, alt):
        for a in assets:
            if a["name"] == n:
                return a
    for a in assets:
        if a["name"].endswith("-x64.zip") and "whisper-" in a["name"]:
            return a
    return None


def find_whisper_server_under(root: str) -> Optional[str]:
    """Locate whisper-server / whisper-server.exe under extracted tree."""
    exe = "whisper-server.exe" if platform.system().lower() == "windows" else "whisper-server"
    for dirpath, _dirnames, filenames in os.walk(root):
        if exe in filenames:
            return os.path.join(dirpath, exe)
    return None


def download_file_cancellable(
    url: str,
    dest: str,
    progress: Optional[Callable[[int, int], None]] = None,
    cancel: Optional[threading.Event] = None,
) -> None:
    """Stream download; set cancel to abort. Raises InterruptedError if cancelled."""
    tmp = dest + ".part"
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0) or 0)
            done = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=256 * 1024):
                    if cancel is not None and cancel.is_set():
                        raise InterruptedError("Download cancelled.")
                    if chunk:
                        f.write(chunk)
                        done += len(chunk)
                        if progress is not None:
                            progress(done, total)
        if cancel is not None and cancel.is_set():
            raise InterruptedError("Download cancelled.")
        os.replace(tmp, dest)
    finally:
        if cancel is not None and cancel.is_set():
            for p in (tmp, dest):
                try:
                    if os.path.isfile(p):
                        os.remove(p)
                except OSError:
                    pass
        elif os.path.isfile(tmp) and not os.path.isfile(dest):
            try:
                os.remove(tmp)
            except OSError:
                pass


def extract_zip(zip_path: str, dest_dir: str, cancel: Optional[threading.Event] = None) -> None:
    if cancel is not None and cancel.is_set():
        raise InterruptedError("Cancelled before extract.")
    with zipfile.ZipFile(zip_path, "r") as z:
        for info in z.infolist():
            if cancel is not None and cancel.is_set():
                raise InterruptedError("Extract cancelled.")
            z.extract(info, dest_dir)


def save_config(path: str, cfg: configparser.ConfigParser) -> None:
    with open(path, "w") as f:
        cfg.write(f)


def build_server_command(exe_path: str) -> str:
    """Uniform template with placeholders expected by whispertype."""
    import shlex

    if os.name == "nt":
        exe_path = os.path.normpath(exe_path)
        q = f'"{exe_path}"' if " " in exe_path else exe_path
    else:
        q = shlex.quote(exe_path)
    return f"{q} -m {{model_path}} -l {{language}} --port {{port}}"


def run_setup_wizard(
    final_config_path: str,
    cfg: configparser.ConfigParser,
    *,
    show_setup_gaps: bool = False,
    from_template: bool = False,
) -> bool:
    """Tkinter wizard; returns True if config was saved successfully.

    Edits are accumulated in a temporary file and moved to ``final_config_path`` only
    when the user clicks Save. If ``show_setup_gaps`` is True (existing destination
    ``config.ini`` was read), a banner lists what still fails environment checks.
    """
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    draft_fd, draft_path = tempfile.mkstemp(prefix="whispertypesetup-", suffix=".ini")
    os.close(draft_fd)
    draft_holder: dict[str, Optional[str]] = {"path": draft_path}
    try:
        save_config(draft_path, cfg)
    except OSError as e:
        try:
            if os.path.isfile(draft_path):
                os.remove(draft_path)
        except OSError:
            pass
        print(f"Could not write setup draft: {e}", file=sys.stderr)
        return False

    root = tk.Tk()
    root.title("WhisperType — whisper.cpp setup")
    # Initial size + min size; pack order pins the action bar to the bottom (see below).
    root.geometry("780x800")
    root.minsize(640, 750)

    state = {"cancelled": False, "saved": False}
    download_busy = {"active": False}
    download_cancel = threading.Event()

    plat = platform.system().lower()
    install_var = tk.StringVar(value=default_install_root())
    exe_var = tk.StringVar(value="")
    binary_mode = tk.StringVar(value="download" if plat == "windows" else "existing")
    releases_var: list[dict] = []
    asset_var = tk.StringVar(value="")
    prefer_blas = tk.BooleanVar(value=False)
    release_choice = tk.StringVar(value="")

    status_var = tk.StringVar(value="Ready.")
    progress_label_var = tk.StringVar(value="")
    progress_value = tk.DoubleVar(value=0.0)
    gaps_var = tk.StringVar(value="")

    models_dir_var = tk.StringVar(value="")
    default_model_var = tk.StringVar(value="")
    models_autofill = tk.BooleanVar(value=True)

    if not from_template:
        if cfg.has_option("Paths", "whisper_install_dir"):
            wd = os.path.expanduser(
                os.path.expandvars(cfg.get("Paths", "whisper_install_dir", fallback="", raw=True))
            )
            if wd:
                install_var.set(wd)
        if cfg.has_option("Models", "models_dir"):
            md = os.path.expanduser(os.path.expandvars(cfg.get("Models", "models_dir", fallback="", raw=True)))
            if md:
                models_dir_var.set(md)
                models_autofill.set(False)

    prev_default = ""
    if cfg.has_option("Models", "default_model"):
        prev_default = cfg.get("Models", "default_model", raw=True).strip()

    wizard_body = ttk.Frame(root)
    step0 = ttk.Frame(wizard_body)
    step1 = ttk.Frame(wizard_body)
    step2 = ttk.Frame(wizard_body)
    step3 = ttk.Frame(wizard_body)
    step_num = tk.IntVar(value=0)

    # —— Step 1: binary ——
    frm = ttk.Frame(step1, padding=4)
    frm.pack(fill=tk.BOTH, expand=True)

    mode_fr = ttk.LabelFrame(frm, text="How do you want to get whisper-server?", padding=6)
    mode_fr.pack(fill=tk.X, pady=(0, 8))

    rb_download = ttk.Radiobutton(
        mode_fr,
        text="Download a pre-built whisper.cpp (official GitHub release zips — Windows only)",
        variable=binary_mode,
        value="download",
        command=lambda: repack_download_only_widgets(),
    )
    rb_download.pack(anchor=tk.W)
    rb_existing = ttk.Radiobutton(
        mode_fr,
        text="I already have whisper-server — I will choose the file path",
        variable=binary_mode,
        value="existing",
        command=lambda: repack_download_only_widgets(),
    )
    rb_existing.pack(anchor=tk.W)

    if plat != "windows":
        rb_download.state(["disabled"])
        binary_mode.set("existing")

    install_row = ttk.Frame(frm)
    install_label = ttk.Label(
        install_row,
        text="Folder for downloaded build (zip extracts here):",
    )
    install_label.pack(anchor=tk.W)
    row = ttk.Frame(install_row)
    row.pack(fill=tk.X)
    install_entry = ttk.Entry(row, textvariable=install_var)
    install_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Button(
        row,
        text="Browse…",
        command=lambda: install_var.set(
            filedialog.askdirectory(initialdir=install_var.get() or os.path.expanduser("~"))
            or install_var.get()
        ),
    ).pack(side=tk.LEFT, padx=4)

    rel_frame = ttk.LabelFrame(frm, text="GitHub release download", padding=6)

    ttk.Label(rel_frame, text="Release:").grid(row=0, column=0, sticky=tk.W)
    release_combo = ttk.Combobox(rel_frame, textvariable=release_choice, width=42)
    release_combo.grid(row=0, column=1, sticky=tk.EW, padx=4)
    ttk.Label(rel_frame, text="Zip asset:").grid(row=1, column=0, sticky=tk.W)
    asset_combo = ttk.Combobox(rel_frame, textvariable=asset_var, width=42)
    asset_combo.grid(row=1, column=1, sticky=tk.EW, padx=4)
    rel_frame.columnconfigure(1, weight=1)
    ttk.Checkbutton(
        rel_frame,
        text="Prefer OpenBLAS build (larger, may be faster on CPU)",
        variable=prefer_blas,
    ).grid(row=2, column=1, sticky=tk.W)

    btn_download_binary = ttk.Button(rel_frame, text="Download & extract")
    btn_download_binary.grid(row=3, column=1, sticky=tk.W, pady=6)

    exe_fr = ttk.LabelFrame(frm, text="whisper-server executable", padding=6)
    ttk.Label(
        exe_fr,
        text="Path to whisper-server (or whisper-server.exe). Required before the models steps.",
        wraplength=640,
    ).pack(anchor=tk.W)
    row2 = ttk.Frame(exe_fr)
    row2.pack(fill=tk.X, pady=(4, 0))
    ttk.Entry(row2, textvariable=exe_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Button(
        row2,
        text="Browse…",
        command=lambda: exe_var.set(
            filedialog.askopenfilename(
                title="Select whisper-server",
                initialdir=install_var.get() or os.path.expanduser("~"),
            )
            or exe_var.get()
        ),
    ).pack(side=tk.LEFT, padx=4)

    linux_box = ttk.Frame(frm)
    if plat != "windows":
        ttk.Label(
            linux_box,
            text=(
                "On Linux/macOS, official release .zips target Windows. Build locally, e.g.:\n"
                "cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j\n"
                "Binary is often build/bin/whisper-server — use Browse above."
            ),
            wraplength=640,
            foreground="gray",
        ).pack(anchor=tk.W, pady=(8, 0))
        doc = "https://github.com/ggml-org/whisper.cpp#quick-start"

        def open_doc():
            import webbrowser

            webbrowser.open(doc)

        ttk.Button(linux_box, text="Open whisper.cpp build docs", command=open_doc).pack(anchor=tk.W, pady=4)

    # —— Step 2: models ——
    mf = ttk.Frame(step2, padding=4)
    mf.pack(fill=tk.BOTH, expand=True)

    guide_fr = ttk.LabelFrame(mf, text="About GGML models and quantization", padding=6)
    guide_fr.pack(fill=tk.X, expand=False, pady=(0, 8))
    guide_tx = tk.Text(guide_fr, height=8, wrap=tk.WORD, font=("TkDefaultFont", 9))
    guide_sy = ttk.Scrollbar(guide_fr, command=guide_tx.yview)
    guide_tx.configure(yscrollcommand=guide_sy.set)
    guide_sy.pack(side=tk.RIGHT, fill=tk.Y)
    guide_tx.pack(side=tk.LEFT, fill=tk.X, expand=False)
    guide_tx.insert(tk.END, MODEL_GUIDE_TEXT)
    guide_tx.configure(state=tk.DISABLED)

    def open_models_readme():
        import webbrowser

        webbrowser.open(WHISPER_MODELS_README)

    ttk.Button(mf, text="Open models README in browser", command=open_models_readme).pack(anchor=tk.W)

    ttk.Label(mf, text="Models directory (must contain at least one .bin before Save):").pack(
        anchor=tk.W, pady=(10, 0)
    )
    rowm = ttk.Frame(mf)
    rowm.pack(fill=tk.X)
    models_entry = ttk.Entry(rowm, textvariable=models_dir_var)
    models_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def browse_models_dir():
        picked = filedialog.askdirectory(
            initialdir=models_dir_var.get() or install_var.get(),
        )
        if picked:
            models_dir_var.set(picked)
            models_autofill.set(False)

    ttk.Button(rowm, text="Browse…", command=browse_models_dir).pack(side=tk.LEFT, padx=4)

    def use_models_near_exe():
        ex = exe_var.get().strip()
        if not ex:
            messagebox.showinfo("Models", "Set a whisper-server path on the binary step first.")
            return
        near = default_models_dir_near_exe(ex)
        models_dir_var.set(near)
        models_autofill.set(False)

    ttk.Button(
        rowm,
        text="Default (next to binary)",
        command=use_models_near_exe,
    ).pack(side=tk.LEFT, padx=(4, 0))

    ttk.Label(
        mf,
        text="Select variants to download (Hugging Face — same names as upstream download-ggml-model.sh):",
    ).pack(anchor=tk.W, pady=(8, 0))
    list_frame = ttk.Frame(mf)
    list_frame.pack(fill=tk.X, expand=False, pady=4)
    scroll = ttk.Scrollbar(list_frame)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    lb = tk.Listbox(
        list_frame,
        selectmode=tk.EXTENDED,
        yscrollcommand=scroll.set,
        height=8,
        width=48,
    )
    lb.pack(side=tk.LEFT, fill=tk.X, expand=False)
    scroll.config(command=lb.yview)
    for m in GGML_MODELS:
        lb.insert(tk.END, m)

    btn_download_models = ttk.Button(mf, text="Download selected model files")
    btn_download_models.pack(anchor=tk.W, pady=4)

    ttk.Label(
        mf,
        text=(
            "If you already have .bin files in this folder, you do not need to download — "
            "click Next to choose the default model."
        ),
        wraplength=680,
        foreground="gray",
    ).pack(anchor=tk.W, pady=(6, 0))

    # —— Step 3: default model only ——
    s3 = ttk.Frame(step3, padding=4)
    s3.pack(fill=tk.BOTH, expand=True)
    ttk.Label(
        s3,
        text="Default model for WhisperType (must select one before Save):",
    ).pack(anchor=tk.W)
    ttk.Label(
        s3,
        text="Uses .bin files from the models folder you set in the previous step.",
        wraplength=680,
        foreground="gray",
    ).pack(anchor=tk.W, pady=(0, 8))
    default_combo = ttk.Combobox(s3, textvariable=default_model_var, state="readonly", width=64)
    default_combo.pack(fill=tk.X, pady=(0, 4))
    ttk.Button(
        s3,
        text="Refresh list from folder",
        command=lambda: refresh_default_model_choices(),
    ).pack(anchor=tk.W)

    # —— Step 0: help only ——
    z0 = ttk.Frame(step0, padding=4)
    z0.pack(fill=tk.BOTH, expand=True)
    ttk.Label(z0, text=INTRO_TEXT, wraplength=680, justify=tk.LEFT).pack(anchor=tk.W)

    # —— progress area (packed with side=BOTTOM when active — above the action bar) ——
    progress_fr = ttk.LabelFrame(root, text="Active download", padding=6)
    progress_bar = ttk.Progressbar(
        progress_fr,
        variable=progress_value,
        maximum=100.0,
        mode="determinate",
    )
    progress_bar.pack(fill=tk.X)
    ttk.Label(progress_fr, textvariable=progress_label_var).pack(anchor=tk.W, pady=(4, 0))
    btn_cancel_dl = ttk.Button(progress_fr, text="Cancel download")

    def set_download_ui(active: bool, indeterminate: bool = False) -> None:
        download_busy["active"] = active
        if active:
            download_cancel.clear()
            progress_fr.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=4)
            if indeterminate:
                progress_bar.configure(mode="indeterminate")
                progress_bar.start(12)
            else:
                progress_bar.stop()
                progress_bar.configure(mode="determinate")
            btn_cancel_dl.pack(anchor=tk.W, pady=(6, 0))
            save_btn.state(["disabled"])
            next_btn.state(["disabled"])
            back_btn.state(["disabled"])
            btn_download_models.state(["disabled"])
            btn_download_binary.state(["disabled"])
        else:
            progress_bar.stop()
            progress_fr.pack_forget()
            btn_cancel_dl.pack_forget()
            progress_value.set(0)
            progress_label_var.set("")
            btn_download_models.state(["!disabled"])
            btn_download_binary.state(["!disabled"])
            refresh_nav()

    def on_cancel_download():
        download_cancel.set()
        progress_label_var.set("Cancelling…")

    btn_cancel_dl.configure(command=on_cancel_download)
    progress_fr.pack_forget()

    # —— bottom bar (pack BOTTOM first so it stays on-screen) ——
    bar = ttk.Frame(root, padding=(8, 4, 8, 8))
    status_label = ttk.Label(bar, textvariable=status_var, wraplength=680, justify=tk.LEFT)
    status_label.pack(fill=tk.X, anchor=tk.W, pady=(0, 6))
    btn_row = ttk.Frame(bar)
    btn_row.pack(fill=tk.X)
    save_btn = ttk.Button(btn_row, text="Save configuration")
    next_btn = ttk.Button(btn_row, text="Next →")
    back_btn = ttk.Button(btn_row, text="← Back")
    cancel_wiz_btn = ttk.Button(btn_row, text="Cancel wizard", command=lambda: on_cancel())
    cancel_wiz_btn.pack(side=tk.RIGHT)
    save_btn.pack(side=tk.RIGHT, padx=(0, 8))
    next_btn.pack(side=tk.RIGHT, padx=(0, 8))
    back_btn.pack(side=tk.RIGHT, padx=(0, 8))

    def _sync_status_wrap(_evt=None) -> None:
        try:
            w = bar.winfo_width()
            if w > 48:
                status_label.configure(wraplength=max(280, w - 24))
        except tk.TclError:
            pass

    bar.bind("<Configure>", _sync_status_wrap)
    bar.pack(side=tk.BOTTOM, fill=tk.X)

    if show_setup_gaps:
        gaps_fr = ttk.LabelFrame(root, text="Your config.ini still needs", padding=8)
        gaps_label = ttk.Label(gaps_fr, textvariable=gaps_var, justify=tk.LEFT, wraplength=680)
        gaps_label.pack(anchor=tk.W, fill=tk.X)

        def _sync_gaps_wrap(_evt=None) -> None:
            try:
                w = gaps_fr.winfo_width()
                if w > 48:
                    gaps_label.configure(wraplength=max(280, w - 24))
            except tk.TclError:
                pass

        gaps_fr.bind("<Configure>", _sync_gaps_wrap)
        gaps_fr.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 0))

    wizard_body.pack(side=tk.TOP, expand=True, fill=tk.BOTH, padx=8, pady=4)
    step0.pack(fill=tk.BOTH, expand=True)

    # —— logic ——
    def resolved_models_dir() -> str:
        return os.path.expanduser(os.path.expandvars(models_dir_var.get().strip()))

    def resolved_exe() -> str:
        return exe_var.get().strip()

    def exe_is_valid() -> bool:
        p = resolved_exe()
        if not p:
            return False
        if os.path.isfile(p):
            return True
        return shutil.which(p) is not None

    def refresh_default_model_choices():
        mdir = resolved_models_dir()
        bins = list_bin_models(mdir)
        default_combo.configure(values=bins)
        if not bins:
            default_model_var.set("")
            default_combo.state(["disabled"])
        else:
            default_combo.state(["!disabled"])
            cur = default_model_var.get().strip()
            pick = pick_suggested_default(bins, prev_default or cur or "")
            if cur in bins:
                pick = cur
            default_model_var.set(pick)
        refresh_nav()

    def requirements_met() -> bool:
        if not exe_is_valid():
            return False
        mdir = resolved_models_dir()
        if not mdir or not os.path.isdir(mdir):
            return False
        bins = list_bin_models(mdir)
        if not bins:
            return False
        dm = default_model_var.get().strip()
        if not dm or dm not in bins:
            return False
        return True

    def wizard_gap_messages() -> list[str]:
        msgs: list[str] = []
        if not exe_is_valid():
            msgs.append("whisper-server executable is missing or not on PATH")
        mdir = resolved_models_dir()
        st = models_dir_var.get().strip()
        if not st:
            msgs.append("models directory is not set")
        elif not os.path.isdir(mdir):
            msgs.append("models directory does not exist or is not a folder")
        else:
            bins = list_bin_models(mdir)
            if not bins:
                msgs.append("no .bin model files in the models directory")
            else:
                dm = default_model_var.get().strip()
                if not dm or dm not in bins:
                    msgs.append("default WhisperType model is not selected or not in the folder")
        return msgs

    def show_step(which: int) -> None:
        step_num.set(which)
        step0.pack_forget()
        step1.pack_forget()
        step2.pack_forget()
        step3.pack_forget()
        if which == 0:
            step0.pack(fill=tk.BOTH, expand=True)
        elif which == 1:
            step1.pack(fill=tk.BOTH, expand=True)
        elif which == 2:
            step2.pack(fill=tk.BOTH, expand=True)
        else:
            step3.pack(fill=tk.BOTH, expand=True)
        refresh_nav()

    def go_next() -> None:
        if download_busy["active"]:
            return
        s = step_num.get()
        if s == 0:
            show_step(1)
            return
        if s == 1:
            if not exe_is_valid():
                messagebox.showwarning("Binary", "Choose a valid whisper-server file before continuing.")
                return
            if models_autofill.get():
                near = default_models_dir_near_exe(resolved_exe())
                if near:
                    models_dir_var.set(near)
            show_step(2)
            refresh_default_model_choices()
            return
        if s == 2:
            mdir = resolved_models_dir()
            if not mdir or not os.path.isdir(mdir):
                messagebox.showwarning(
                    "Models",
                    "Choose an existing models folder before continuing (use Browse or the default next to the binary).",
                )
                return
            show_step(3)
            refresh_default_model_choices()
            return

    def go_back() -> None:
        if download_busy["active"]:
            return
        s = step_num.get()
        if s == 0:
            return
        show_step(s - 1)

    def refresh_nav() -> None:
        if download_busy["active"]:
            save_btn.state(["disabled"])
            next_btn.state(["disabled"])
            back_btn.state(["disabled"])
            return
        s = step_num.get()
        if s == 0:
            back_btn.state(["disabled"])
            next_btn.state(["!disabled"])
            save_btn.state(["disabled"])
            status_var.set("Welcome — click Next to set up whisper-server.")
        elif s == 1:
            back_btn.state(["!disabled"])
            next_btn.state(["!disabled"] if exe_is_valid() else ["disabled"])
            save_btn.state(["disabled"])
            if exe_is_valid():
                status_var.set("Binary step done — Next: models folder (config not saved yet).")
            else:
                status_var.set("Step 1: set whisper-server, then click Next.")
        elif s == 2:
            back_btn.state(["!disabled"])
            mdir = resolved_models_dir()
            next_ok = bool(mdir and os.path.isdir(mdir))
            next_btn.state(["!disabled"] if next_ok else ["disabled"])
            save_btn.state(["disabled"])
            if not next_ok:
                status_var.set(
                    "Step 2: set the models directory — downloading here is optional if .bin files already exist."
                )
            else:
                nbin = len(list_bin_models(mdir))
                if nbin:
                    status_var.set(
                        f"Models folder OK ({nbin} .bin). Next to choose default model, or add more via download."
                    )
                else:
                    status_var.set(
                        "Step 2: optional download — or add .bin files to this folder, then Next to select default."
                    )
        else:
            back_btn.state(["!disabled"])
            next_btn.state(["disabled"])
            if requirements_met():
                save_btn.state(["!disabled"])
                status_var.set("Step 3: all set — Save writes config.ini.")
            else:
                save_btn.state(["disabled"])
                parts = []
                mdir = resolved_models_dir()
                if not mdir or not os.path.isdir(mdir):
                    parts.append("valid models directory")
                elif not list_bin_models(mdir):
                    parts.append("at least one .bin (go back to download or copy files)")
                elif (
                    not default_model_var.get().strip()
                    or default_model_var.get() not in list_bin_models(mdir)
                ):
                    parts.append("choose a default model from the list")
                status_var.set("Step 3: still need: " + ", ".join(parts) + ".")
        if show_setup_gaps:
            gm = wizard_gap_messages()
            if gm:
                gaps_var.set("Still missing:\n" + "\n".join(f"• {x}" for x in gm))
            else:
                gaps_var.set(
                    "Nothing left to fix for server + models — finish the steps and click Save to write config.ini."
                )

    next_btn.configure(command=go_next)
    back_btn.configure(command=go_back)

    def repack_download_only_widgets() -> None:
        install_row.pack_forget()
        rel_frame.pack_forget()
        exe_fr.pack_forget()
        try:
            linux_box.pack_forget()
        except tk.TclError:
            pass
        if plat == "windows" and binary_mode.get() == "download":
            install_row.pack(fill=tk.X, pady=(4, 0), after=mode_fr)
            rel_frame.pack(fill=tk.X, pady=8, after=install_row)
            exe_fr.pack(fill=tk.X, pady=(12, 0), after=rel_frame)
            if not releases_var:
                load_releases()
        else:
            exe_fr.pack(fill=tk.X, pady=(12, 0), after=mode_fr)
        if plat != "windows":
            linux_box.pack(fill=tk.X, pady=(4, 0), after=exe_fr)
        refresh_nav()

    def load_releases():
        status_var.set("Fetching releases…")
        root.update()

        def work():
            try:
                data = fetch_latest_releases(12)
                root.after(
                    0,
                    lambda: _populate_releases(
                        data, release_combo, release_choice, asset_combo, asset_var
                    ),
                )
            except Exception as e:
                root.after(0, lambda: status_var.set(f"Release fetch failed: {e}"))

        threading.Thread(target=work, daemon=True).start()

    def _populate_releases(data, r_combo, r_var, a_combo, a_var):
        releases_var.clear()
        releases_var.extend(data)
        tags = [d.get("tag_name", "?") for d in data]
        r_combo["values"] = tags
        if tags:
            r_var.set(tags[0])
            _on_release_change()
        status_var.set("Releases loaded.")
        refresh_nav()

    def _on_release_change(*_):
        tag = release_choice.get()
        for d in list(releases_var):
            if d.get("tag_name") == tag:
                zips = [
                    a["name"]
                    for a in d.get("assets", [])
                    if a["name"].endswith(".zip")
                    and "whisper" in a["name"].lower()
                    and "xcframework" not in a["name"].lower()
                    and "jar" not in a["name"].lower()
                ]
                asset_combo["values"] = zips
                pick = pick_windows_asset(d.get("assets", []), prefer_blas.get())
                asset_var.set(pick["name"] if pick else (zips[0] if zips else ""))
                break

    release_combo.bind("<<ComboboxSelected>>", _on_release_change)
    try:
        prefer_blas.trace_add("write", lambda *_: _on_release_change())
    except AttributeError:
        prefer_blas.trace("w", lambda *_: _on_release_change())

    def do_download_binary():
        if plat != "windows" or binary_mode.get() != "download":
            messagebox.showinfo("Setup", "Use “Browse” to select your whisper-server binary.")
            return
        tag = release_choice.get()
        asset_name = asset_var.get()
        if not tag or not asset_name:
            messagebox.showwarning("Setup", "Select a release and zip asset.")
            return
        rel = next((d for d in releases_var if d.get("tag_name") == tag), None)
        if not rel:
            return
        asset = next((a for a in rel.get("assets", []) if a["name"] == asset_name), None)
        if not asset:
            return
        root_dir = install_var.get().strip()
        if not root_dir:
            messagebox.showerror("Setup", "Choose install folder.")
            return
        os.makedirs(root_dir, exist_ok=True)
        url = asset["browser_download_url"]
        zip_path = os.path.join(root_dir, asset_name)

        def prog(done: int, total: int):
            if total:
                pct = min(100.0, 100.0 * done / total)
                root.after(0, lambda: progress_value.set(pct))
                root.after(
                    0,
                    lambda d=done, t=total: progress_label_var.set(
                        f"{asset_name}: {100 * d // t}% ({d // (1024 * 1024)} / {t // (1024 * 1024)} MiB)"
                        if t
                        else f"{asset_name}: …"
                    ),
                )
            else:
                root.after(0, lambda: progress_label_var.set(f"{asset_name}: downloading…"))

        set_download_ui(True, indeterminate=False)

        def work():
            try:
                download_file_cancellable(url, zip_path, progress=prog, cancel=download_cancel)
                root.after(0, lambda: progress_label_var.set("Extracting…"))
                extract_zip(zip_path, root_dir, cancel=download_cancel)
                srv = find_whisper_server_under(root_dir)
                root.after(0, lambda: _after_extract(srv, zip_path))
            except InterruptedError:
                root.after(
                    0,
                    lambda: messagebox.showinfo("Download", "Download cancelled."),
                )
                root.after(0, lambda: status_var.set("Cancelled."))
            except Exception as e:
                root.after(0, lambda: messagebox.showerror("Download", str(e)))
                root.after(0, lambda: status_var.set("Download failed."))
            finally:
                root.after(0, lambda: set_download_ui(False))

        def _after_extract(srv: Optional[str], zp: str):
            if srv:
                exe_var.set(srv)
                if models_autofill.get():
                    near = default_models_dir_near_exe(srv)
                    if near:
                        models_dir_var.set(near)
                messagebox.showinfo("Setup", f"Installed whisper-server:\n{srv}")
            else:
                messagebox.showwarning(
                    "Setup",
                    "Extracted archive but whisper-server.exe was not found.",
                )
            try:
                os.remove(zp)
            except OSError:
                pass
            refresh_nav()

        threading.Thread(target=work, daemon=True).start()

    btn_download_binary.configure(command=do_download_binary)

    def download_selected_models():
        mdir = models_dir_var.get().strip()
        if not mdir:
            messagebox.showerror("Models", "Set models directory.")
            return
        os.makedirs(mdir, exist_ok=True)
        sel = [lb.get(i) for i in lb.curselection()]
        if not sel:
            messagebox.showinfo("Models", "Select at least one model variant in the list.")
            return

        set_download_ui(True, indeterminate=False)

        def work():
            try:
                planned: list[tuple[str, str, str]] = []
                for m in sel:
                    dest = os.path.join(mdir, f"ggml-{m}.bin")
                    if not os.path.isfile(dest):
                        planned.append((hf_ggml_url(m), dest, f"ggml-{m}.bin"))
                if not planned:
                    root.after(0, lambda: messagebox.showinfo("Models", "All selected files already exist."))
                    return

                n_plan = len(planned)
                for idx, (url, dest, label) in enumerate(planned, start=1):

                    def prog(
                        done: int,
                        total: int,
                        *,
                        fi: int = idx,
                        lbl: str = label,
                        n: int = n_plan,
                    ):
                        if total:
                            frac = min(1.0, done / total)
                            overall = 100.0 * (fi - 1 + frac) / n
                            root.after(0, lambda v=overall: progress_value.set(min(100.0, v)))
                            mb_done = done // (1024 * 1024)
                            mb_tot = total // (1024 * 1024)
                            pct = 100 * done // total
                            root.after(
                                0,
                                lambda p=pct, md=mb_done, mt=mb_tot, fii=fi, nn=n, lb=lbl: progress_label_var.set(
                                    f"File {fii}/{nn} — {lb}: {p}% ({md} / {mt} MiB)"
                                ),
                            )
                        else:
                            root.after(
                                0,
                                lambda fii=fi, nn=n, lb=lbl: progress_label_var.set(
                                    f"File {fii}/{nn} — {lb}…"
                                ),
                            )

                    root.after(
                        0,
                        lambda fi=idx, lbl=label, n=n_plan: progress_label_var.set(
                            f"Starting file {fi}/{n}: {lbl}"
                        ),
                    )
                    download_file_cancellable(url, dest, progress=prog, cancel=download_cancel)

                root.after(0, lambda: progress_value.set(100.0))
                root.after(0, lambda: messagebox.showinfo("Models", "Downloads finished."))
                root.after(0, refresh_default_model_choices)
            except InterruptedError:
                root.after(0, lambda: messagebox.showinfo("Models", "Download cancelled."))
            except Exception as e:
                root.after(0, lambda: messagebox.showerror("Models", str(e)))
            finally:
                root.after(0, lambda: set_download_ui(False))
                root.after(0, refresh_nav)

        threading.Thread(target=work, daemon=True).start()

    btn_download_models.configure(command=download_selected_models)

    def apply_save():
        if step_num.get() != 3:
            messagebox.showerror("Setup", "Finish step 3 (default model) before saving.")
            return
        if not requirements_met():
            messagebox.showerror("Setup", "Complete all requirements before saving.")
            return
        exe = resolved_exe()
        mdir = resolved_models_dir()
        inst = install_var.get().strip()
        dm = default_model_var.get().strip()
        if not cfg.has_section("Server"):
            cfg.add_section("Server")
        if not cfg.has_section("Models"):
            cfg.add_section("Models")
        if not cfg.has_section("Paths"):
            cfg.add_section("Paths")
        cfg.set("Server", "command", build_server_command(exe))
        cfg.set("Models", "models_dir", mdir)
        cfg.set("Models", "default_model", dm)
        if inst:
            cfg.set("Paths", "whisper_install_dir", inst)
        dp = draft_holder.get("path")
        if not dp:
            messagebox.showerror("Setup", "Internal error: draft config file missing.")
            return
        save_config(dp, cfg)
        try:
            os.replace(dp, final_config_path)
        except OSError as e:
            messagebox.showerror("Setup", f"Could not save configuration:\n{e}")
            return
        draft_holder["path"] = None
        state["saved"] = True
        messagebox.showinfo("Setup", f"Saved {final_config_path}")
        root.destroy()

    save_btn.configure(command=apply_save)

    def on_cancel():
        if download_busy["active"]:
            if not messagebox.askyesno("Quit", "A download is running. Cancel download and close?"):
                return
            download_cancel.set()
        state["cancelled"] = True
        p = draft_holder.get("path")
        if p and os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass
        draft_holder["path"] = None
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_cancel)

    def _bind_trace(var, cb):
        if hasattr(var, "trace_add"):
            var.trace_add("write", cb)
        else:
            var.trace("w", lambda *_a: cb())

    def on_exe_change():
        if models_autofill.get():
            ex = exe_var.get().strip()
            if ex and os.path.isfile(ex):
                models_dir_var.set(default_models_dir_near_exe(ex))
        refresh_nav()

    _bind_trace(exe_var, lambda *_: root.after_idle(on_exe_change))
    _bind_trace(models_dir_var, lambda *_: root.after_idle(refresh_default_model_choices))
    _bind_trace(default_model_var, lambda *_: root.after_idle(refresh_nav))
    _bind_trace(install_var, lambda *_: root.after_idle(refresh_nav))

    models_entry.bind("<Key>", lambda _e: models_autofill.set(False))

    default_combo.bind("<<ComboboxSelected>>", lambda _e: refresh_nav())

    parsed_exe: Optional[str] = None
    if not from_template and cfg.has_option("Server", "command"):
        raw_cmd = cfg.get("Server", "command", raw=True)
        parsed_exe = parse_server_command(raw_cmd)
        if parsed_exe:
            exe_var.set(parsed_exe)

    repack_download_only_widgets()

    if models_autofill.get() and not models_dir_var.get().strip() and parsed_exe:
        near = default_models_dir_near_exe(parsed_exe)
        if near:
            models_dir_var.set(near)

    refresh_default_model_choices()
    refresh_nav()

    try:
        root.mainloop()
        return state["saved"]
    finally:
        p = draft_holder.get("path")
        if p and os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass
        draft_holder["path"] = None


def main() -> None:
    script = config_dir()
    config_path = (
        os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(script, "config.ini")
    )
    example = os.path.join(script, "config.ini.example")
    dest_exists = os.path.isfile(config_path)
    cfg = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
    if dest_exists:
        cfg.read(config_path)
    elif os.path.isfile(example):
        cfg.read(example)
    else:
        print("Missing config.ini and config.ini.example", file=sys.stderr)
        sys.exit(1)
    ok = run_setup_wizard(config_path, cfg, show_setup_gaps=dest_exists, from_template=not dest_exists)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
