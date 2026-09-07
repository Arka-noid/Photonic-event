#!/usr/bin/env python3
"""Anteprima locale del sito.

Il sito legge `./data/events.json` come farebbe su GitHub Pages, dove i dati
vengono affiancati alla pagina. In locale li copiamo dentro site/data/ (che è
gitignorata) e serviamo la cartella, così l'anteprima è identica alla produzione.
"""

import http.server
import shutil
import socketserver
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8000


def main() -> None:
    target = ROOT / "site" / "data"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("events.json", "health.json", "schedule.json"):
        source = ROOT / "data" / name
        if source.exists():
            shutil.copy2(source, target / name)
            print(f"copiato {name}")
        else:
            print(f"manca data/{name}: lancia prima `python -m collector.run collect --offline --dry-run`")

    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(ROOT / "site"), **kw)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        print(f"\nAnteprima su http://localhost:{PORT}  (ctrl+c per uscire)")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
