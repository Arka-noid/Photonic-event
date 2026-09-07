# CLAUDE.md

Le istruzioni di progetto per gli agenti stanno in **[AGENTS.md](AGENTS.md)**:
comandi, regole sui dati, struttura e stile valgono anche qui e non vengono
ripetuti. Leggi prima quello, poi torna qui per la parte specifica di Claude Code.

## Specifico di Claude Code

- **Impostazioni condivise**: [`.claude/settings.json`](.claude/settings.json),
  versionato e valido per tutto il team; il ragionamento è visibile per
  impostazione predefinita. Le chiavi sono spiegate una per una in
  [`.claude/README.md`](.claude/README.md).
- **Preferenze personali**: `.claude/settings.local.json`, che ha precedenza sul
  file condiviso ed è ignorato da git. È lì che vanno le tue sovrascritture, per
  esempio per spegnere i riassunti del ragionamento.
- **Verifica prima di rispondere**: i due comandi offline di
  [AGENTS.md](AGENTS.md) girano senza rete e senza secrets, quindi non c'è
  motivo di dichiarare una modifica funzionante senza averli eseguiti.
- **Niente rete verso le fonti** durante lo sviluppo: si usano le fixture in
  `tests/fixtures/`. Il traffico verso i siti delle conferenze parte solo dai
  workflow.
- **Telegram e `ANTHROPIC_API_KEY`**: mai in chiaro, mai in un commit. In locale
  si lavora con `--dry-run`, che stampa il messaggio invece di inviarlo.

## Dove guardare per prima cosa

| Domanda | File |
| --- | --- |
| Cosa fa il progetto | [README.md](README.md) |
| Come lavorarci | [AGENTS.md](AGENTS.md) |
| Come sono configurate le sessioni | [.claude/README.md](.claude/README.md) |
| Quali fonti esistono | [collector/registry.yaml](collector/registry.yaml) |
| Quali eventi sono curati a mano | [data/watchlist.yaml](data/watchlist.yaml) |
