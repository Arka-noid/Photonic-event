# Impostazioni Claude Code

`settings.json` è condiviso da tutto il team (viene versionato). Le preferenze
personali vanno invece in `.claude/settings.local.json`, che ha precedenza e non
va committato.

## Visibilità del ragionamento

| Chiave | Valore | Effetto |
| --- | --- | --- |
| `alwaysThinkingEnabled` | `true` | Il ragionamento esteso resta attivo di default sui modelli che lo supportano; se `false` viene disattivato. |
| `showThinkingSummaries` | `true` | Richiede i riassunti del ragionamento e li mostra in conversazione e nella vista transcript (`ctrl+o`). |
| `viewMode` | `"verbose"` | Vista transcript all'avvio: mostra i blocchi di ragionamento e le chiamate ai tool per esteso (alternative: `default`, `focus`). |
| `defaultView` | `"transcript"` | Apre la conversazione sul transcript completo invece che sulla sola chat. |
| `verbose` | `true` | Output dei tool completo invece dei riassunti troncati. |
| `showTurnDuration` | `true` | Mostra quanto è durato ogni turno, ragionamento incluso. |

## Note

- Il budget di token per il ragionamento non è una impostazione di visibilità e
  qui non viene fissato: se serve, si imposta per sessione con la variabile
  d'ambiente `MAX_THINKING_TOKENS`, oppure con `effortLevel`
  (`low` | `medium` | `high` | `xhigh`) in `settings.local.json`.
- Per disattivare il ragionamento visibile solo per sé, basta sovrascrivere le
  chiavi in `.claude/settings.local.json`, per esempio:

  ```json
  { "showThinkingSummaries": false, "viewMode": "default" }
  ```
