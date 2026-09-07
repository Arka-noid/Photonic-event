# AGENTS.md

Istruzioni per gli agenti di codice che lavorano su **Photonic-event**. È il
documento di riferimento: [`CLAUDE.md`](CLAUDE.md) rimanda qui e aggiunge solo
quello che è specifico di Claude Code.

## Il progetto in due righe

Raccoglie conferenze, summer school e workshop fra fotonica e reti neurali, ne
segue le scadenze e manda un digest su Telegram; i dati finiscono in
`data/events.json` e sono pubblicati come sito statico su GitHub Pages.
Il contesto completo è nel [README](README.md).

## Ambiente e comandi

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

| Comando | Quando |
| --- | --- |
| `.venv/bin/pytest -q` | Sempre, prima di ogni commit |
| `.venv/bin/python -m collector.run collect --offline --dry-run` | Sempre: pipeline completa sulle fixture |
| `.venv/bin/python -m collector.run remind --dry-run --today AAAA-MM-GG` | Toccando scadenze o promemoria |
| `.venv/bin/python scripts/preview.py` | Toccando `site/` (serve su :8000) |

Sono gli stessi due comandi che gira la CI in
[`.github/workflows/tests.yml`](.github/workflows/tests.yml): se passano in
locale, passa anche lì.

## Regole del progetto

- **I test non toccano la rete.** Ogni fonte nuova va coperta da una fixture in
  `tests/fixtures/`, non da una chiamata HTTP. `--offline` deve restare capace
  di far girare l'intera pipeline.
- **Una fonte che fallisce non fa fallire la raccolta.** Le fonti girano isolate:
  timeout, 403 e selettori sbagliati finiscono in `data/health.json` e vengono
  mostrati; non vanno mai fatti passare in silenzio né convertiti in un'eccezione
  che interrompe il run.
- **Onestà dei dati prima della completezza.** `confidence: unconfirmed` per le
  edizioni attese ma non confermate, `date_precision: month` quando si conosce
  solo il mese. Le scadenze si accettano solo se etichettate nel testo
  (`abstract deadline: …`), mai dedotte; le date ambigue (`10/05/2026`) si
  rifiutano. Meglio nessuna data che una sbagliata.
- **Le fonti si dichiarano, non si programmano.** Una fonte nuova è una voce in
  [`collector/registry.yaml`](collector/registry.yaml); il codice in
  `collector/sources/` si tocca solo per un tipo di fonte davvero nuovo. Una
  fonte con selettori non verificati sul sito reale resta `verified: false`.
- **Rispetto delle fonti.** Una sola richiesta per fonte per run, timeout brevi,
  `User-Agent` identificativo, nessun crawling ricorsivo.
- **Niente segreti nel repo.** Token Telegram e `ANTHROPIC_API_KEY` vivono nei
  secrets di GitHub Actions e si leggono solo da variabili d'ambiente.
- **`data/events.json` e `data/health.json` li scrivono i workflow.** Vanno
  modificati a mano solo per correggere un dato sbagliato, mai per aggiungere
  eventi: quelli si aggiungono a [`data/watchlist.yaml`](data/watchlist.yaml).

## Struttura

```
collector/          pipeline: modelli, pertinenza, date, store, fonti, notifiche
  registry.yaml     elenco dichiarativo delle fonti
data/               events.json, health.json (dai workflow), watchlist.yaml (a mano)
site/               sito statico, nessun build step
tests/              pytest offline su fixture salvate
.github/workflows/  raccolta (giornaliera), promemoria, pubblicazione, test
```

## Stile

- Italiano in commit, commenti, documentazione e interfaccia del sito.
- Messaggi di commit con prefisso dell'area toccata, minuscolo:
  `collect:`, `dati:`, `pages:`, `claude:`.
- Commenti che spiegano *perché*, non *cosa*: quelli esistenti nei workflow sono
  il riferimento.
- Nessuna dipendenza nuova senza motivo: `requirements.txt` è volutamente corto.

## Prima di consegnare

1. `pytest -q` verde.
2. `collect --offline --dry-run` completa senza errori.
3. Se hai toccato il registry, `data/health.json` non deve peggiorare.
4. Il README resta vero: se cambi frequenze, comandi o campi, aggiornalo.
