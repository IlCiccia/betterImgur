# imgpusher

GUI per caricare immagini sulla tua repo GitHub personale e ottenere subito il
link "raw" diretto, con drag & drop, scelta della cartella di destinazione
(esistente o nuova) e copia automatica del link negli appunti.

## Requisiti

- macOS (funziona anche su Linux/Windows, ma le istruzioni qui sotto sono
  pensate per macOS)
- Python 3.8 o superiore
- `git` installato e nel PATH
- Una repository locale già clonata e con un remote GitHub funzionante
  (via HTTPS o SSH, anche con alias host tipo `github.com-ilciccia`)

## Installazione

### 1. Posizionati nella cartella del progetto

```bash
cd /percorso/dove/hai/salvato/imgpusher_gui.py
```

### 2. Crea un ambiente virtuale (venv)

Un venv tiene le dipendenze di questo script isolate dal resto del sistema,
senza toccare l'installazione globale di Python.

```bash
python3 -m venv venv
```

Questo crea una cartella `venv/` nella directory corrente. Non va mai
condivisa né versionata (se questa cartella finisse dentro una repo git,
aggiungila a `.gitignore`).

### 3. Attiva il venv

```bash
source venv/bin/activate
```

Il prompt del terminale mostrerà `(venv)` davanti al percorso, a conferma che
è attivo. Da questo momento, `python3` e `pip` puntano automaticamente alle
versioni dentro il venv.

### 4. Installa le dipendenze

```bash
pip install -r requirements.txt
```

Questo installa `tkinterdnd2`, la libreria che abilita il drag & drop vero e
proprio. **Non è strettamente obbligatoria**: senza di essa lo script parte
comunque, ma la finestra offrirà solo il pulsante "Sfoglia file..." al posto
del trascinamento diretto.

> **Nota su tkinter (macOS con Homebrew):** `tkinter` fa parte della libreria
> standard di Python, quindi di norma non richiede installazione separata. Se
> però usi una versione di Python installata via Homebrew e all'avvio ottieni
> `ModuleNotFoundError: No module named 'tkinter'`, installalo con:
> ```bash
> brew install python-tk
> ```
> (Con Python installato dal sito ufficiale python.org, tkinter è già incluso
> e questo passaggio non serve.)

## Avvio

Con il venv attivo (vedi passo 3):

```bash
python3 imgpusher_gui.py
```

Alla primissima esecuzione, il programma chiede di selezionare la cartella
locale della repo (quella contenente la sottocartella `.git`). La scelta
viene salvata in `~/.imgpusher_config.json` e non va ripetuta nelle
esecuzioni successive, a meno di usare il pulsante "Cambia repo..." nella
finestra.

## Uso quotidiano

Le volte successive, per avviare l'app basta:

```bash
cd /percorso/dove/hai/salvato/imgpusher_gui.py
source venv/bin/activate
python3 imgpusher_gui.py
```

Per uscire dal venv al termine (facoltativo, si disattiva comunque chiudendo
il terminale):

```bash
deactivate
```

### Suggerimento

Se vuoi evitare di attivare il venv manualmente ogni volta, puoi lanciare lo
script chiamando direttamente l'interprete dentro `venv/` senza attivarlo:

```bash
venv/bin/python3 imgpusher_gui.py
```

Utile anche per creare un alias nella shell (`~/.zshrc`):

```bash
alias imgpusher="cd /percorso/dove/hai/salvato/imgpusher_gui.py && venv/bin/python3 imgpusher_gui.py"
```

Dopo aver aggiunto l'alias e ricaricato la shell (`source ~/.zshrc`), basterà
digitare `imgpusher` da qualsiasi cartella.

## Come funziona (in breve)

1. Trascini uno o più file immagine nella finestra (o li selezioni con
   "Sfoglia file...").
2. Ogni file viene copiato nella repo locale, rinominato con un prefisso
   data/ora (per evitare collisioni di nome e problemi di cache).
3. Lo script esegue `git add`, `git commit` e `git push` automaticamente.
4. Costruisce il link `raw.githubusercontent.com` corrispondente e lo copia
   negli appunti.

## Risoluzione problemi

**`SyntaxError: unexpected character after line continuation character`,
con `{\rtf1\ansi...}` in cima al file**
Il file `.py` è stato salvato in formato RTF invece che testo semplice
(succede aprendolo con TextEdit su macOS). Riscarica il file originale, oppure
in TextEdit vai su **Format → Make Plain Text** prima di salvare. Per
modificare lo script in futuro, usa `nano`, o un editor di codice (VS Code,
Sublime Text, ecc.) invece di TextEdit.

**`ModuleNotFoundError: No module named 'tkinter'`**
Vedi la nota sopra su Homebrew (`brew install python-tk`).

**Il drag & drop non compare, solo il pulsante "Sfoglia file..."**
`tkinterdnd2` non è installato (o non è installato *dentro* il venv attivo).
Controlla di aver attivato il venv prima di installare/lanciare
(`source venv/bin/activate`), poi `pip install -r requirements.txt`.

**Errore durante `git push` all'interno dell'app**
La causa più comune è che il remote della repo non sia raggiungibile con le
credenziali attualmente configurate (vedi la configurazione SSH per account
multipli, se applicabile). Prova a lanciare `git push` a mano dal terminale,
nella stessa cartella della repo, per vedere il messaggio di errore completo.

## Struttura dei file

```
imgpusher_gui.py        script principale (unico file necessario)
requirements.txt        dipendenze opzionali (drag & drop)
venv/                   ambiente virtuale locale (non versionare)
~/.imgpusher_config.json   configurazione salvata (percorso della repo)
```