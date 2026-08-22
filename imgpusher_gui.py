#!/usr/bin/env python3
"""
imgpusher_gui.py — GUI per caricare immagini sulla tua repo GitHub personale
e ottenere subito il link "raw" diretto, oppure recuperare il link di
un'immagine già presente nella repo, senza dover ricaricare nulla.

Due schede:
  - "Aggiungi immagine": drag & drop (o Sfoglia file...) mette i file in
    una lista di attesa, senza toccare git. Solo premendo "Carica" viene
    eseguito l'upload effettivo (copia + git add + commit + push) e il
    link viene copiato negli appunti.
  - "Copia link": scegli una cartella già esistente nella repo, seleziona
    un'immagine già presente, ottieni il suo link raw senza ricaricarla.

In entrambe le schede, le cartelle tecniche (venv, .venv, env, __pycache__,
node_modules, e qualunque cartella nascosta) non compaiono mai negli elenchi.

Dipendenze:
    - Python 3.8+
    - git installato, nel PATH, con la repo già clonata e collegata a un
      remote GitHub funzionante (va bene anche via alias SSH)
    - (opzionale, per il drag & drop vero e proprio) tkinterdnd2:
          pip install tkinterdnd2
      Senza questa libreria il programma funziona comunque tramite il
      pulsante "Sfoglia file...".

Avvio:
    python3 imgpusher_gui.py
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
NEW_BRANCH_LABEL = "+ Nuovo branch..."

# Cartelle tecniche mai mostrate/attraversate negli elenchi (oltre a quelle
# nascoste, cioè che iniziano con '.').
EXCLUDED_DIR_NAMES = {"venv", ".venv", "env", "__pycache__", "node_modules"}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".tiff", ".ico"}


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
    branch = get_current_branch(repo_dir)
    remote_url = run_git(["config", "--get", "remote.origin.url"], repo_dir)

    if remote_url.startswith("git@") or "@" in remote_url.split("//")[0]:
        path_part = remote_url.split(":")[-1]
    else:
        path_part = remote_url.split("github.com/")[-1]

    if path_part.endswith(".git"):
        path_part = path_part[:-4]

    owner, repo = path_part.strip("/").split("/", 1)
    return owner, repo, branch


def get_current_branch(repo_dir: str) -> str:
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_dir)


def list_branches(repo_dir: str):
    output = run_git(["branch", "--format=%(refname:short)"], repo_dir)
    return [line.strip() for line in output.splitlines() if line.strip()]


def is_working_tree_clean(repo_dir: str) -> bool:
    return run_git(["status", "--porcelain"], repo_dir).strip() == ""


def sanitize_branch_name(name: str) -> str:
    """Sostituisce ogni spazio (singolo o multiplo) con un trattino."""
    return "-".join(name.split())


def checkout_branch(repo_dir: str, branch_name: str, create: bool = False):
    args = ["checkout"]
    if create:
        args.append("-b")
    args.append(branch_name)
    run_git(args, repo_dir)


def build_raw_url(repo_dir: str, rel_path: str) -> str:
    """Costruisce l'URL raw.githubusercontent.com per un file già nella repo."""
    owner, repo, branch = get_repo_info(repo_dir)
    url_path = "/".join(quote(part) for part in rel_path.split("/"))
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{url_path}"


def _is_excluded_dir(name: str) -> bool:
    return name.startswith(".") or name in EXCLUDED_DIR_NAMES


def list_existing_folders(repo_dir: str):
    """Elenca le sottocartelle "reali" della repo, escludendo quelle tecniche."""
    folders = []
    repo_path = Path(repo_dir)
    for dirpath, dirnames, _ in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d)]
        rel = Path(dirpath).relative_to(repo_path)
        if str(rel) != ".":
            folders.append(str(rel).replace(os.sep, "/"))
    return sorted(folders)


def list_image_files(repo_dir: str, folder: str):
    """Elenca i file immagine presenti direttamente dentro 'folder' (non ricorsivo)."""
    target = Path(repo_dir) / folder if folder else Path(repo_dir)
    if not target.is_dir():
        return []
    files = [
        entry.name
        for entry in target.iterdir()
        if entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return sorted(files)


def push_current_branch(repo_dir: str):
    """Fa push, impostando l'upstream automaticamente se manca."""
    try:
        run_git(["push", "--quiet"], repo_dir)
    except GitError as exc:
        message = str(exc).lower()
        if "upstream" in message or "set-upstream" in message:
            branch = get_current_branch(repo_dir)
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

    return build_raw_url(repo_dir, rel_path)


# --- Interfaccia grafica -----------------------------------------------------
BaseTk = TkinterDnD.Tk if DND_AVAILABLE else tk.Tk


class ImgPusherApp(BaseTk):
    def __init__(self):
        super().__init__()
        self.title("imgpusher")
        self.geometry("560x520")
        self.resizable(False, False)

        self.config_data = load_config()
        self.result_queue = queue.Queue()
        self.pending_paths = []  # file selezionati/trascinati, non ancora caricati

        self._build_ui()
        self.after(100, self._poll_queue)

        if not self._repo_dir_valid():
            self.after(200, self._prompt_repo_dir)
        else:
            self._refresh_branch_list()
            self._refresh_folder_lists()

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
        self._refresh_branch_list()
        self._refresh_folder_lists()

    # ---- gestione branch ----
    def _refresh_branch_list(self):
        repo_dir = self.config_data.get("repo_dir")
        if not repo_dir:
            return
        try:
            branches = list_branches(repo_dir)
            current = get_current_branch(repo_dir)
        except GitError as exc:
            messagebox.showerror("Errore nella lettura dei branch", str(exc))
            return
        self.branch_combo["values"] = branches + [NEW_BRANCH_LABEL]
        self.branch_var.set(current)

    def _on_branch_selected(self, _event):
        repo_dir = self.config_data.get("repo_dir")
        selected = self.branch_var.get()

        if selected == NEW_BRANCH_LABEL:
            raw_name = simpledialog.askstring("Nuovo branch", "Nome del nuovo branch:")
            if not raw_name or not raw_name.strip():
                self._refresh_branch_list()
                return
            branch_name = sanitize_branch_name(raw_name)
            create = True
        else:
            branch_name = selected
            create = False
            if branch_name == get_current_branch(repo_dir):
                return  # nessun cambiamento reale

        if not is_working_tree_clean(repo_dir):
            messagebox.showerror(
                "Impossibile cambiare branch",
                "Ci sono modifiche non salvate nella repo (fuori da questa app). "
                "Sistemale manualmente da terminale prima di cambiare branch.",
            )
            self._refresh_branch_list()
            return

        if self.pending_paths:
            self._clear_pending_state()
            self.status_var.set("Coda di caricamento svuotata per il cambio di branch.")

        try:
            checkout_branch(repo_dir, branch_name, create=create)
        except GitError as exc:
            messagebox.showerror("Errore nel cambio branch", str(exc))
            self._refresh_branch_list()
            return

        verb = "Creato e selezionato" if create else "Passato al"
        self.status_var.set(f'{verb} branch "{branch_name}".')
        self._refresh_branch_list()
        self._refresh_folder_lists()

    # ---- UI generale ----
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

        branch_frame = ttk.Frame(self)
        branch_frame.pack(fill="x", padx=12, pady=(0, 6))
        ttk.Label(branch_frame, text="Branch:").pack(side="left")
        self.branch_var = tk.StringVar(value="")
        self.branch_combo = ttk.Combobox(
            branch_frame, textvariable=self.branch_var, state="readonly", width=30
        )
        self.branch_combo.pack(side="left", padx=8)
        self.branch_combo.bind("<<ComboboxSelected>>", self._on_branch_selected)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        add_tab = ttk.Frame(notebook)
        link_tab = ttk.Frame(notebook)
        notebook.add(add_tab, text="Aggiungi immagine")
        notebook.add(link_tab, text="Copia link")

        self._build_add_tab(add_tab)
        self._build_link_tab(link_tab)

        # Area di stato/risultato, condivisa tra le due schede.
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

    # ---- scheda "Aggiungi immagine" ----
    def _build_add_tab(self, parent):
        pad = {"padx": 0, "pady": 6}

        folder_frame = ttk.Frame(parent)
        folder_frame.pack(fill="x", **pad)
        ttk.Label(folder_frame, text="Cartella di destinazione:").pack(side="left")
        self.add_folder_var = tk.StringVar(value=ROOT_FOLDER_LABEL)
        self.add_folder_combo = ttk.Combobox(
            folder_frame, textvariable=self.add_folder_var, state="readonly", width=32
        )
        self.add_folder_combo.pack(side="left", padx=8)
        self.add_folder_combo.bind("<<ComboboxSelected>>", self._on_add_folder_selected)

        if DND_AVAILABLE:
            drop_text = "Trascina qui uno o più file\n(verranno aggiunti alla lista sotto)"
        else:
            drop_text = (
                "Drag & drop non disponibile\n"
                "(installa con: pip install tkinterdnd2)\n"
                "Usa il pulsante sotto"
            )
        self.drop_zone = tk.Label(
            parent,
            text=drop_text,
            relief="ridge",
            borderwidth=2,
            bg="#f4f4f4",
            fg="#666666",
            height=6,
            justify="center",
        )
        self.drop_zone.pack(fill="both", expand=True, pady=(6, 4))
        self.drop_zone.bind("<Button-1>", lambda _e: self._browse_files())

        if DND_AVAILABLE:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self._on_drop)

        ttk.Button(parent, text="Sfoglia file...", command=self._browse_files).pack(pady=(0, 6))

        ttk.Label(parent, text="In attesa di caricamento:").pack(fill="x", pady=(2, 2))

        pending_frame = ttk.Frame(parent)
        pending_frame.pack(fill="both", expand=False)
        pending_scrollbar = ttk.Scrollbar(pending_frame, orient="vertical")
        self.pending_listbox = tk.Listbox(
            pending_frame, yscrollcommand=pending_scrollbar.set, height=5
        )
        pending_scrollbar.config(command=self.pending_listbox.yview)
        self.pending_listbox.pack(side="left", fill="both", expand=True)
        pending_scrollbar.pack(side="right", fill="y")

        button_row = ttk.Frame(parent)
        button_row.pack(fill="x", pady=(6, 0))
        ttk.Button(button_row, text="Rimuovi selezionato", command=self._remove_pending_selected).pack(
            side="left"
        )
        ttk.Button(button_row, text="Svuota lista", command=self._clear_pending).pack(
            side="left", padx=(6, 0)
        )
        self.upload_button = ttk.Button(
            button_row, text="Carica", command=self._confirm_upload, state="disabled"
        )
        self.upload_button.pack(side="right")

    def _on_add_folder_selected(self, _event):
        if self.add_folder_var.get() == NEW_FOLDER_LABEL:
            name = simpledialog.askstring(
                "Nuova cartella",
                "Nome della nuova cartella (es. avatar oppure token/mostri):",
            )
            if name:
                name = name.strip().strip("/")
                if _is_excluded_dir(name.split("/")[0]):
                    messagebox.showerror(
                        "Nome non valido",
                        f"'{name}' è un nome riservato (cartella tecnica) e non può essere usato.",
                    )
                    self.add_folder_var.set(ROOT_FOLDER_LABEL)
                    return
                values = list(self.add_folder_combo["values"])
                if name not in values:
                    values.insert(-1, name)
                    self.add_folder_combo["values"] = values
                self.add_folder_var.set(name)
            else:
                self.add_folder_var.set(ROOT_FOLDER_LABEL)

    def _browse_files(self):
        paths = filedialog.askopenfilenames(title="Seleziona una o più immagini")
        if paths:
            self._add_to_pending(list(paths))

    def _on_drop(self, event):
        paths = self.tk.splitlist(event.data)
        if paths:
            self._add_to_pending(list(paths))

    # ---- gestione della coda "in attesa di caricamento" ----
    def _add_to_pending(self, paths):
        added = 0
        for path in paths:
            if path not in self.pending_paths:
                self.pending_paths.append(path)
                self.pending_listbox.insert("end", os.path.basename(path))
                added += 1
        if added:
            self._update_upload_button_state()
            self.status_var.set(
                f"{len(self.pending_paths)} file in attesa di caricamento. "
                "Premi \"Carica\" per confermare."
            )

    def _remove_pending_selected(self):
        selection = self.pending_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        self.pending_listbox.delete(index)
        del self.pending_paths[index]
        self._update_upload_button_state()
        self.status_var.set(f"{len(self.pending_paths)} file in attesa di caricamento.")

    def _clear_pending(self):
        self._clear_pending_state()
        self.status_var.set("Pronto.")

    def _clear_pending_state(self):
        self.pending_listbox.delete(0, "end")
        self.pending_paths.clear()
        self._update_upload_button_state()

    def _update_upload_button_state(self):
        self.upload_button.config(state="normal" if self.pending_paths else "disabled")

    def _confirm_upload(self):
        if not self._repo_dir_valid():
            messagebox.showerror("Errore", "Configura prima la cartella della repo.")
            return
        if not self.pending_paths:
            return

        folder = self.add_folder_var.get()
        folder = "" if folder == ROOT_FOLDER_LABEL else folder

        repo_dir = self.config_data["repo_dir"]
        paths = list(self.pending_paths)  # istantanea: la coda potrebbe cambiare durante l'upload

        self.status_var.set("Caricamento in corso...")
        self.result_var.set("")
        self.upload_button.config(state="disabled")

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
        self.result_queue.put(("upload_done", urls))

    # ---- scheda "Copia link" ----
    def _build_link_tab(self, parent):
        pad = {"padx": 0, "pady": 6}

        folder_frame = ttk.Frame(parent)
        folder_frame.pack(fill="x", **pad)
        ttk.Label(folder_frame, text="Cartella:").pack(side="left")
        self.link_folder_var = tk.StringVar(value=ROOT_FOLDER_LABEL)
        self.link_folder_combo = ttk.Combobox(
            folder_frame, textvariable=self.link_folder_var, state="readonly", width=32
        )
        self.link_folder_combo.pack(side="left", padx=8)
        self.link_folder_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_file_list())

        ttk.Label(parent, text="Immagini in questa cartella:").pack(fill="x", pady=(6, 2))

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        self.file_listbox = tk.Listbox(
            list_frame, yscrollcommand=scrollbar.set, activestyle="dotbox"
        )
        scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.file_listbox.bind("<Double-Button-1>", lambda _e: self._get_link_for_selection())

        ttk.Button(
            parent, text="Ottieni link per l'immagine selezionata",
            command=self._get_link_for_selection,
        ).pack(pady=(6, 0))

    def _refresh_file_list(self):
        self.file_listbox.delete(0, "end")
        repo_dir = self.config_data.get("repo_dir")
        if not repo_dir:
            return
        folder = self.link_folder_var.get()
        folder = "" if folder == ROOT_FOLDER_LABEL else folder
        for name in list_image_files(repo_dir, folder):
            self.file_listbox.insert("end", name)

    def _get_link_for_selection(self):
        selection = self.file_listbox.curselection()
        if not selection:
            messagebox.showinfo("Nessuna selezione", "Seleziona prima un'immagine dall'elenco.")
            return
        filename = self.file_listbox.get(selection[0])
        folder = self.link_folder_var.get()
        folder = "" if folder == ROOT_FOLDER_LABEL else folder
        rel_path = f"{folder}/{filename}" if folder else filename
        repo_dir = self.config_data["repo_dir"]
        try:
            url = build_raw_url(repo_dir, rel_path)
        except GitError as exc:
            messagebox.showerror("Errore", str(exc))
            return
        self.result_var.set(url)
        self.clipboard_clear()
        self.clipboard_append(url)
        self.status_var.set("Link copiato negli appunti.")

    # ---- condiviso: elenco cartelle ----
    def _refresh_folder_lists(self):
        repo_dir = self.config_data.get("repo_dir")
        if not repo_dir:
            return
        folders = list_existing_folders(repo_dir)

        add_values = [ROOT_FOLDER_LABEL] + folders + [NEW_FOLDER_LABEL]
        self.add_folder_combo["values"] = add_values
        self.add_folder_var.set(ROOT_FOLDER_LABEL)

        link_values = [ROOT_FOLDER_LABEL] + folders
        self.link_folder_combo["values"] = link_values
        self.link_folder_var.set(ROOT_FOLDER_LABEL)
        self._refresh_file_list()

    # ---- coda di aggiornamento UI (worker thread -> main thread) ----
    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.result_queue.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind == "error":
                    self.status_var.set("Errore. I file restano in attesa: correggi e riprova.")
                    self._update_upload_button_state()
                    messagebox.showerror("Errore durante il caricamento", payload)
                elif kind == "upload_done":
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
                    self._clear_pending_state()
                    self._refresh_folder_lists()
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