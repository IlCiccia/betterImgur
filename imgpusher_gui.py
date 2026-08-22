#!/usr/bin/env python3
"""
imgpusher_gui.py — GUI per caricare immagini sulla tua repo GitHub personale
e ottenere subito il link "raw" diretto, con drag & drop, scelta della
cartella di destinazione (esistente o nuova) e copia automatica del link
negli appunti.

Dipendenze:
    - Python 3.8+
    - git installato, nel PATH, con la repo già clonata e collegata a un
      remote GitHub funzionante (va bene anche via alias SSH, tipo
      git@github.com-ilciccia:...)
    - (opzionale, per il drag & drop vero e proprio) tkinterdnd2:
          pip install tkinterdnd2
      Senza questa libreria il programma funziona comunque tramite il
      pulsante "Sfoglia file...".

Avvio:
    python3 imgpusher_gui.py

Alla prima esecuzione ti verrà chiesto di selezionare la cartella locale
della repo (quella che contiene la sottocartella .git). La scelta viene
salvata in ~/.imgpusher_config.json per le volte successive.
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from urllib.parse import quote

# --- Drag & drop opzionale --------------------------------------------------
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

CONFIG_PATH = Path.home() / ".imgpusher_config.json"
NEW_FOLDER_LABEL = "+ Nuova cartella..."
ROOT_FOLDER_LABEL = "(cartella principale)"


# --- Configurazione persistente ---------------------------------------------
def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"repo_dir": ""}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


# --- Operazioni Git ----------------------------------------------------------
class GitError(Exception):
    pass


def run_git(args, cwd) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def get_repo_info(repo_dir: str):
    """Restituisce (owner, repo, branch) leggendo la repo git locale."""
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_dir)
    remote_url = run_git(["config", "--get", "remote.origin.url"], repo_dir)

    # Supporta sia URL SSH (anche con alias host tipo github.com-ilciccia)
    # sia URL HTTPS.
    if remote_url.startswith("git@") or "@" in remote_url.split("//")[0]:
        path_part = remote_url.split(":")[-1]
    else:
        path_part = remote_url.split("github.com/")[-1]

    if path_part.endswith(".git"):
        path_part = path_part[:-4]

    owner, repo = path_part.strip("/").split("/", 1)
    return owner, repo, branch


def list_existing_folders(repo_dir: str):
    """Elenca le sottocartelle della repo (escluse quelle nascoste tipo .git)."""
    folders = []
    repo_path = Path(repo_dir)
    for dirpath, dirnames, _ in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        rel = Path(dirpath).relative_to(repo_path)
        if str(rel) != ".":
            folders.append(str(rel).replace(os.sep, "/"))
    return sorted(folders)


def push_current_branch(repo_dir: str):
    """Fa push, impostando l'upstream automaticamente se manca."""
    try:
        run_git(["push", "--quiet"], repo_dir)
    except GitError as exc:
        message = str(exc).lower()
        if "upstream" in message or "set-upstream" in message:
            branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_dir)
            run_git(["push", "--set-upstream", "origin", branch, "--quiet"], repo_dir)
        else:
            raise


def upload_file(src_path: str, target_folder: str, repo_dir: str, log_fn) -> str:
    """Copia il file nella repo, fa commit+push, restituisce l'URL raw."""
    src = Path(src_path)
    if not src.is_file():
        raise GitError(f"File non trovato: {src_path}")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    new_name = f"{timestamp}_{src.name}"

    target_folder = target_folder.strip("/")
    dest_dir = Path(repo_dir) / target_folder if target_folder else Path(repo_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / new_name

    log_fn(f"Copio {src.name}...")
    shutil.copy2(src, dest_path)

    rel_path = dest_path.relative_to(repo_dir).as_posix()

    log_fn("git add...")
    run_git(["add", rel_path], repo_dir)

    log_fn("git commit...")
    run_git(["commit", "-m", f"add {rel_path}", "--quiet"], repo_dir)

    log_fn("git push...")
    push_current_branch(repo_dir)

    owner, repo, branch = get_repo_info(repo_dir)
    url_path = "/".join(quote(part) for part in rel_path.split("/"))
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{url_path}"


# --- Interfaccia grafica -----------------------------------------------------
BaseTk = TkinterDnD.Tk if DND_AVAILABLE else tk.Tk


class ImgPusherApp(BaseTk):
    def __init__(self):
        super().__init__()
        self.title("imgpusher")
        self.geometry("540x430")
        self.resizable(False, False)

        self.config_data = load_config()
        self.result_queue = queue.Queue()

        self._build_ui()
        self.after(100, self._poll_queue)

        if not self._repo_dir_valid():
            self.after(200, self._prompt_repo_dir)
        else:
            self._refresh_folder_list()

    # ---- setup repo ----
    def _repo_dir_valid(self) -> bool:
        repo_dir = self.config_data.get("repo_dir", "")
        return bool(repo_dir) and (Path(repo_dir) / ".git").is_dir()

    def _prompt_repo_dir(self):
        messagebox.showinfo(
            "Configurazione",
            "Seleziona la cartella locale della tua repo GitHub "
            "(quella che contiene la sottocartella .git).",
        )
        self._choose_repo_dir()

    def _choose_repo_dir(self):
        chosen = filedialog.askdirectory(title="Seleziona la cartella della repo")
        if not chosen:
            return
        if not (Path(chosen) / ".git").is_dir():
            messagebox.showerror(
                "Errore", "Quella cartella non contiene un repository git (.git non trovato)."
            )
            return
        self.config_data["repo_dir"] = chosen
        save_config(self.config_data)
        self.repo_label.config(text=f"Repo: {chosen}")
        self._refresh_folder_list()

    # ---- UI ----
    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        top_frame = ttk.Frame(self)
        top_frame.pack(fill="x", **pad)
        self.repo_label = ttk.Label(
            top_frame,
            text=f"Repo: {self.config_data.get('repo_dir') or '(non configurata)'}",
            foreground="#555555",
        )
        self.repo_label.pack(side="left")
        ttk.Button(top_frame, text="Cambia repo...", command=self._choose_repo_dir).pack(
            side="right"
        )

        folder_frame = ttk.Frame(self)
        folder_frame.pack(fill="x", **pad)
        ttk.Label(folder_frame, text="Cartella di destinazione:").pack(side="left")
        self.folder_var = tk.StringVar(value=ROOT_FOLDER_LABEL)
        self.folder_combo = ttk.Combobox(
            folder_frame, textvariable=self.folder_var, state="readonly", width=34
        )
        self.folder_combo.pack(side="left", padx=8)
        self.folder_combo.bind("<<ComboboxSelected>>", self._on_folder_selected)

        if DND_AVAILABLE:
            drop_text = "Trascina qui uno o più file\n(oppure usa il pulsante sotto)"
        else:
            drop_text = (
                "Drag & drop non disponibile\n"
                "(installa con: pip install tkinterdnd2)\n"
                "Usa il pulsante sotto"
            )
        self.drop_zone = tk.Label(
            self,
            text=drop_text,
            relief="ridge",
            borderwidth=2,
            bg="#f4f4f4",
            fg="#666666",
            height=8,
            justify="center",
        )
        self.drop_zone.pack(fill="both", expand=True, **pad)
        self.drop_zone.bind("<Button-1>", lambda _e: self._browse_files())

        if DND_AVAILABLE:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self._on_drop)

        ttk.Button(self, text="Sfoglia file...", command=self._browse_files).pack(pady=(0, 6))

        self.status_var = tk.StringVar(value="Pronto.")
        ttk.Label(self, textvariable=self.status_var, foreground="#555555").pack(fill="x", **pad)

        result_frame = ttk.Frame(self)
        result_frame.pack(fill="x", **pad)
        self.result_var = tk.StringVar(value="")
        self.result_entry = ttk.Entry(result_frame, textvariable=self.result_var, state="readonly")
        self.result_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(result_frame, text="Copia link", command=self._copy_result).pack(
            side="left", padx=(6, 0)
        )

    # ---- gestione cartelle ----
    def _refresh_folder_list(self):
        repo_dir = self.config_data.get("repo_dir")
        if not repo_dir:
            return
        folders = list_existing_folders(repo_dir)
        values = [ROOT_FOLDER_LABEL] + folders + [NEW_FOLDER_LABEL]
        self.folder_combo["values"] = values
        self.folder_var.set(ROOT_FOLDER_LABEL)

    def _on_folder_selected(self, _event):
        if self.folder_var.get() == NEW_FOLDER_LABEL:
            name = simpledialog.askstring(
                "Nuova cartella",
                "Nome della nuova cartella (es. avatar oppure token/mostri):",
            )
            if name:
                name = name.strip().strip("/")
                values = list(self.folder_combo["values"])
                if name not in values:
                    values.insert(-1, name)
                    self.folder_combo["values"] = values
                self.folder_var.set(name)
            else:
                self.folder_var.set(ROOT_FOLDER_LABEL)

    # ---- selezione file ----
    def _browse_files(self):
        paths = filedialog.askopenfilenames(title="Seleziona una o più immagini")
        if paths:
            self._start_upload(list(paths))

    def _on_drop(self, event):
        paths = self.tk.splitlist(event.data)
        if paths:
            self._start_upload(list(paths))

    # ---- upload ----
    def _start_upload(self, paths):
        if not self._repo_dir_valid():
            messagebox.showerror("Errore", "Configura prima la cartella della repo.")
            return

        folder = self.folder_var.get()
        folder = "" if folder == ROOT_FOLDER_LABEL else folder

        repo_dir = self.config_data["repo_dir"]
        self.status_var.set("Caricamento in corso...")
        self.result_var.set("")

        thread = threading.Thread(
            target=self._upload_worker, args=(paths, folder, repo_dir), daemon=True
        )
        thread.start()

    def _upload_worker(self, paths, folder, repo_dir):
        urls = []
        for path in paths:
            try:
                url = upload_file(
                    path,
                    folder,
                    repo_dir,
                    log_fn=lambda msg: self.result_queue.put(("status", msg)),
                )
                urls.append(url)
            except GitError as exc:
                self.result_queue.put(("error", str(exc)))
                return
        self.result_queue.put(("done", urls))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.result_queue.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind == "error":
                    self.status_var.set("Errore.")
                    messagebox.showerror("Errore durante il caricamento", payload)
                elif kind == "done":
                    urls = payload
                    text = "\n".join(urls)
                    self.result_var.set(urls[0] if len(urls) == 1 else f"{len(urls)} file caricati")
                    self.clipboard_clear()
                    self.clipboard_append(text)
                    if len(urls) == 1:
                        self.status_var.set("Fatto. Link copiato negli appunti.")
                    else:
                        self.status_var.set(
                            f"Fatto. {len(urls)} link copiati negli appunti (uno per riga)."
                        )
                    self._refresh_folder_list()
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _copy_result(self):
        text = self.result_var.get()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_var.set("Copiato negli appunti.")


if __name__ == "__main__":
    if not shutil.which("git"):
        print("Errore: git non risulta installato o non è nel PATH.")
        sys.exit(1)
    app = ImgPusherApp()
    app.mainloop()