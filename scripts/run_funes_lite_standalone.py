"""Graphical, non-interactive entry point for the portable FUNES Lite build."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import sys
import threading
import tkinter as tk
from tkinter import ttk


def _application_directory() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def _record_fatal_error(output_dir: Path, message: str) -> None:
    """Best-effort persistent diagnostic for failures shown in the window."""

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "funes_lite_fatal_error.txt").write_text(
            "FUNES — FRET Unified Normalization and Extraction Suite\n"
            f"Error fatal: {message}\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _append_runtime_log(output_dir: Path, message: str) -> None:
    """Best-effort startup and completion trace for packaged diagnostics."""

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        with (output_dir / "funes_lite_runtime.log").open("a", encoding="utf-8") as stream:
            stream.write(f"{timestamp} {message}\n")
    except OSError:
        pass


class FunesLiteWindow:
    """Small splash/progress window; it never asks for an analysis decision."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("FUNES — FRET Unified Normalization and Extraction Suite")
        self.root.geometry("560x390")
        self.root.resizable(False, False)
        self.root.configure(background="#10263c")
        self.status = tk.StringVar(value="Iniciando análisis automático provisional…")
        self.progress_text = tk.StringVar(value="Progreso total: 0 / 0")
        self._build()

    def _build(self) -> None:
        panel = tk.Frame(self.root, background="#10263c", padx=36, pady=28)
        panel.pack(fill="both", expand=True)
        mark = tk.Canvas(
            panel,
            width=116,
            height=82,
            background="#10263c",
            highlightthickness=0,
        )
        mark.create_line(32, 41, 84, 41, fill="#b8d5e8", width=5)
        mark.create_oval(12, 21, 52, 61, fill="#55d6d0", outline="")
        mark.create_oval(64, 21, 104, 61, fill="#f7c873", outline="")
        mark.create_text(32, 41, text="C0", fill="#10263c", font=("Segoe UI", 10, "bold"))
        mark.create_text(84, 41, text="C1", fill="#10263c", font=("Segoe UI", 10, "bold"))
        mark.pack(pady=(0, 8))
        tk.Label(panel, text="FUNES", font=("Segoe UI", 26, "bold"), foreground="white", background="#10263c").pack()
        tk.Label(panel, text="FRET Unified Normalization and Extraction Suite", font=("Segoe UI", 10), foreground="#b8d5e8", background="#10263c").pack(pady=(2, 24))
        ttk.Progressbar(panel, mode="determinate", length=460, maximum=1, variable=tk.DoubleVar(value=0)).pack()
        self.bar = panel.winfo_children()[-1]
        tk.Label(panel, textvariable=self.progress_text, font=("Segoe UI", 10), foreground="white", background="#10263c").pack(pady=(9, 4))
        tk.Label(panel, textvariable=self.status, font=("Segoe UI", 11, "bold"), foreground="#55d6d0", background="#10263c", wraplength=470).pack(pady=(8, 14))
        tk.Label(panel, text="Advertencia: análisis automático provisional, no validado científicamente.", font=("Segoe UI", 9), foreground="#f7c873", background="#10263c", wraplength=470).pack(side="bottom")

    def update_progress(self, status: str, completed: int, total: int) -> None:
        self.status.set(status)
        self.progress_text.set(f"Progreso total: {completed} / {total}")
        self.bar.configure(maximum=max(total, 1), value=completed)

    def complete(self, completed: int, failures: int, output_dir: Path) -> None:
        total = completed + failures
        self.bar.configure(value=self.bar.cget("maximum"))
        self.progress_text.set(f"Progreso total: {total} / {total}")
        detail = "sin fallos" if failures == 0 else f"{failures} fallo(s) registrado(s) en informes laterales"
        self.status.set(f"Análisis finalizado: {completed} posición(es) exportada(s), {detail}.\nResultados: {output_dir}")

    def fatal(self, message: str) -> None:
        self.status.set(f"Error fatal: {message}")


def main() -> int:
    app_root = _application_directory()
    output_dir = app_root / "output"
    _append_runtime_log(output_dir, "startup: importing FUNES analysis route")
    sys.path.insert(0, str(app_root / "funes_files"))
    from funes.simple_analysis import SimpleAnalysisError, SimpleFretAnalysisConfig, run_simple_fret_analysis
    _append_runtime_log(output_dir, "startup: analysis route imported")

    root = tk.Tk()
    window = FunesLiteWindow(root)
    _append_runtime_log(output_dir, "startup: window initialized")

    def progress(status: str, completed: int, total: int) -> None:
        root.after(0, window.update_progress, status, completed, total)

    def run() -> None:
        _append_runtime_log(output_dir, "analysis: batch started")
        try:
            result = run_simple_fret_analysis(
                app_root / "input", output_dir, SimpleFretAnalysisConfig(progress_callback=progress)
            )
        except SimpleAnalysisError as exc:
            message = str(exc)
            _record_fatal_error(output_dir, message)
            _append_runtime_log(output_dir, f"analysis: fatal: {message}")
            root.after(0, window.fatal, message)
            return
        except Exception as exc:  # Unexpected faults are fatal, but shown in the app.
            message = f"Error inesperado: {exc}"
            _record_fatal_error(output_dir, message)
            _append_runtime_log(output_dir, f"analysis: fatal: {message}")
            root.after(0, window.fatal, message)
            return
        _append_runtime_log(
            output_dir,
            f"analysis: completed with {len(result.positions)} export(s) and {len(result.failures)} failure(s)",
        )
        root.after(0, window.complete, len(result.positions), len(result.failures), output_dir)

    threading.Thread(target=run, daemon=True).start()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
