# Photonic-event

Raccoglie conferenze, summer school e workshop all'incrocio fra **fotonica** e **reti
neurali** (photonic computing, neuromorphic photonics, optical AI), tiene d'occhio le
**scadenze** e avvisa su **Telegram**. I risultati sono consultabili come sito
installabile sul telefono.

- 🌐 Sito: <https://arka-noid.github.io/Photonic-event/>
- 🤖 Raccolta **ogni giorno** alle 06:15 UTC; promemoria scadenze alle 07:00 UTC
- ⟳ Il pulsante in cima al sito lancia una raccolta subito, senza aspettare il turno
- 💬 Notifiche: Telegram

---

## Come funziona

```
fonti  ──▶  pertinenza  ──▶  data/events.json  ──┬──▶  digest Telegram (novità)
(registry)   e regione        (merge + storico)  ├──▶  promemoria scadenze
                                                 └──▶  sito su GitHub Pages
```

Ogni fonte è dichiarata in [`collector/registry.yaml`](collector/registry.yaml) e gira
**isolata**: un timeout, un 403 o un selettore CSS sbagliato non fanno fallire la
raccolta, finiscono in `data/health.json` e vengono mostrati in fondo al sito e in coda
al digest. Se una fonte smette di funzionare, il sistema lo dice invece di tacere.

### Onestà dei dati

Due campi esistono apposta per non far sembrare certo ciò che non lo è:

| Campo | Significato |
|---|---|
| `confidence: unconfirmed` | Edizione *attesa*, non ancora confermata dalla pagina ufficiale → sul sito appare come **date da confermare** |
| `date_precision: month` | Della data si conosce solo il mese → viene scritto "ottobre 2026", mai "1 ott 2026" |

Un'edizione della watchlist diventa `confirmed` solo se la pagina ufficiale contiene un
intervallo di date dell'anno atteso; le scadenze si accettano solo quando sono
**etichettate** nel testo (`abstract deadline: …`), mai dedotte da una data qualsiasi.
Le date in formato numerico ambiguo (`10/05/2026`) vengono **rifiutate**: meglio nessuna
data che un promemoria per il giorno sbagliato.

---

## Configurazione

### 1. Bot Telegram

1. Su Telegram apri una chat con [@BotFather](https://t.me/BotFather), manda `/newbot` e
   segui le istruzioni. Alla fine ricevi un token tipo `123456:ABC-DEF…`.
2. **Manda un messaggio qualsiasi al tuo nuovo bot** (serve a creare la conversazione).
3. Recupera il tuo chat id aprendo nel browser:
   `https://api.telegram.org/bot<IL_TUO_TOKEN>/getUpdates` e cercando
   `"chat":{"id":123456789`.

### 2. Secrets del repository

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`:

| Secret | Obbligatorio | A cosa serve |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | sì | Token di @BotFather |
| `TELEGRAM_CHAT_ID` | sì | La tua chat id |
| `ANTHROPIC_API_KEY` | no | Attiva la fonte di ricerca web con Claude (vedi sotto) |

Verifica con: `Actions` → **Raccolta eventi** → `Run workflow` → `mode: collect`,
`dry_run: false`. Dovresti ricevere il digest su Telegram.

### 3. GitHub Pages

`Settings` → `Pages` → **Source: GitHub Actions**. Il workflow *Pubblica il sito* fa il
resto a ogni aggiornamento dei dati.

### 4. Il pulsante ⟳ del sito (facoltativo)

Il pulsante in alto a destra avvia la raccolta senza passare da GitHub: mostra
l'avanzamento e ricarica i dati appena il sito è ripubblicato, in tutto un paio di minuti.

Il sito è statico, quindi l'unico modo di far partire un workflow da lì è chiamare l'API
di GitHub, che vuole un token. In una pagina pubblica non esiste un posto sicuro dove
metterlo, perciò lo si chiede al proprietario alla prima pressione e resta **solo nel
browser di quel dispositivo** (`localStorage`). Da usare un token
[fine-grained](https://github.com/settings/personal-access-tokens/new) ristretto:

- *Repository access* → **Only select repositories** → `Photonic-event`
- *Repository permissions* → **Actions: Read and write**, nient'altro
- scadenza breve: quando scade, il pulsante lo richiede

Due avvertenze. Il token vale per l'intera origine `arka-noid.github.io`, condivisa da
tutte le GitHub Pages dello stesso account: tienilo ristretto come sopra e usa
*Dimentica il token* (in fondo alla pagina) su un dispositivo che non controlli più.
E chi non vuole token non perde nulla: il pulsante offre *Apri su GitHub*, dove
`Run workflow` fa esattamente la stessa cosa.

Una raccolta lanciata due volte nello stesso giorno di solito riporta "nessun evento
nuovo": è l'esito giusto, non un errore.

---

## Tarare le fonti (da fare una volta)

I selettori CSS di SPIE, Optica, IEEE Photonics ed EOS **non sono stati verificati**
contro i siti veri: l'ambiente in cui è stato scritto il progetto non li raggiungeva.
Sono marcati `verified: false` nel registry. Per sistemarli:

1. `Actions` → **Raccolta eventi** → `Run workflow` con `mode: probe`.
2. Scarica l'artifact `probe-output`: contiene la risposta grezza di ogni fonte.
3. Correggi i `selectors` in `collector/registry.yaml` guardando l'HTML reale, e
   promuovi una risposta a fixture in `tests/fixtures/` aggiungendo un test.
4. Ripeti finché ogni fonte riporta `ok` in `data/health.json` — oppure mettila
   `enabled: false` se il sito non è raccoglibile.

Nel frattempo la raccolta funziona comunque: la **watchlist curata**
([`data/watchlist.yaml`](data/watchlist.yaml)) garantisce che le grandi conferenze
ricorrenti siano sempre presenti, con il link ufficiale.

---

## Aggiungere un evento o una fonte

**Un evento ricorrente** → aggiungi una voce a `data/watchlist.yaml`:

```yaml
- name: Nome della conferenza
  url: https://sito-ufficiale.example/
  typical_month: 6        # mese in cui si tiene di solito (1-12)
  kind: conference        # conference | school | workshop | special-session
  topics: [photonics, ml]
  region: europe
  note: "Una riga di contesto."
```

**Una fonte nuova** → aggiungi una voce a `collector/registry.yaml`. I tipi disponibili
sono `ics`, `rss`, `html`, `aideadlines`, `watchlist`, `llm`. Per l'HTML servono i
selettori:

```yaml
- id: nuova-fonte
  name: Nome leggibile
  type: html
  url: https://example.org/events
  topics_default: [photonics]
  enabled: true
  selectors:
    item: ".event-card"       # il contenitore di un singolo evento
    title: "h3"
    link: "a@href"            # '@attributo' legge un attributo invece del testo
    date: ".dates"
    location: ".venue"
```

---

## Ricerca web con Claude (opzionale)

La fonte `llm-search` è già scritta ma **inerte finché manca `ANTHROPIC_API_KEY`**: si
auto-disattiva e `health.json` lo riporta come `skipped`. Aggiungendo il secret si
accende da sola, senza modifiche al codice. Usa `claude-opus-5` con il server tool di
ricerca web e restituisce JSON vincolato a schema; le voci che produce nascono
`unconfirmed`, perché un modello può sbagliare una data anche citando la fonte giusta.

Il numero di query per run è limitato da `max_queries` nel registry: è la voce di costo
principale, quindi conviene alzarlo con prudenza.

---

## Sviluppo in locale

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

.venv/bin/pytest -q                                        # test, nessuna rete
.venv/bin/python -m collector.run collect --offline --dry-run   # pipeline sulle fixture
.venv/bin/python -m collector.run remind --dry-run              # promemoria di oggi
.venv/bin/python scripts/preview.py                             # sito su :8000
```

Comandi disponibili:

| Comando | Cosa fa |
|---|---|
| `collect` | Raccoglie, aggiorna `data/events.json`, manda il digest |
| `remind` | Manda i promemoria delle scadenze in soglia oggi |
| `probe` | Interroga ogni fonte e salva le risposte grezze in `probe-output/` |
| `test-telegram` | Manda un messaggio di prova per verificare i secrets |

Opzioni utili su tutti: `--dry-run` (stampa invece di inviare), `--offline` (usa le
fixture, nessuna rete), `--today AAAA-MM-GG` (finge una data, per i test).

---

## Struttura

```
collector/          pipeline: modello dati, pertinenza, date, store, fonti, notifiche
  registry.yaml     elenco dichiarativo delle fonti
data/
  events.json       stato persistente (committato dai workflow)
  health.json       esito dell'ultima raccolta, fonte per fonte
  watchlist.yaml    eventi ricorrenti curati a mano
site/               sito statico, nessun build step
tests/              pytest offline su fixture salvate
```

## Note sul rispetto delle fonti

`User-Agent` identificativo con link al repository, una sola richiesta per fonte per
run, timeout brevi, nessun crawling ricorsivo. La raccolta gira due volte a settimana:
gli eventi accademici non cambiano più spesso di così.
