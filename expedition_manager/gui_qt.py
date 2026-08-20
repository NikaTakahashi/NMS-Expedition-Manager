"""Graphical interface for Expedition Manager (Qt6 — PyQt6 / PySide6).

This is the primary GUI backend. On Linux it runs on **native Wayland**
(xdg-shell, via the Qt6 ``wayland`` platform plugin) — no X11 involved.
On Windows and macOS it uses the native platform integration.

The GUI is a thin front-end over the existing core modules:
  - catalog.build_catalog()   → expedition list
  - sync.sync() / sync.library_status() → downloads + status badges
  - installer.install/uninstall/find_nms_cache_dirs → install tab
  - config.load_config/save_config → settings tab

Threading model (identical to the tkinter GUI): every long-running action
(sync, install, uninstall) runs in a worker ``threading.Thread`` that pushes
("kind", payload) tuples to a ``queue.Queue``. The Qt main thread drains the
queue with a 100 ms ``QTimer`` poller, so widgets are only ever touched from
the GUI thread.

Backend selection (see cli.cmd_gui): PyQt6 → PySide6 → tkinter fallback.
"""
import functools
import html as _html
import os
import queue
import re as _re
import sys
import threading
import traceback
from pathlib import Path

# ---------------------------------------------------------------- Qt import
# PyQt6 first (system package on Arch: python-pyqt6), PySide6 as fallback
# (pip-installable on every platform). Both expose the same Qt6 C++ API;
# this module only uses APIs that are identical in both bindings.
try:
    from PyQt6.QtCore import QEvent, Qt, QTimer
    from PyQt6.QtGui import QColor, QFont, QGuiApplication, QIcon, QTextCursor
    from PyQt6.QtWidgets import (
        QApplication, QComboBox, QFileDialog, QFrame,
        QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
        QHeaderView, QMessageBox, QProgressBar, QPushButton, QRadioButton,
        QScrollArea, QTabWidget, QTreeWidget, QTreeWidgetItem, QTextEdit,
        QVBoxLayout, QWidget,
    )
    _QT_IMPL = "PyQt6"
except ImportError:  # pragma: no cover - depends on the host system
    from PySide6.QtCore import QEvent, Qt, QTimer
    from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QTextCursor
    from PySide6.QtWidgets import (
        QApplication, QComboBox, QFileDialog, QFrame,
        QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
        QHeaderView, QMessageBox, QProgressBar, QPushButton, QRadioButton,
        QScrollArea, QTabWidget, QTreeWidget, QTreeWidgetItem, QTextEdit,
        QVBoxLayout, QWidget,
    )
    _QT_IMPL = "PySide6"

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

_LOG_COLORS = {"ok": "#4ec9b0", "warn": "#dcdcaa",
               "err": "#f48771", "info": "#569cd6"}
_LOG_DEFAULT = "#d4d4d4"
_MAX_LOG_BLOCKS = 2000


def _qt_slot(method):
    """Make a Python slot invoked by Qt exception-safe.

    PyQt6 turns any exception that escapes a Python slot called from the C++
    side (button clicks, timer timeouts, selection changes, ...) into a
    silent ``qFatal``: the whole application aborts (SIGABRT) with no
    traceback and no way to recover. Catching every such exception and
    logging it instead is the only way to keep the window alive.
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception as e:
            self._slot_failed(method.__name__, e)
    return wrapper


def launch() -> int:
    """Create and run the Qt main window. Returns the process exit code."""
    # Last line of defence: if a Python exception still escapes a Qt callback
    # (see _qt_slot), print a real traceback to the terminal before PyQt's
    # qFatal path kills the process, so the bug is diagnosable.
    sys.excepthook = lambda t, v, tb: traceback.print_exception(t, v, tb)
    threading.excepthook = lambda a: traceback.print_exception(
        a.exc_type, a.exc_value, a.exc_traceback)
    # Prefer native Wayland (xdg-shell) when running on a Wayland session
    # and the user has not chosen a platform explicitly. (The launchers set
    # QT_QPA_PLATFORM too; this is the second line of defence.)
    if (sys.platform.startswith("linux")
            and "QT_QPA_PLATFORM" not in os.environ):
        if (os.environ.get("WAYLAND_DISPLAY")
                or os.environ.get("XDG_SESSION_TYPE") == "wayland"):
            os.environ["QT_QPA_PLATFORM"] = "wayland"

    app = QApplication(sys.argv[:1] or ["expedition-manager"])
    app.setApplicationName("Expedition Manager")
    app.setOrganizationName("expedition-manager")
    # Wayland app_id / X11 WM_CLASS: lets the compositor match this window
    # to an "expedition-manager" desktop entry (taskbar icon / grouping).
    try:
        QGuiApplication.setDesktopFileName("expedition-manager")
    except Exception:
        pass

    # Window icon: the .ico (Qt loads .ico natively on every platform);
    # fall back to the hicolor theme entry on Linux.
    icon = QIcon()
    ico = Path(__file__).resolve().parent.parent / "assets" / "ExpeditionManager.ico"
    if ico.exists():
        icon.addFile(str(ico))
    if icon.isNull() and IS_LINUX:
        icon = QIcon.fromTheme("expedition-manager")
    if icon.isNull():
        icon = QIcon.fromTheme("applications-games")
    app.setWindowIcon(icon)

    win = MainWindow()
    win.show()
    return app.exec()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # ------------------------------------------------------------- model
        self.q: "queue.Queue" = queue.Queue()
        self.worker_busy = False
        self.catalog = []
        self.status = {}          # (exp_id, mode, difficulty) -> manifest entry
        self.state = load_state()
        self._tree_items = {}
        self.custom_vars = {}     # prop -> QComboBox
        self.custom_info = {}     # prop -> spec dict

        self.setWindowTitle(APP_TITLE)
        self.resize(980, 680)
        self.setMinimumSize(760, 520)

        # ------------------------------------------------------- root layout
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self.tabs = QTabWidget()
        self.tab_library = QWidget()
        self.tab_install = QWidget()
        self.tab_settings = QWidget()
        self.tabs.addTab(self.tab_library, "Library")
        self.tabs.addTab(self.tab_install, "Install")
        self.tabs.addTab(self.tab_settings, "Settings")
        root.addWidget(self.tabs, stretch=1)

        # shared sync control strip
        strip = QFrame()
        strip_l = QHBoxLayout(strip)
        strip_l.setContentsMargins(4, 4, 4, 4)
        self.btn_sync_all = QPushButton("Sync all")
        self.btn_sync_all.clicked.connect(
            lambda: self.do_sync(None, False))
        self.btn_sync_sel = QPushButton("Sync selection")
        self.btn_sync_sel.clicked.connect(
            lambda: self.do_sync(self._tree_selection(), False))
        self.btn_sync_force = QPushButton("Force resync")
        self.btn_sync_force.clicked.connect(
            lambda: self.do_sync(None, True))
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFixedWidth(260)
        self.lbl_progress = QLabel("")
        for b in (self.btn_sync_all, self.btn_sync_sel, self.btn_sync_force):
            strip_l.addWidget(b)
        strip_l.addSpacing(8)
        strip_l.addWidget(self.progress)
        strip_l.addSpacing(4)
        strip_l.addWidget(self.lbl_progress)
        strip_l.addStretch(1)
        root.addWidget(strip)

        # shared log panel
        self.logview = QTextEdit()
        self.logview.setReadOnly(True)
        mono = QFont()
        mono.setStyleHint(QFont.StyleHint.TypeWriter)
        self.logview.setFont(mono)
        self.logview.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; }")
        self.logview.setFixedHeight(170)
        root.addWidget(self.logview)

        self.setCentralWidget(central)
        self.statusBar().showMessage("")

        # ------------------------------------------------------- build tabs
        self._build_library_tab()
        self._build_install_tab()
        self._build_settings_tab()

        self._populate_settings()
        self._refresh_all()

        # start the queue pump (stopped on close)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_queue)
        self._timer.start(100)

        # auto-detect the NMS cache folder (fast local scan)
        self._detect_caches()

        # try to preselect the installed expedition on the Install tab
        inst = self.state.get("installed") or {}
        if inst.get("exp_id"):
            self._set_install_exp(inst["exp_id"])
            if inst.get("mode") == "Redux":
                self.rb_redux.setChecked(True)
            else:
                self.rb_original.setChecked(True)
            for d in DIFFICULTIES:
                if inst.get("difficulty") == d:
                    self._diff_radio(d).setChecked(True)
            self._on_install_choice()
            if inst.get("custom"):
                self._apply_custom_values(inst["custom"])

    # --------------------------------------------------------------- helpers

    def _slot_failed(self, name: str, exc: Exception):
        """Report an exception caught by a _qt_slot-guarded callback."""
        tb = traceback.format_exc()
        try:
            self.q.put(("log", "err", f"GUI error in {name}(): {exc}"))
        except Exception:
            pass
        try:
            sys.stderr.write(
                f"[Expedition Manager] GUI error in {name}:\n{tb}")
            sys.stderr.flush()
        except Exception:
            pass
        # An error mid-operation must not leave the UI frozen.
        try:
            if getattr(self, "worker_busy", False):
                self.worker_busy = False
                self._set_busy(False)
        except Exception:
            pass

    def _diff_radio(self, value: str) -> QRadioButton:
        return {"Defaults": self.rb_def,
                "Easy": self.rb_easy,
                "Hardcore": self.rb_hardcore}[value]

    # ------------------------------------------------------------------ UI

    def _build_library_tab(self):
        lay = QVBoxLayout(self.tab_library)
        lay.setContentsMargins(4, 4, 4, 4)
        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(
            QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(
            ["ID", "Name", "Latest Redux", "Originals", "Redux", "Status"])
        header = self.tree.header()
        header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.tree.itemDoubleClicked.connect(self._on_tree_double_click)
        self.tree.itemSelectionChanged.connect(
            lambda: self._update_statusbar())
        lay.addWidget(self.tree)

    def _build_install_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        scroll.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # ---- Expedition
        grp = QGroupBox("Expedition")
        g = QGridLayout(grp)
        g.setContentsMargins(10, 10, 10, 10)
        g.addWidget(QLabel("Expedition:"), 0, 0)
        self.cmb_exp = QComboBox()
        self.cmb_exp.setFixedWidth(380)
        self.cmb_exp.currentTextChanged.connect(self._on_exp_change)
        g.addWidget(self.cmb_exp, 0, 1, 1, 2)

        g.addWidget(QLabel("Version:"), 1, 0)
        self.rb_original = QRadioButton("Original")
        self.rb_original.setChecked(True)
        self.rb_original.clicked.connect(self._on_install_choice)
        self.rb_redux = QRadioButton("Redux")
        self.rb_redux.clicked.connect(self._on_install_choice)
        ver_l = QHBoxLayout()
        ver_l.setContentsMargins(0, 0, 0, 0)
        ver_l.addWidget(self.rb_original)
        ver_l.addSpacing(16)
        ver_l.addWidget(self.rb_redux)
        ver_l.addStretch(1)
        row_v = QWidget()
        row_v.setLayout(ver_l)
        g.addWidget(row_v, 1, 1, 1, 2)

        g.addWidget(QLabel("Difficulty:"), 2, 0)
        self.rb_def = QRadioButton("Default")
        self.rb_easy = QRadioButton("Easy")
        self.rb_hardcore = QRadioButton("Hardcore")
        self.rb_def.setChecked(True)
        self.rb_def.clicked.connect(self._on_install_choice)
        self.rb_easy.clicked.connect(self._on_install_choice)
        self.rb_hardcore.clicked.connect(self._on_install_choice)
        dif_l = QHBoxLayout()
        dif_l.setContentsMargins(0, 0, 0, 0)
        dif_l.addWidget(self.rb_def)
        dif_l.addSpacing(16)
        dif_l.addWidget(self.rb_easy)
        dif_l.addSpacing(16)
        dif_l.addWidget(self.rb_hardcore)
        dif_l.addStretch(1)
        row_d = QWidget()
        row_d.setLayout(dif_l)
        g.addWidget(row_d, 2, 1, 1, 2)

        self.lbl_comb_state = QLabel("")
        self.lbl_comb_state.setStyleSheet("color: gray;")
        g.addWidget(self.lbl_comb_state, 3, 1, 1, 2)
        g.setColumnStretch(1, 1)
        lay.addWidget(grp)

        # ---- Customization (per-parameter values, like the website)
        grpC = QGroupBox(
            "Customization — fine-tune any parameter (as on the website)")
        c = QVBoxLayout(grpC)
        c.setContentsMargins(10, 10, 10, 10)
        row = QHBoxLayout()
        self.btn_load_preset = QPushButton("Load selected mode")
        self.btn_load_preset.clicked.connect(
            lambda: self._load_preset_form(notify=True))
        self.btn_reset_all = QPushButton("Reset all")
        self.btn_reset_all.clicked.connect(self._reset_custom_form)
        self.lbl_custom_state = QLabel("")
        self.lbl_custom_state.setStyleSheet("color: gray;")
        row.addWidget(self.btn_load_preset)
        row.addWidget(self.btn_reset_all)
        row.addSpacing(12)
        row.addWidget(self.lbl_custom_state)
        row.addStretch(1)
        c.addLayout(row)

        self._custom_grid = QGridLayout()
        self._custom_grid.setContentsMargins(4, 4, 4, 4)
        self._build_custom_grid(self._custom_grid)
        c.addLayout(self._custom_grid)

        self.lbl_custom_help = QLabel(" ")
        self.lbl_custom_help.setWordWrap(True)
        self.lbl_custom_help.setStyleSheet("color: gray;")
        self.lbl_custom_help.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        c.addWidget(self.lbl_custom_help)
        lay.addWidget(grpC)

        # ---- NMS cache folder
        grp2 = QGroupBox("NMS cache folder")
        c2 = QVBoxLayout(grp2)
        c2.setContentsMargins(10, 10, 10, 10)
        row2 = QHBoxLayout()
        self.cmb_cache = QComboBox()
        self.cmb_cache.setEditable(False)
        # A long cache path (e.g. the full Proton prefix) must not set the
        # tab's — and therefore the window's — minimum width. Keep the
        # combo's own size small and let the layout stretch it to fill the
        # row; an overlong path is simply truncated in the display.
        self.cmb_cache.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.btn_cache_rescan = QPushButton("Re-detect")
        self.btn_cache_rescan.clicked.connect(self._detect_caches)
        row2.addWidget(self.cmb_cache, stretch=1)
        row2.addWidget(self.btn_cache_rescan)
        c2.addLayout(row2)
        self.lbl_cache_warn = QLabel("")
        self.lbl_cache_warn.setWordWrap(True)
        self.lbl_cache_warn.setStyleSheet("color: #a00000;")
        c2.addWidget(self.lbl_cache_warn)
        lay.addWidget(grp2)

        # ---- Current installation
        grp3 = QGroupBox("Current installation")
        c3 = QVBoxLayout(grp3)
        c3.setContentsMargins(10, 10, 10, 10)
        self.lbl_installed = QLabel("(none)")
        self.lbl_installed.setWordWrap(True)
        c3.addWidget(self.lbl_installed)
        lay.addWidget(grp3)

        # ---- action row
        brow = QHBoxLayout()
        self.btn_install = QPushButton("Install")
        self.btn_install.setFixedWidth(150)
        self.btn_install.clicked.connect(self.do_install)
        self.btn_uninstall = QPushButton("Uninstall")
        self.btn_uninstall.setFixedWidth(150)
        self.btn_uninstall.clicked.connect(self.do_uninstall)
        brow.addWidget(self.btn_install)
        brow.addWidget(self.btn_uninstall)
        brow.addStretch(1)
        lay.addLayout(brow)
        lay.addStretch(1)

        tab_lay = QVBoxLayout(self.tab_install)
        tab_lay.setContentsMargins(4, 4, 4, 4)
        tab_lay.addWidget(scroll)

    def _build_settings_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        scroll.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        grp = QGroupBox("Paths")
        g = QGridLayout(grp)
        g.setContentsMargins(10, 10, 10, 10)
        g.setHorizontalSpacing(8)
        r = 0
        if IS_LINUX:
            g.addWidget(QLabel("Proton prefix:"), r, 0,
                        Qt.AlignmentFlag.AlignRight |
                        Qt.AlignmentFlag.AlignVCenter)
            self.ent_prefix = QLineEdit()
            g.addWidget(self.ent_prefix, r, 1)
            b1 = QPushButton("Browse…")
            b1.clicked.connect(self._browse_prefix)
            b2 = QPushButton("Standard")
            b2.clicked.connect(self._standard_prefix)
            hb = QHBoxLayout()
            hb.setContentsMargins(0, 0, 0, 0)
            hb.addWidget(b1)
            hb.addWidget(b2)
            hb.addStretch(1)
            row_w = QWidget()
            row_w.setLayout(hb)
            g.addWidget(row_w, r, 2)
            r += 1
        else:
            self.ent_prefix = None
            native = ("%APPDATA%\\HelloGames\\NMS" if IS_WINDOWS
                      else "~/Library/Application Support/HelloGames/NMS")
            hint = QLabel(
                f"The game folder ({native}) is probed automatically on this "
                "system — no extra path is needed.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color: gray;")
            g.addWidget(hint, r, 0, 1, 3)
            r += 1

        g.addWidget(QLabel("Library path:"), r, 0,
                    Qt.AlignmentFlag.AlignRight |
                    Qt.AlignmentFlag.AlignVCenter)
        self.ent_library = QLineEdit()
        g.addWidget(self.ent_library, r, 1)
        b3 = QPushButton("Browse…")
        b3.clicked.connect(self._browse_library)
        b4 = QPushButton("Reset")
        b4.clicked.connect(self._reset_library)
        hb2 = QHBoxLayout()
        hb2.setContentsMargins(0, 0, 0, 0)
        hb2.addWidget(b3)
        hb2.addWidget(b4)
        hb2.addStretch(1)
        row_w2 = QWidget()
        row_w2.setLayout(hb2)
        g.addWidget(row_w2, r, 2)
        g.setColumnStretch(1, 1)
        lay.addWidget(grp)

        if IS_LINUX:
            hint2 = QLabel(
                "Used on Linux/Proton to locate the game cache. Leave empty "
                "to probe the standard Steam locations.")
            hint2.setWordWrap(True)
            hint2.setStyleSheet("color: gray;")
            lay.addWidget(hint2)

        brow = QHBoxLayout()
        self.btn_save_cfg = QPushButton("Save")
        self.btn_save_cfg.clicked.connect(self.do_save_config)
        self.btn_restore_def = QPushButton("Restore defaults")
        self.btn_restore_def.clicked.connect(self._restore_defaults)
        self.btn_detect_now = QPushButton("Detect NMS cache now")
        self.btn_detect_now.clicked.connect(self._detect_caches_log)
        for b in (self.btn_save_cfg, self.btn_restore_def, self.btn_detect_now):
            brow.addWidget(b)
        brow.addStretch(1)
        lay.addLayout(brow)

        grp5 = QGroupBox("File locations (read-only)")
        g5 = QGridLayout(grp5)
        g5.setContentsMargins(10, 10, 10, 10)
        for i, (label, path) in enumerate(
                (("config.txt", CONFIG_FILE),
                 ("State / backups", state_dir()))):
            lab = QLabel(label)
            lab.setStyleSheet("color: gray;")
            val = QLabel(str(path))
            val.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            # Paths can be long; wrap instead of widening the tab (the
            # window follows the app frame, not the text).
            val.setWordWrap(True)
            g5.addWidget(lab, i, 0)
            g5.addWidget(val, i, 1)
        g5.setColumnStretch(1, 1)
        lay.addWidget(grp5)
        lay.addStretch(1)

        tab_lay = QVBoxLayout(self.tab_settings)
        tab_lay.setContentsMargins(4, 4, 4, 4)
        tab_lay.addWidget(scroll)

    # ------------------------------------------------------------------ log

    def log(self, level: str, msg: str):
        """Thread-safe log line (queued, rendered by the main thread)."""
        self.q.put(("log", level, msg))

    def _append_log(self, level: str, msg: str):
        color = _LOG_COLORS.get(level, _LOG_DEFAULT)
        self.logview.append(
            f'<span style="color:{color};">'
            f'{_html.escape(msg).replace("\n", "<br>")}</span>')
        doc = self.logview.document()
        if doc.blockCount() > _MAX_LOG_BLOCKS:
            excess = doc.blockCount() - _MAX_LOG_BLOCKS
            for _ in range(excess):
                doc.removeBlock(0)
        self.logview.moveCursor(QTextCursor.MoveOperation.End)

    # ---------------------------------------------------------------- workers

    def _run_bg(self, fn, *args, **kwargs):
        """Run fn(*args) in a worker thread; results arrive via the queue.

        While a worker runs, all action buttons are disabled. fn should
        return a ("done", payload) tuple OR push ("log"/"progress") items
        to self.q itself and return its result.
        """
        if self.worker_busy:
            QMessageBox.information(self, APP_TITLE,
                                    "Another operation is still running.")
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
                self.q.put(("error", ("unexpected",
                                      f"{type(e).__name__}: {e}")))

        threading.Thread(target=runner, daemon=True).start()

    @_qt_slot
    def _poll_queue(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                try:
                    if kind == "log":
                        self._append_log(item[1], item[2])
                    elif kind == "progress":
                        done, total, msg = item[1], item[2], item[3]
                        if total:
                            self.progress.setRange(0, total)
                            self.progress.setValue(done)
                            self.lbl_progress.setText(f"{done}/{total}  {msg}")
                        else:
                            self.lbl_progress.setText(msg)
                    elif kind == "done":
                        self._on_worker_done(item[1])
                    elif kind == "error":
                        self._on_worker_error(item[1])
                except Exception as e:
                    # One bad queue item must not kill the pump.
                    self._slot_failed(f"_poll_queue/{kind}", e)
        except queue.Empty:
            pass

    def _on_worker_done(self, result):
        self.worker_busy = False
        self._set_busy(False)
        self.progress.setValue(0)
        self.lbl_progress.setText("")
        self._refresh_all()

    def _on_worker_error(self, exc_pair):
        self.worker_busy = False
        self._set_busy(False)
        self.progress.setValue(0)
        self.lbl_progress.setText("")
        kind, msg = exc_pair
        self.log("err", msg)
        self._refresh_all()
        title = "Network error" if kind == "network" else "Unexpected error"
        QMessageBox.critical(self, title, msg)

    def _set_busy(self, busy: bool):
        for b in (self.btn_sync_all, self.btn_sync_sel, self.btn_sync_force,
                  self.btn_install, self.btn_uninstall):
            b.setEnabled(not busy)
        if busy:
            self.statusBar().showMessage("Working…")
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
        tree.setUpdatesEnabled(False)
        # First selected expedition id (str); _tree_selection() returns a
        # list, which is not hashable and must not be used as a dict key.
        _sel = self._tree_selection()
        prev_sel = _sel[0] if _sel else None
        tree.clear()
        self._tree_items = {}
        for exp in self.catalog:
            redux = exp.latest_redux
            orig_cell = self._status_cell(exp.id, "Originals")
            redux_cell = self._status_cell(exp.id, "Redux")
            inst = self.state.get("installed") or {}
            if inst.get("exp_id") == exp.id:
                status = (f"INSTALLED "
                          f"({inst.get('mode')}/{inst.get('difficulty')})")
            else:
                status = ("not downloaded" if not self.status
                          else "downloaded")
            item = QTreeWidgetItem(tree, [
                exp.id, exp.name,
                redux.id if redux else "—",
                orig_cell, redux_cell, status])
            item.setData(0, Qt.ItemDataRole.UserRole, exp.id)
            self._tree_items[exp.id] = item
            if inst.get("exp_id") == exp.id:
                item.setForeground(5, QColor("#2e7d32"))
        # keep previous selection if possible
        if prev_sel and prev_sel in self._tree_items:
            tree.setCurrentItem(self._tree_items[prev_sel])
            tree.scrollToItem(self._tree_items[prev_sel])
        tree.setUpdatesEnabled(True)

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
        names = [f"{e.id}  —  {e.name}" for e in self.catalog]
        current = self.cmb_exp.currentText()
        self.cmb_exp.blockSignals(True)
        self.cmb_exp.clear()
        self.cmb_exp.addItems(names)
        if current in names:
            i = names.index(current)
        else:
            i = 0
        self.cmb_exp.setCurrentIndex(i)
        self.cmb_exp.blockSignals(False)

        self._update_redux_state()
        self._on_install_choice()
        self._refresh_installed_label()

    def _refresh_installed_label(self):
        inst = self.state.get("installed") or {}
        if inst:
            text = (f"{inst['exp_id']}  ·  "
                    f"{inst.get('mode')}/{inst.get('difficulty')}\n"
                    f"Cache: {self.state.get('cache_dir', '?')}")
            if inst.get("custom"):
                text += (f"\nCustomization: "
                         f"{len(inst['custom'])} value(s) saved")
            if self.state.get("backup_cache"):
                text += f"\nBackup: {self.state['backup_cache']}"
        else:
            text = "(nothing installed)"
        self.lbl_installed.setText(text)

    @_qt_slot
    def _update_statusbar(self):
        n = len(self.status)
        inst = self.state.get("installed") or {}
        inst_txt = (f"{inst['exp_id']} "
                    f"({inst.get('mode')}/{inst.get('difficulty')})"
                    if inst else "none")
        self.statusBar().showMessage(
            f"Library: {n} files · Installed: {inst_txt} · Ready")

    # -------------------------------------------------------- library tab

    def _tree_selection(self):
        return [i.data(0, Qt.ItemDataRole.UserRole)
                for i in self.tree.selectedItems()]

    @_qt_slot
    def _on_tree_double_click(self, _item, _column=0):
        sel = self._tree_selection()
        if not sel:
            return
        self.tabs.setCurrentWidget(self.tab_install)
        self._set_install_exp(sel[0])
        self._on_exp_change()

    # ---------------------------------------------------------- install tab

    def _exp_from_combo(self):
        val = self.cmb_exp.currentText()
        for e in self.catalog:
            if f"{e.id}  —  {e.name}" == val:
                return e
        return None

    def _current_diff(self) -> str:
        for d in DIFFICULTIES:
            if self._diff_radio(d).isChecked():
                return d
        return "Defaults"

    def _set_install_exp(self, exp_id: str):
        for e in self.catalog:
            if e.id == exp_id:
                self.cmb_exp.setCurrentText(f"{e.id}  —  {e.name}")
                return

    @_qt_slot
    def _on_exp_change(self, *_):
        self._update_redux_state()
        self._on_install_choice()

    def _update_redux_state(self):
        exp = self._exp_from_combo()
        if exp is not None and not exp.latest_redux:
            self.rb_redux.setEnabled(False)
            if self.rb_redux.isChecked():
                self.rb_original.setChecked(True)
        else:
            self.rb_redux.setEnabled(True)

    @_qt_slot
    def _on_install_choice(self, *_):
        """Update the combo-state hint + Install button label."""
        exp = self._exp_from_combo()
        if exp is None:
            return
        mode = "Redux" if self.rb_redux.isChecked() else "Originals"
        diff = self._current_diff()
        if mode == "Redux" and not exp.latest_redux:
            self.rb_original.setChecked(True)
            mode = "Originals"
        key = (exp.id, mode, diff)
        downloaded = key in self.status
        self.btn_install.setText(
            "Download first" if not downloaded else "Install")
        self.lbl_comb_state.setText(
            ("Downloaded ✓" if downloaded
             else f"{mode}/{diff} not downloaded yet — click the button "
                  f"to download it")
            + ("" if exp.latest_redux
               else f"   ({exp.name} has no Redux version)"))
        self.lbl_comb_state.setStyleSheet(
            f"color: {'#2e7d32' if downloaded else 'gray'};")
        self._load_preset_form()

    # ------------------------------------------------ customization form

    @staticmethod
    def _humanize(prop):
        return _re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", prop)

    def _prop_display(self, p):
        return p.get("display") or self._humanize(p["prop"])

    def _build_custom_grid(self, grid: QGridLayout):
        self.custom_vars = {}
        self.custom_info = {}
        try:
            groups, _ = customize.load_spec()
        except Exception as e:
            err = QLabel(
                f"Could not load the customization parameters: {e}\n"
                "Run a sync (it fills the local source cache) and restart "
                "the GUI.")
            err.setWordWrap(True)
            err.setStyleSheet("color: #a00000;")
            grid.addWidget(err, 0, 0, 1, 2)
            return
        r = 0
        for g in groups:
            hdr = QLabel(g["name"])
            f = hdr.font()
            f.setBold(True)
            hdr.setFont(f)
            grid.addWidget(hdr, r, 0, 1, 2,
                           Qt.AlignmentFlag.AlignLeft)
            r += 1
            for p in g["props"]:
                label = QLabel(self._prop_display(p))
                label.setAlignment(
                    Qt.AlignmentFlag.AlignRight |
                    Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(label, r, 0)
                combo = QComboBox()
                opts = p.get("options")
                if opts:
                    combo.addItems(
                        [customize.DEFAULT_TEXT] + [o["text"] for o in opts])
                elif p["type"] == "bool":
                    combo.addItems(
                        [customize.DEFAULT_TEXT, "true", "false"])
                else:
                    # free-form (int / float / string / seed)
                    combo.setEditable(True)
                    combo.setInsertPolicy(
                        QComboBox.InsertPolicy.NoInsert)
                    combo.lineEdit().setPlaceholderText("")
                combo.setFixedWidth(340)
                # help text on focus / label click; state on any change
                prop = p["prop"]
                label.setProperty("exped_prop", prop)
                combo.setProperty("exped_prop", prop)
                label.installEventFilter(self)
                combo.installEventFilter(self)
                combo.currentTextChanged.connect(
                    lambda _t, p=p: (self._custom_help(p),
                                     self._update_custom_state()))
                self.custom_vars[prop] = combo
                self.custom_info[prop] = p
                grid.addWidget(combo, r, 1)
                r += 1
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(r, 1)

    def eventFilter(self, obj, event):
        try:
            t = event.type()
            if t in (QEvent.Type.FocusIn, QEvent.Type.MouseButtonPress):
                prop = obj.property("exped_prop")
                if prop is not None:
                    p = self.custom_info.get(prop)
                    if p is not None:
                        self._custom_help(p)
            return super().eventFilter(obj, event)
        except Exception as e:
            self._slot_failed("eventFilter", e)
            return False

    @_qt_slot
    def _custom_help(self, p):
        if not p:
            self.lbl_custom_help.setText(" ")
            return
        text = " ".join(str(p.get("description") or "").split())
        text = text.replace("<br>", " · ").replace("**", "")
        w = str(p.get("warning") or "")
        if w:
            text += (f"    ⚠ {w.replace('<br>', ' ').replace('**', '')}"
                     if text else "")
        self.lbl_custom_help.setText(text.strip() or "(no description)")

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

    @_qt_slot
    def _load_preset_form(self, notify=False):
        vars_ = getattr(self, "custom_vars", None)
        if not vars_:
            return
        try:
            preset = customize.load_preset(self._current_diff())
        except Exception:
            preset = {}
        for prop, combo in vars_.items():
            combo.blockSignals(True)
            if prop in preset:
                combo.setCurrentText(
                    self._value_to_display(preset[prop],
                                           self.custom_info[prop]))
            else:
                combo.setCurrentText(customize.DEFAULT_TEXT)
            combo.blockSignals(False)
        self._update_custom_state()
        if notify:
            self.log("info",
                     f"Loaded the {self._current_diff()} preset values "
                     f"into the customization form.")

    @_qt_slot
    def _reset_custom_form(self):
        for combo in getattr(self, "custom_vars", {}).values():
            combo.blockSignals(True)
            combo.setCurrentText(customize.DEFAULT_TEXT)
            combo.blockSignals(False)
        self._update_custom_state()

    def _apply_custom_values(self, flat):
        for prop, value in (flat or {}).items():
            combo = getattr(self, "custom_vars", {}).get(prop)
            info = getattr(self, "custom_info", {}).get(prop)
            if combo is not None and info is not None:
                combo.blockSignals(True)
                combo.setCurrentText(self._value_to_display(value, info))
                combo.blockSignals(False)
        self._update_custom_state()

    def _current_custom_flat(self):
        out = {}
        for prop, combo in getattr(self, "custom_vars", {}).items():
            disp = combo.currentText().strip()
            if not disp or disp == customize.DEFAULT_TEXT:
                continue
            out[prop] = self._display_to_value(disp, self.custom_info[prop])
        return out

    @_qt_slot
    def _update_custom_state(self):
        if not getattr(self, "custom_vars", None):
            return
        diff = self._current_diff()
        try:
            preset = customize.load_preset(diff)
        except Exception:
            preset = {}
        flat = self._current_custom_flat()
        n = sum(1 for k, v in flat.items() if preset.get(k) != v)
        if n:
            self.lbl_custom_state.setText(
                f"{n} parameter(s) changed vs {diff} — the file will be "
                f"generated at install time")
            self.lbl_custom_state.setStyleSheet("color: #8a6d00;")
        else:
            self.lbl_custom_state.setText(
                "No changes — the pre-built file will be installed")
            self.lbl_custom_state.setStyleSheet("color: gray;")

    @_qt_slot
    def _detect_caches(self):
        found = installer.find_nms_cache_dirs()
        self.cmb_cache.blockSignals(True)
        self.cmb_cache.clear()
        self.cmb_cache.addItems([str(c) for c in found])
        self.cmb_cache.blockSignals(False)
        if not found:
            hint = ("Play the game once so it creates its data folder."
                    if not IS_LINUX else
                    "Play the game once (creates the prefix), or set the "
                    "Proton prefix in Settings.")
            self.lbl_cache_warn.setText(
                f"No NMS cache folder found. {hint}")
            return
        self.lbl_cache_warn.setText("")
        # default: the one already recorded in state, else the one containing
        # the cache file, else the first
        state_dir_val = (self.state.get("cache_dir") or "")
        def contains_file(c):
            return installer._resolve_cache_file(c).exists()
        target = next((c for c in found if str(c) == state_dir_val), None)
        if target is None:
            target = next((c for c in found if contains_file(c)), found[0])
        self.cmb_cache.setCurrentText(str(target))

    @_qt_slot
    def _detect_caches_log(self):
        found = installer.find_nms_cache_dirs()
        if found:
            for c in found:
                self.log("ok", f"Cache dir found: {c}")
        else:
            extra = (" On Linux, check Settings → Proton prefix."
                     if IS_LINUX else "")
            self.log("warn", "No NMS cache folder found." + extra)
        self._detect_caches()

    # -------------------------------------------------------------- actions

    @_qt_slot
    def do_sync(self, only_exps=None, force=False):
        exps = [e for e in self.catalog if e.id in only_exps] if only_exps \
            else None
        label = (f"{len(only_exps)} selected" if only_exps else "all") + \
                ("  [force]" if force else "")
        self.log("info", f"Sync started ({label})…")

        def _sync_one(only_exp, force_):
            def progress_cb(done, total, msg):
                self.q.put(("progress", done, total, msg))
            return syncmod.sync(force=force_, only_exp=only_exp,
                                progress=progress_cb)

        def work():
            if exps:
                # sync each selected expedition through the real API
                got = 0
                for e in exps:
                    d, s = _sync_one(e.id, force)
                    got += d
                    self.q.put(("progress", got,
                                max(len(exps), 1), f"{e.id} done"))
                self.q.put(("log", "ok",
                            f"Sync complete: {got} downloaded/updated."))
            else:
                d, s = _sync_one(None, force)
                self.q.put(("log", "ok",
                            f"Sync complete: {d} downloaded/updated, "
                            f"{s} unchanged."))
            return None

        self._run_bg(work)

    @_qt_slot
    def do_install(self):
        exp = self._exp_from_combo()
        if exp is None:
            return
        mode = "Redux" if self.rb_redux.isChecked() else "Originals"
        diff = self._current_diff()
        if mode == "Redux" and not exp.latest_redux:
            mode = "Originals"
            self.rb_original.setChecked(True)
        key = (exp.id, mode, diff)
        cache = self.cmb_cache.currentText().strip()

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
            self.log("info",
                     f"Downloading {exp.id} ({mode}/{diff}) before "
                     f"install…")

            def work():
                def progress_cb(done, total, msg):
                    self.q.put(("progress", done, total, msg))
                d, s = syncmod.sync(force=False, only_exp=exp.id,
                                    progress=progress_cb)
                self.q.put(("log", "ok", f"Download finished: {d} file(s)."))
                return None

            self._run_bg(work)
            return

        if not cache:
            self._detect_caches()
            cache = self.cmb_cache.currentText().strip()
            if not cache:
                hint = ("Play the game once so it creates its data folder."
                        if not IS_LINUX else
                        "Play the game once, or set the Proton prefix in "
                        "the Settings tab.")
                QMessageBox.warning(
                    self, APP_TITLE,
                    "No NMS cache folder found.\n\n" + hint)
                return

        n_custom = (sum(1 for k, v in flat.items() if preset.get(k) != v)
                    if changed else 0)
        msg = (f"Install {exp.name} ({exp.id})?\n\n"
               f"Version: {mode}   Difficulty: {diff}\n"
               f"Target cache: {cache}\n"
               + (f"Custom parameters: {n_custom} — the file will be "
                  f"generated from the cached sources\n" if changed else
                  "\n")
               + "\nThe current season cache file (SEASON_DATA_CACHE_S*.JSON) "
               "will be backed up automatically.\n\n"
               "⚠ Put STEAM IN OFFLINE MODE before launching NMS, or the "
               "game will overwrite the installed expedition.")
        if (QMessageBox.question(
                self, "Install expedition", msg,
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
                != QMessageBox.StandardButton.Yes):
            return

        self.log("info",
                 f"Installing {exp.id} ({mode}/{diff}) → {cache} …")

        def work():
            src_file = None
            custom = dict(flat) if changed else None
            if changed:
                self.q.put(
                    ("log", "info",
                     "Generating the custom expedition file…"))
                try:
                    src_file, custom = customize.install_source_from_flat(
                        exp.id, mode, diff, flat)
                except Exception as e:
                    self.q.put(("log", "err",
                                f"Could not generate the custom file: {e}"))
                    return False
            ok = installer.install(exp.id, mode, diff, interactive=False,
                                   cache_dir=cache,
                                   source_file=(str(src_file)
                                                if src_file else None),
                                   custom=custom)
            self.q.put(("log", "ok" if ok else "err",
                        "Installation complete. Start NMS in OFFLINE mode."
                        if ok else "Installation FAILED — see log."))
            return ok

        self._run_bg(work)

    @_qt_slot
    def do_uninstall(self):
        inst = self.state.get("installed")
        if not inst:
            QMessageBox.information(
                self, APP_TITLE, "No expedition is currently installed.")
            return
        if (QMessageBox.question(
                self, "Uninstall expedition",
                f"Restore the original cache (undo {inst['exp_id']} "
                f"{inst.get('mode')}/{inst.get('difficulty')})?\n\n"
                "The backup of the original cache will be kept in the "
                "state directory.")
                != QMessageBox.StandardButton.Yes):
            return
        self.log("info", "Uninstalling…")

        def work():
            ok = installer.uninstall(interactive=False)
            self.q.put(("log", "ok" if ok else "err",
                        "Uninstallation complete." if ok
                        else "Uninstall FAILED."))
            return ok

        self._run_bg(work)

    # ------------------------------------------------------------ settings

    def _populate_settings(self):
        cfg = load_config()
        if self.ent_prefix is not None:
            self.ent_prefix.setText(cfg.get("proton_prefix", ""))
        self.ent_library.setText(cfg.get("library_path", ""))

    @_qt_slot
    def do_save_config(self):
        new = {"library_path": (self.ent_library.text().strip()
                                or str(PROJECT_ROOT
                                       / "ExpeditionManagerLibrary"))}
        if self.ent_prefix is not None:
            new["proton_prefix"] = self.ent_prefix.text().strip()
        if not new["library_path"]:
            QMessageBox.warning(self, APP_TITLE,
                                "Library path cannot be empty.")
            return
        save_config(new)
        self.log("ok", f"Configuration saved → {CONFIG_FILE}")
        self._populate_settings()
        self._refresh_all()  # library path may have changed

    @_qt_slot
    def _browse_prefix(self):
        if self.ent_prefix is None:
            return
        d = QFileDialog.getExistingDirectory(
            self, "Select the NMS Proton prefix", str(PROJECT_ROOT))
        if d:
            self.ent_prefix.setText(d)

    @_qt_slot
    def _standard_prefix(self):
        if self.ent_prefix is None:
            return
        self.ent_prefix.setText(DEFAULT_PREFIX)

    @_qt_slot
    def _browse_library(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select the expedition library folder", str(PROJECT_ROOT))
        if d:
            self.ent_library.setText(d)

    @_qt_slot
    def _reset_library(self):
        self.ent_library.setText(
            str(PROJECT_ROOT / "ExpeditionManagerLibrary"))

    @_qt_slot
    def _restore_defaults(self):
        from .config import DEFAULT_CONFIG
        for k, v in DEFAULT_CONFIG.items():
            if k == "proton_prefix" and self.ent_prefix is not None:
                self.ent_prefix.setText(v)
            elif k == "library_path":
                self.ent_library.setText(v)

    # --------------------------------------------------------------- window

    def closeEvent(self, event):
        try:
            self._timer.stop()
        except Exception:
            pass
        # Worker threads are daemons: they die with the process.
        event.accept()
