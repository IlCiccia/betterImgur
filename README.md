# imgpusher

A GUI to upload images to your personal GitHub repo and instantly get the
direct "raw" link, with drag & drop, a choice of destination folder
(existing or new), and automatic clipboard copy of the link.

## Requirements

- macOS (also works on Linux/Windows, but the instructions below are
  written for macOS)
- Python 3.8 or higher
- `git` installed and available in your PATH
- A local repository already cloned, with a working GitHub remote
  (via HTTPS or SSH, including host aliases such as `github.com-ilciccia`)

## Installation

### 1. Move into the project folder

```bash
cd /path/where/you/saved/imgpusher_gui.py
```

### 2. Create a virtual environment (venv)

A venv keeps this script's dependencies isolated from the rest of your
system, without touching your global Python installation.

```bash
python3 -m venv venv
```

This creates a `venv/` folder in the current directory. Never share or
version-control this folder (if it ends up inside a git repo, add it to
`.gitignore`).

### 3. Activate the venv

```bash
source venv/bin/activate
```

Your terminal prompt will show `(venv)` before the path, confirming it's
active. From this point on, `python3` and `pip` automatically point to the
versions inside the venv.

### 4. Install the dependencies

```bash
pip install -r requirements.txt
```

This installs `tkinterdnd2`, the library that enables true drag & drop.
**It's not strictly required**: the script still runs without it, but the
window will only offer the "Browse files..." button instead of direct
dragging.

> **Note on tkinter (macOS with Homebrew):** `tkinter` is part of Python's
> standard library, so it normally doesn't need separate installation. If
> you're using a Python version installed via Homebrew and you get
> `ModuleNotFoundError: No module named 'tkinter'` at startup, install it
> with:
> ```bash
> brew install python-tk
> ```
> (With Python installed from the official python.org site, tkinter is
> already included and this step isn't needed.)

## Starting the app

With the venv active (see step 3):

```bash
python3 imgpusher_gui.py
```

On first launch, the program asks you to select the local repo folder (the
one containing the `.git` subfolder). This choice is saved to
`~/.imgpusher_config.json` and won't need to be repeated on later runs,
unless you use the "Change repo..." button in the window.

## Everyday use

On subsequent runs, starting the app just takes:

```bash
cd /path/where/you/saved/imgpusher_gui.py
source venv/bin/activate
python3 imgpusher_gui.py
```

To leave the venv when you're done (optional — it also deactivates
automatically when you close the terminal):

```bash
deactivate
```

### Tip

If you'd rather skip activating the venv manually every time, you can call
the interpreter inside `venv/` directly, without activating it:

```bash
venv/bin/python3 imgpusher_gui.py
```

This is also handy for creating a shell alias (`~/.zshrc`):

```bash
alias imgpusher="cd /path/where/you/saved/imgpusher_gui.py && venv/bin/python3 imgpusher_gui.py"
```

After adding the alias and reloading your shell (`source ~/.zshrc`), just
type `imgpusher` from anywhere.

## How it works (in short)

1. You drag one or more image files into the window (or pick them with
   "Browse files...").
2. Each file is copied into the local repo, renamed with a date/time
   prefix (to avoid name collisions and caching issues).
3. The script runs `git add`, `git commit`, and `git push` automatically.
4. It builds the corresponding `raw.githubusercontent.com` link and copies
   it to the clipboard.

## Troubleshooting

**`SyntaxError: unexpected character after line continuation character`,
with `{\rtf1\ansi...}` at the top of the file**
The `.py` file was saved in RTF format instead of plain text (happens when
opening it with TextEdit on macOS). Re-download the original file, or in
TextEdit go to **Format → Make Plain Text** before saving. To edit the
script in the future, use `nano`, or a proper code editor (VS Code, Sublime
Text, etc.) instead of TextEdit.

**`ModuleNotFoundError: No module named 'tkinter'`**
See the Homebrew note above (`brew install python-tk`).

**Drag & drop doesn't show up, only the "Browse files..." button**
`tkinterdnd2` isn't installed (or isn't installed *inside* the active
venv). Make sure the venv is activated before installing/launching
(`source venv/bin/activate`), then `pip install -r requirements.txt`.

**Error during `git push` inside the app**
The most common cause is that the repo's remote isn't reachable with the
credentials currently configured (see the multi-account SSH setup, if
applicable). Try running `git push` manually from the terminal, in the same
repo folder, to see the full error message.

## File structure

```
imgpusher_gui.py        main script (the only file you actually need)
requirements.txt        optional dependency (drag & drop)
venv/                    local virtual environment (don't version-control)
~/.imgpusher_config.json  saved configuration (repo path)
```