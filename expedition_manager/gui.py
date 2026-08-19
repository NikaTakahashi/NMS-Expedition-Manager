"""Graphical interface for Expedition Manager (tkinter + ttk).

The GUI is a thin front-end over the existing core modules:
  - catalog.build_catalog()   → expedition list
  - sync.sync() / sync.library_status() → downloads + status badges
  - installer.install/uninstall/find_nms_cache_dirs → install tab
  - config.load_config/save_config → settings tab

Threading model: every long-running action (sync, install, uninstall)
runs in a worker thread that pushes ("kind", payload) tuples to a
queue.Queue. The Tk main thread drains the queue with a single
root.after() poller, so widgets are only ever touched from the main
thread.
"""
import queue
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import customize, installer, sync as syncmod
from .catalog import build_catalog
from .config import (CONFIG_FILE, DEFAULT_PREFIX, PROJECT_ROOT,
                     load_config, load_state, save_config, state_dir)
from .sources import SourceError, Sources

APP_TITLE = "Expedition Manager — No Man's Sky"
MODES = ("Originals", "Redux")
DIFFICULTIES = ("Defaults", "Easy", "Hardcore")

IS_LINUX = sys.platform.startswith("linux")
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"


def launch() -> int:
    """Create and run the main window. Returns the process exit code."""
    app = App()
    app.root.mainloop()
    return 0


# ---------------------------------------------------------------------------
# scrollable helper
# ---------------------------------------------------------------------------
def _make_scrollable(parent):
    """Return (wrap, inner): widgets packed into `inner` scroll vertically
    when the window is too short to show them all (prevents the bottom
    rows — e.g. the Install/Uninstall buttons — from collapsing).
    """
    wrap = ttk.Frame(parent)
    canvas = tk.Canvas(wrap, highlightthickness=0, borderwidth=0)
    vsb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    inner = ttk.Frame(canvas)
    win = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _inner_config(_e):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _canvas_config(e):
        canvas.itemconfigure(win, width=e.width)

    inner.bind("<Configure>", _inner_config)
    canvas.bind("<Configure>", _canvas_config)

    _WHEEL_SEQS = ("<4>", "<5>", "<MouseWheel>")

    def _wheel(event):
        up = getattr(event, "num", 0) == 4 or getattr(event, "delta", 0) > 0
        down = getattr(event, "num", 0) == 5 or getattr(event, "delta", 0) < 0
        if up:
            canvas.yview_scroll(-1, "units")
        elif down:
            canvas.yview_scroll(1, "units")

    def _enter(_e):
        for seq in _WHEEL_SEQS:
            inner.bind(seq, _wheel)

    def _leave(_e):
        for seq in _WHEEL_SEQS:
            inner.unbind(seq)

    inner.bind("<Enter>", _enter)
    inner.bind("<Leave>", _leave)
    return wrap, inner


class App:
    def __init__(self):
        self.q: "queue.Queue" = queue.Queue()
        self.worker_busy = False

        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("980x680")
        self.root.minsize(760, 520)

        # Window icon: Windows takes the .ico directly; on Linux the icon
        # comes from the hicolor theme, on macOS from the app bundle, so
        # nothing to do there.
        if IS_WINDOWS:
            _ico = Path(__file__).resolve().parent.parent / "assets" / "ExpeditionManager.ico"
            if _ico.exists():
                self.root.iconbitmap(default=str(_ico))

        # ttk theme (vista: Windows, aqua: macOS, clam: portable fallback)
        style = ttk.Style(self.root)
        for theme in ("vista", "aqua", "clam"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break

        # model
        self.catalog = []
        self.status = {}        # (exp_id, mode, difficulty) -> manifest entry
        self.state = load_state()

        self._build_ui()
        self._populate_settings()
        self._refresh_all()

        # start the queue pump (its id is cancelled on close)
        self._poll_id = self.root.after(100, self._poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # auto-detect the NMS cache folder (fast local scan)
        self._detect_caches()

        # try to preselect the installed expedition on the Install tab
        inst = self.state.get("installed") or {}
        if inst.get("exp_id"):
            self._set_install_exp(inst["exp_id"])
            if inst.get("mode") in ("Originals", "Redux"):
                self.var_mode.set(inst["mode"])
            if inst.get("difficulty") in DIFFICULTIES:
                self.var_diff.set(inst["difficulty"])
            self._on_install_choice()
            if inst.get("custom"):
                self._apply_custom_values(inst["custom"])

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        # Notebook with the three tabs
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill=tk.BOTH, expand=True)
        self.tab_library = ttk.Frame(self.nb)
        self.tab_install = ttk.Frame(self.nb)
        self.tab_settings = ttk.Frame(self.nb)
        self.nb.add(self.tab_library, text="  Library  ")
        self.nb.add(self.tab_install, text="  Install  ")
        self.nb.add(self.tab_settings, text="  Settings  ")

        # ---- Library tab (the treeview scrolls its own rows; no wrapper)
        lib = self.tab_library
        self.tree = ttk.Treeview(
            lib, columns=("id", "original", "redux", "originals", "redux_st", "status"),
            show="headings", selectmode="extended")
        cols = [
            ("id", "ID", 60, "center"),
            ("original", "Name", 220, "w"),
            ("redux", "Latest Redux", 90, "center"),
            ("originals", "Originals", 150, "center"),
            ("redux_st", "Redux", 150, "center"),
            ("status", "Status", 140, "center"),
        ]
        for key, label, width, anchor in cols:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor=anchor)
        vsb = ttk.Scrollbar(lib, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        # ---- Install tab
        inst = self.tab_install
        inst_wrap, inst_in = _make_scrollable(inst)
        inst_wrap.pack(fill=tk.BOTH, expand=True)
        frm = ttk.LabelFrame(inst_in, text="Expedition")
        frm.pack(fill=tk.X, padx=10, pady=6)

        row = ttk.Frame(frm); row.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(row, text="Expedition:").pack(side=tk.LEFT)
        self.cmb_exp = ttk.Combobox(row, width=38, state="readonly")
        self.cmb_exp.pack(side=tk.LEFT, padx=6)
        self.cmb_exp.bind("<<ComboboxSelected>>", self._on_exp_change)

        row = ttk.Frame(frm); row.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(row, text="Version:").pack(side=tk.LEFT)
        self.var_mode = tk.StringVar(value="Originals")
        ttk.Radiobutton(row, text="Original", value="Originals",
                        variable=self.var_mode, command=self._on_install_choice
                        ).pack(side=tk.LEFT, padx=6)
        self.rb_redux = ttk.Radiobutton(row, text="Redux", value="Redux",
                                        variable=self.var_mode, command=self._on_install_choice)
        self.rb_redux.pack(side=tk.LEFT, padx=6)

        row = ttk.Frame(frm); row.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(row, text="Difficulty:").pack(side=tk.LEFT)
        self.var_diff = tk.StringVar(value="Defaults")
        for label, value in (("Default", "Defaults"), ("Easy", "Easy"),
                             ("Hardcore", "Hardcore")):
            ttk.Radiobutton(row, text=label, value=value,
                            variable=self.var_diff, command=self._on_install_choice).pack(side=tk.LEFT, padx=6)

        self.lbl_comb_state = ttk.Label(frm, text="", foreground="gray")
        self.lbl_comb_state.pack(fill=tk.X, padx=8, pady=(0, 4))

        # ---- Customization (per-parameter values, like the website)
        frmC = ttk.LabelFrame(
            inst_in,
            text="Customization — fine-tune any parameter (as on the website)")
        frmC.pack(fill=tk.X, padx=10, pady=6)

        row = ttk.Frame(frmC); row.pack(fill=tk.X, padx=8, pady=2)
        ttk.Button(row, text="Load selected mode", width=18,
                   command=lambda: self._load_preset_form(notify=True)).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(row, text="Reset all", width=12,
                   command=self._reset_custom_form).pack(side=tk.LEFT, padx=2)
        self.lbl_custom_state = ttk.Label(row, text="", foreground="gray")
        self.lbl_custom_state.pack(side=tk.LEFT, padx=8)

        grid_holder = ttk.Frame(frmC)
        grid_holder.pack(fill=tk.X)
        self._build_custom_grid(grid_holder)
        self.lbl_custom_help = ttk.Label(frmC, text=" ", foreground="gray",
                                         wraplength=780, justify="left")
        self.lbl_custom_help.pack(fill=tk.X, padx=8, pady=(2, 4))

        frm2 = ttk.LabelFrame(inst_in, text="NMS cache folder")
        frm2.pack(fill=tk.X, padx=10, pady=6)
        row = ttk.Frame(frm2); row.pack(fill=tk.X, padx=8, pady=4)
        self.cmb_cache = ttk.Combobox(row, width=56, state="readonly")
        self.cmb_cache.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row, text="Re-detect", width=10,
                   command=self._detect_caches).pack(side=tk.LEFT, padx=4)
        self.lbl_cache_warn = ttk.Label(frm2, text="", foreground="#a00000", wraplength=620)
        self.lbl_cache_warn.pack(fill=tk.X, padx=8, pady=(0, 4))

        frm3 = ttk.LabelFrame(inst_in, text="Current installation")
        frm3.pack(fill=tk.X, padx=10, pady=6)
        self.lbl_installed = ttk.Label(frm3, text="(none)", wraplength=620)
        self.lbl_installed.pack(fill=tk.X, padx=8, pady=6)

        row = ttk.Frame(inst_in); row.pack(fill=tk.X, padx=10, pady=6)
        self.btn_install = ttk.Button(row, text="Install", width=24,
                                      command=self.do_install)
        self.btn_install.pack(side=tk.LEFT, padx=4)
        self.btn_uninstall = ttk.Button(row, text="Uninstall", width=24,
                                        command=self.do_uninstall)
        self.btn_uninstall.pack(side=tk.LEFT, padx=4)

        # ---- Settings tab
        st = self.tab_settings
        set_wrap, set_in = _make_scrollable(st)
        set_wrap.pack(fill=tk.BOTH, expand=True)
        frm4 = ttk.LabelFrame(set_in, text="Paths")
        frm4.pack(fill=tk.X, padx=10, pady=6)

        if IS_LINUX:
            row = ttk.Frame(frm4); row.pack(fill=tk.X, padx=8, pady=4)
            ttk.Label(row, text="Proton prefix:", width=14, anchor="w").pack(side=tk.LEFT)
            self.ent_prefix = ttk.Entry(row)
            self.ent_prefix.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
            ttk.Button(row, text="Browse…", width=9,
                       command=self._browse_prefix).pack(side=tk.LEFT, padx=2)
            ttk.Button(row, text="Standard", width=10,
                       command=self._standard_prefix).pack(side=tk.LEFT, padx=2)
        else:
            self.ent_prefix = None
            native = ("%APPDATA%\\HelloGames\\NMS" if IS_WINDOWS
                      else "~/Library/Application Support/HelloGames/NMS")
            ttk.Label(frm4, foreground="gray",
                      text=(f"The game folder ({native}) is probed automatically "
                            "on this system — no extra path is needed."),
                      wraplength=620, justify="left").pack(anchor="w", padx=12,
                                                           pady=(0, 4))

        row = ttk.Frame(frm4); row.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(row, text="Library path:", width=14, anchor="w").pack(side=tk.LEFT)
        self.ent_library = ttk.Entry(row)
        self.ent_library.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Button(row, text="Browse…", width=9,
                   command=self._browse_library).pack(side=tk.LEFT, padx=2)
        ttk.Button(row, text="Reset", width=9,
                   command=self._reset_library).pack(side=tk.LEFT, padx=2)

        if IS_LINUX:
            ttk.Label(set_in, foreground="gray",
                      text="Used on Linux/Proton to locate the game cache. "
                           "Leave empty to probe the standard Steam locations.",
                      wraplength=620, justify="left").pack(anchor="w", padx=18)

        row = ttk.Frame(set_in); row.pack(fill=tk.X, padx=10, pady=6)
        ttk.Button(row, text="Save", width=14,
                   command=self.do_save_config).pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text="Restore defaults", width=16,
                   command=self._restore_defaults).pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text="Detect NMS cache now", width=20,
                   command=self._detect_caches_log).pack(side=tk.LEFT, padx=4)

        frm5 = ttk.LabelFrame(set_in, text="File locations (read-only)")
        frm5.pack(fill=tk.X, padx=10, pady=6)
        for label, path in (("config.txt", CONFIG_FILE),
                            ("State / backups", state_dir())):
            row = ttk.Frame(frm5); row.pack(fill=tk.X, padx=8, pady=2)
            ttk.Label(row, text=label, width=14, anchor="w").pack(side=tk.LEFT)
            ttk.Label(row, text=str(path), foreground="gray").pack(side=tk.LEFT, padx=6)

        # ---- shared sync control strip
        strip = ttk.Frame(self.root)
        strip.pack(fill=tk.X, side=tk.BOTTOM, before=self.nb)
        self.btn_sync_all = ttk.Button(strip, text="Sync all",
                                       command=lambda: self.do_sync(None, False))
        self.btn_sync_all.pack(side=tk.LEFT, padx=6, pady=4)
        self.btn_sync_sel = ttk.Button(strip, text="Sync selection",
                                       command=lambda: self.do_sync(self._tree_selection(), False))
        self.btn_sync_sel.pack(side=tk.LEFT, padx=4, pady=4)
        self.btn_sync_force = ttk.Button(strip, text="Force resync",
                                         command=lambda: self.do_sync(None, True))
        self.btn_sync_force.pack(side=tk.LEFT, padx=4, pady=4)
        self.progress = ttk.Progressbar(strip, mode="determinate", length=260)
        self.progress.pack(side=tk.LEFT, padx=8, pady=4)
        self.lbl_progress = ttk.Label(strip, text="")
        self.lbl_progress.pack(side=tk.LEFT, padx=4)

        # ---- shared log panel
        logframe = ttk.LabelFrame(self.root, text="Log")
        logframe.pack(fill=tk.X, side=tk.BOTTOM, before=self.nb)
        self.logbox = tk.Text(logframe, height=9, state="disabled",
                              wrap="word", background="#1e1e1e",
                              foreground="#d4d4d4", insertbackground="#d4d4d4")
        lvsb = ttk.Scrollbar(logframe, orient="vertical", command=self.logbox.yview)
        self.logbox.configure(yscrollcommand=lvsb.set)
        self.logbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        lvsb.pack(side=tk.RIGHT, fill=tk.Y)
        for tag, color in (("ok", "#4ec9b0"), ("warn", "#dcdcaa"),
                           ("err", "#f48771"), ("info", "#569cd6")):
            self.logbox.tag_config(tag, foreground=color)

        # ---- status bar
        self.statusbar = ttk.Label(self.root, text="", relief="sunken",
                                   anchor="w", padding=(6, 2))
        self.statusbar.pack(fill=tk.X, side=tk.BOTTOM, before=self.nb)


    # ------------------------------------------------------------------ log

    def log(self, level: str, msg: str):
        """Thread-safe log line (queued, rendered by the main thread)."""
        self.q.put(("log", level, msg))

    def _append_log(self, level: str, msg: str):
        self.logbox.configure(state="normal")
        line = f"{msg}\n"
        self.logbox.insert(tk.END, line, level)
        # trim to ~2000 lines
        if int(self.logbox.index("end-1c").split(".")[0]) > 2000:
            self.logbox.delete("1.0", "1.0")
        self.logbox.see(tk.END)
        self.logbox.configure(state="disabled")

    # ---------------------------------------------------------------- workers

    def _run_bg(self, fn, *args, **kwargs):
        """Run fn(*args) in a worker thread; results arrive via the queue.

        While a worker runs, all action buttons are disabled. fn should
        return a ("done", payload) tuple OR push ("log"/"progress") items
        to self.q itself and return its result.
        """
        if self.worker_busy:
            messagebox.showinfo(APP_TITLE, "Another operation is still running.")
            return
        self.worker_busy = True
        self._set_busy(True)

        def runner():
            try:
                result = fn(*args, **kwargs)
                self.q.put(("done", result))
            except SourceError as e:
                self.q.put(("error", ("network", str(e))))
            except Exception as e:  # keep the UI alive on any bug
                self.q.put(("error", ("unexpected", f"{type(e).__name__}: {e}")))

        threading.Thread(target=runner, daemon=True).start()

    def _poll_queue(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._append_log(item[1], item[2])
                elif kind == "progress":
                    done, total, msg = item[1], item[2], item[3]
                    if total:
                        self.progress.configure(maximum=total, value=done)
                        self.lbl_progress.configure(
                            text=f"{done}/{total}  {msg}")
                    else:
                        self.lbl_progress.configure(text=msg)
                elif kind == "done":
                    self._on_worker_done(item[1])
                elif kind == "error":
                    self._on_worker_error(item[1])
        except queue.Empty:
            pass
        self._poll_id = self.root.after(100, self._poll_queue)

    def _on_worker_done(self, result):
        self.worker_busy = False
        self._set_busy(False)
        self.progress.configure(value=0)
        self.lbl_progress.configure(text="")
        self._refresh_all()

    def _on_worker_error(self, exc_pair):
        self.worker_busy = False
        self._set_busy(False)
        self.progress.configure(value=0)
        self.lbl_progress.configure(text="")
        kind, msg = exc_pair
        self.log("err", msg)
        self._refresh_all()
        title = "Network error" if kind == "network" else "Unexpected error"
        messagebox.showerror(title, msg)

    def _set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        for b in (self.btn_sync_all, self.btn_sync_sel, self.btn_sync_force,
                  self.btn_install, self.btn_uninstall):
            b.configure(state=state)
        if busy:
            self.statusbar.configure(text="Working…")
        else:
            self._update_statusbar()

    # ------------------------------------------------------------ model IO

    def _load_catalog(self):
        """Load the expedition catalog from the local source cache (offline)."""
        src = Sources(PROJECT_ROOT / "data" / "sources", quiet=True)
        raw = src.fetch("_data/expeditions.yml")
        self.catalog = build_catalog(raw)

    def _load_library_status(self):
        try:
            self.status = syncmod.library_status()
        except Exception:
            self.status = {}

    def _reload_state(self):
        self.state = load_state()

    # ------------------------------------------------------------ refresh

    def _refresh_all(self):
        try:
            self._load_catalog()
        except Exception as e:
            self.log("err", f"Could not load the catalog: {e}")
            return
        self._load_library_status()
        self._reload_state()
        self._refresh_library_tree()
        self._refresh_install_tab()
        self._update_statusbar()

    def _refresh_library_tree(self):
        tree = self.tree
        prev_sel = tree.selection() or None
        tree.delete(*tree.get_children())
        for exp in self.catalog:
            redux = exp.latest_redux
            orig_cell = self._status_cell(exp.id, "Originals")
            redux_cell = self._status_cell(exp.id, "Redux")
            inst = self.state.get("installed") or {}
            if inst.get("exp_id") == exp.id:
                status = f"INSTALLED ({inst.get('mode')}/{inst.get('difficulty')})"
                tag = "installed"
            else:
                status = "not downloaded" if not self.status else "downloaded"
                tag = ""
            iid = tree.insert(
                "", tk.END, iid=exp.id,
                values=(exp.id, exp.name, redux.id if redux else "—",
                        orig_cell, redux_cell, status),
                tags=(tag,) if tag else ())
            if inst.get("exp_id") == exp.id:
                tree.item(iid, tags=("installed",))
        # keep previous selection if possible
        if prev_sel and prev_sel[0] in tree.get_children():
            tree.selection_set(prev_sel[0])
            tree.see(prev_sel[0])

    def _status_cell(self, exp_id, mode):
        def mark(diff):
            return "✔" if (exp_id, mode, diff) in self.status else "·"
        if mode == "Redux" and not any(
                (exp_id, "Redux", d) in self.status for d in DIFFICULTIES):
            exp = next((e for e in self.catalog if e.id == exp_id), None)
            if exp and not exp.latest_redux:
                return "— (no redux)"
        return (f"D {mark('Defaults')}   E {mark('Easy')}   "
                f"H {mark('Hardcore')}")

    def _refresh_install_tab(self):
        # expedition combobox (keep current value)
        current = self.cmb_exp.get()
        names = [f"{e.id}  —  {e.name}" for e in self.catalog]
        self.cmb_exp["values"] = names
        mapping = {f"{e.id}  —  {e.name}": e for e in self.catalog}
        if current in mapping:
            self.cmb_exp.set(current)
        elif self.catalog:
            self.cmb_exp.set(names[0])
            self._on_exp_change()

        self._update_redux_state()
        self._on_install_choice()
        self._refresh_installed_label()

    def _refresh_installed_label(self):
        inst = self.state.get("installed") or {}
        if inst:
            text = (f"{inst['exp_id']}  ·  {inst.get('mode')}/{inst.get('difficulty')}"
                    f"\nCache: {self.state.get('cache_dir', '?')}")
            if inst.get("custom"):
                text += f"\nCustomization: {len(inst['custom'])} value(s) saved"
            if self.state.get("backup_cache"):
                text += f"\nBackup: {self.state['backup_cache']}"
        else:
            text = "(nothing installed)"
        self.lbl_installed.configure(text=text)

    def _update_statusbar(self):
        n = len(self.status)
        inst = self.state.get("installed") or {}
        inst_txt = (f"{inst['exp_id']} ({inst.get('mode')}/{inst.get('difficulty')})"
                    if inst else "none")
        self.statusbar.configure(
            text=f"Library: {n} files · Installed: {inst_txt} · Ready")

    # -------------------------------------------------------- library tab

    def _tree_selection(self):
        return [self.tree.item(i)["values"][0]
                for i in self.tree.selection()]

    def _on_tree_double_click(self, _event=None):
        sel = self._tree_selection()
        if not sel:
            return
        self.nb.select(self.tab_install)
        self._set_install_exp(sel[0])
        self._on_exp_change()

    # ---------------------------------------------------------- install tab

    def _exp_from_combo(self):
        val = self.cmb_exp.get()
        for e in self.catalog:
            if f"{e.id}  —  {e.name}" == val:
                return e
        return None

    def _set_install_exp(self, exp_id: str):
        for e in self.catalog:
            if e.id == exp_id:
                self.cmb_exp.set(f"{e.id}  —  {e.name}")
                return

    def _on_exp_change(self, _event=None):
        self._update_redux_state()
        self._on_install_choice()

    def _update_redux_state(self):
        exp = self._exp_from_combo()
        if exp is not None and not exp.latest_redux:
            self.rb_redux.state(["disabled"])
            if self.var_mode.get() == "Redux":
                self.var_mode.set("Originals")
        else:
            self.rb_redux.state(["!disabled"])

    def _on_install_choice(self, _event=None):
        """Update the combo-state hint + Install button label."""
        exp = self._exp_from_combo()
        if exp is None:
            return
        mode = self.var_mode.get()
        diff = self.var_diff.get()
        if mode == "Redux" and not exp.latest_redux:
            self.var_mode.set("Originals")
            mode = "Originals"
        key = (exp.id, mode, diff)
        downloaded = key in self.status
        self.btn_install.configure(
            text="Download first" if not downloaded else "Install")
        self.lbl_comb_state.configure(
            text=("Downloaded ✓" if downloaded
                  else f"{mode}/{diff} not downloaded yet — click the button "
                       f"to download it")
            + ("" if exp.latest_redux else f"   ({exp.name} has no Redux version)"),
            foreground=("#2e7d32" if downloaded else "gray"))
        self._load_preset_form()

    # ------------------------------------------------ customization form

    @staticmethod
    def _humanize(prop):
        import re as _re
        return _re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", prop)

    def _prop_display(self, p):
        return p.get("display") or self._humanize(p["prop"])

    def _build_custom_grid(self, parent):
        self.custom_vars = {}
        self.custom_info = {}
        try:
            groups, _ = customize.load_spec()
        except Exception as e:
            ttk.Label(parent, foreground="#a00000",
                      text=(f"Could not load the customization parameters: {e}\n"
                            "Run a sync (it fills the local source cache) and "
                            "restart the GUI."),
                      wraplength=640, justify="left").pack(padx=8, pady=4)
            return
        r = 0
        for g in groups:
            ttk.Label(parent, text=g["name"],
                      font=("TkDefaultFont", 9, "bold")).grid(
                row=r, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 0))
            r += 1
            for p in g["props"]:
                label = ttk.Label(parent, text=self._prop_display(p),
                                  width=32, anchor="e")
                label.grid(row=r, column=0, sticky="e", padx=(8, 2), pady=1)
                var = tk.StringVar()
                combo = ttk.Combobox(parent, textvariable=var, width=30)
                opts = p.get("options")
                if opts:
                    combo["values"] = ([customize.DEFAULT_TEXT]
                                        + [o["text"] for o in opts])
                    combo["state"] = "readonly"
                elif p["type"] == "bool":
                    combo["values"] = [customize.DEFAULT_TEXT, "true", "false"]
                combo.grid(row=r, column=1, sticky="w", padx=(0, 8), pady=1)
                combo.bind("<<ComboboxSelected>>",
                           lambda _e, p=p: self._custom_help(p))
                combo.bind("<FocusIn>", lambda _e, p=p: self._custom_help(p))
                label.bind("<Button-1>", lambda _e, p=p: self._custom_help(p))
                self.custom_vars[p["prop"]] = var
                self.custom_info[p["prop"]] = p
                r += 1

    def _custom_help(self, p):
        if not p:
            self.lbl_custom_help.configure(text=" ")
            return
        text = " ".join(str(p.get("description") or "").split())
        text = text.replace("<br>", " · ").replace("**", "")
        w = str(p.get("warning") or "")
        if w:
            text += (f"    ⚠ {w.replace('<br>', ' ').replace('**', '')}"
                     if text else "")
        self.lbl_custom_help.configure(text=text.strip() or "(no description)")

    def _value_to_display(self, value, p):
        for o in (p.get("options") or []):
            if str(o["value"]) == str(value):
                return o["text"]
        return str(value)

    def _display_to_value(self, disp, p):
        for o in (p.get("options") or []):
            if o["text"] == disp:
                return str(o["value"])
        return disp

    def _load_preset_form(self, notify=False):
        vars_ = getattr(self, "custom_vars", None)
        if not vars_:
            return
        try:
            preset = customize.load_preset(self.var_diff.get())
        except Exception:
            preset = {}
        for prop, var in vars_.items():
            if prop in preset:
                var.set(self._value_to_display(preset[prop],
                                               self.custom_info[prop]))
            else:
                var.set(customize.DEFAULT_TEXT)
        self._update_custom_state()
        if notify:
            self.log("info", f"Loaded the {self.var_diff.get()} preset values "
                             f"into the customization form.")

    def _reset_custom_form(self):
        for var in getattr(self, "custom_vars", {}).values():
            var.set(customize.DEFAULT_TEXT)
        self._update_custom_state()

    def _apply_custom_values(self, flat):
        for prop, value in (flat or {}).items():
            var = getattr(self, "custom_vars", {}).get(prop)
            info = getattr(self, "custom_info", {}).get(prop)
            if var is not None and info is not None:
                var.set(self._value_to_display(value, info))
        self._update_custom_state()

    def _current_custom_flat(self):
        out = {}
        for prop, var in getattr(self, "custom_vars", {}).items():
            disp = var.get().strip()
            if not disp or disp == customize.DEFAULT_TEXT:
                continue
            out[prop] = self._display_to_value(disp, self.custom_info[prop])
        return out

    def _update_custom_state(self):
        if not getattr(self, "custom_vars", None):
            return
        diff = self.var_diff.get()
        try:
            preset = customize.load_preset(diff)
        except Exception:
            preset = {}
        flat = self._current_custom_flat()
        n = sum(1 for k, v in flat.items() if preset.get(k) != v)
        if n:
            self.lbl_custom_state.configure(
                text=(f"{n} parameter(s) changed vs {diff} — the file will "
                      f"be generated at install time"),
                foreground="#8a6d00")
        else:
            self.lbl_custom_state.configure(
                text="No changes — the pre-built file will be installed",
                foreground="gray")

    def _detect_caches(self):
        found = installer.find_nms_cache_dirs()
        self.cmb_cache["values"] = [str(c) for c in found]
        if not found:
            hint = ("Play the game once so it creates its data folder."
                    if not IS_LINUX else
                    "Play the game once (creates the prefix), or set the Proton "
                    "prefix in Settings.")
            self.lbl_cache_warn.configure(
                text=f"No NMS cache folder found. {hint}")
            return
        self.lbl_cache_warn.configure(text="")
        # default: the one already recorded in state, else the one containing
        # the cache file, else the first
        current = (self.state.get("cache_dir") or "")
        def contains_file(c):
            return installer._resolve_cache_file(c).exists()
        target = next((c for c in found if str(c) == current), None)
        if target is None:
            target = next((c for c in found if contains_file(c)), found[0])
        self.cmb_cache.set(str(target))

    def _detect_caches_log(self):
        found = installer.find_nms_cache_dirs()
        if found:
            for c in found:
                self.log("ok", f"Cache dir found: {c}")
        else:
            extra = (" On Linux, check Settings → Proton prefix." if IS_LINUX else "")
            self.log("warn", "No NMS cache folder found." + extra)
        self._detect_caches()

    # -------------------------------------------------------------- actions

    def do_sync(self, only_exps=None, force=False):
        exps = [e for e in self.catalog if e.id in only_exps] if only_exps else None
        label = (f"{len(only_exps)} selected" if only_exps else "all") + \
                ("  [force]" if force else "")
        self.log("info", f"Sync started ({label})…")

        def _sync_one(only_exp, force_):
            def progress_cb(done, total, msg):
                self.q.put(("progress", done, total, msg))
            return syncmod.sync(force=force_, only_exp=only_exp, progress=progress_cb)

        def work():
            if exps:
                # sync each selected expedition through the real API
                got = 0
                for e in exps:
                    d, s = _sync_one(e.id, force)
                    got += d
                    self.q.put(("progress", got,
                                max(len(exps), 1), f"{e.id} done"))
                self.q.put(("log", "ok", f"Sync complete: {got} downloaded/updated."))
            else:
                d, s = _sync_one(None, force)
                self.q.put(("log", "ok",
                            f"Sync complete: {d} downloaded/updated, {s} unchanged."))
            return None

        self._run_bg(work)

    def do_install(self):
        exp = self._exp_from_combo()
        if exp is None:
            return
        mode = self.var_mode.get()
        diff = self.var_diff.get()
        if mode == "Redux" and not exp.latest_redux:
            mode = "Originals"
            self.var_mode.set(mode)
        key = (exp.id, mode, diff)
        cache = self.cmb_cache.get().strip()

        # Custom values (the website's form). A customized file is generated
        # from the cached sources, so no library download is required for it.
        flat = self._current_custom_flat()
        try:
            preset = customize.load_preset(diff)
        except Exception:
            preset = {}
        changed = bool(flat) and flat != preset

        if key not in self.status and not changed:
            # "Download first" mode
            self.log("info", f"Downloading {exp.id} ({mode}/{diff}) before install…")
            def work():
                def progress_cb(done, total, msg):
                    self.q.put(("progress", done, total, msg))
                d, s = syncmod.sync(force=False, only_exp=exp.id, progress=progress_cb)
                self.q.put(("log", "ok", f"Download finished: {d} file(s)."))
                return None
            self._run_bg(work)
            return

        if not cache:
            self._detect_caches()
            cache = self.cmb_cache.get().strip()
            if not cache:
                hint = ("Play the game once so it creates its data folder."
                        if not IS_LINUX else
                        "Play the game once, or set the Proton prefix in the "
                        "Settings tab.")
                messagebox.showwarning(
                    APP_TITLE, "No NMS cache folder found.\n\n" + hint)
                return

        n_custom = (sum(1 for k, v in flat.items() if preset.get(k) != v)
                    if changed else 0)
        msg = (f"Install {exp.name} ({exp.id})?\n\n"
               f"Version: {mode}   Difficulty: {diff}\n"
               f"Target cache: {cache}\n"
               + (f"Custom parameters: {n_custom} — the file will be generated "
                  f"from the cached sources\n" if changed else "\n")
               + "\nThe current season cache file (SEASON_DATA_CACHE_S*.JSON) will be backed up "
               "automatically.\n\n⚠ Put STEAM IN OFFLINE MODE before launching "
               "NMS, or the game will overwrite the installed expedition.")
        if not messagebox.askyesno("Install expedition", msg, icon="warning"):
            return

        self.log("info", f"Installing {exp.id} ({mode}/{diff}) → {cache} …")

        def work():
            src_file = None
            custom = dict(flat) if changed else None
            if changed:
                self.q.put(("log", "info", "Generating the custom expedition file…"))
                try:
                    src_file, custom = customize.install_source_from_flat(
                        exp.id, mode, diff, flat)
                except Exception as e:
                    self.q.put(("log", "err",
                                f"Could not generate the custom file: {e}"))
                    return False
            ok = installer.install(exp.id, mode, diff, interactive=False,
                                   cache_dir=cache,
                                   source_file=str(src_file) if src_file else None,
                                   custom=custom)
            self.q.put(("log", "ok" if ok else "err",
                        "Installation complete. Start NMS in OFFLINE mode."
                        if ok else "Installation FAILED — see log."))
            return ok

        self._run_bg(work)

    def do_uninstall(self):
        inst = self.state.get("installed")
        if not inst:
            messagebox.showinfo(APP_TITLE, "No expedition is currently installed.")
            return
        if not messagebox.askyesno(
                "Uninstall expedition",
                f"Restore the original cache (undo {inst['exp_id']} "
                f"{inst.get('mode')}/{inst.get('difficulty')})?\n\n"
                f"The backup of the original cache will be kept in the state "
                f"directory."):
            return
        self.log("info", "Uninstalling…")

        def work():
            ok = installer.uninstall(interactive=False)
            self.q.put(("log", "ok" if ok else "err",
                        "Uninstallation complete." if ok else "Uninstall FAILED."))
            return ok

        self._run_bg(work)

    # ------------------------------------------------------------ settings

    def _populate_settings(self):
        cfg = load_config()
        if self.ent_prefix is not None:
            self.ent_prefix.delete(0, tk.END)
            self.ent_prefix.insert(0, cfg.get("proton_prefix", ""))
        self.ent_library.delete(0, tk.END)
        self.ent_library.insert(0, cfg.get("library_path", ""))

    def do_save_config(self):
        new = {"library_path": self.ent_library.get().strip()
               or str(PROJECT_ROOT / "ExpeditionManagerLibrary")}
        if self.ent_prefix is not None:
            new["proton_prefix"] = self.ent_prefix.get().strip()
        if not new["library_path"]:
            messagebox.showwarning(APP_TITLE, "Library path cannot be empty.")
            return
        save_config(new)
        self.log("ok", f"Configuration saved → {CONFIG_FILE}")
        self._populate_settings()
        self._refresh_all()  # library path may have changed

    def _browse_prefix(self):
        if self.ent_prefix is None:
            return
        d = filedialog.askdirectory(title="Select the NMS Proton prefix")
        if d:
            self.ent_prefix.delete(0, tk.END)
            self.ent_prefix.insert(0, d)

    def _standard_prefix(self):
        if self.ent_prefix is None:
            return
        self.ent_prefix.delete(0, tk.END)
        self.ent_prefix.insert(0, DEFAULT_PREFIX)

    def _browse_library(self):
        d = filedialog.askdirectory(title="Select the expedition library folder")
        if d:
            self.ent_library.delete(0, tk.END)
            self.ent_library.insert(0, d)

    def _reset_library(self):
        self.ent_library.delete(0, tk.END)
        self.ent_library.insert(
            0, str(PROJECT_ROOT / "ExpeditionManagerLibrary"))

    def _restore_defaults(self):
        from .config import DEFAULT_CONFIG
        for k, v in DEFAULT_CONFIG.items():
            if k == "proton_prefix" and self.ent_prefix is not None:
                self.ent_prefix.delete(0, tk.END)
                self.ent_prefix.insert(0, v)
            elif k == "library_path":
                self.ent_library.delete(0, tk.END)
                self.ent_library.insert(0, v)

    # --------------------------------------------------------------- window

    def _on_close(self):
        try:
            self.root.after_cancel(self._poll_id)
        except (tk.TclError, AttributeError):
            pass
        self.root.destroy()
