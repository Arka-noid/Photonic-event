"""Interfaccia a riga di comando.

    python -m collector.run collect          raccolta + digest Telegram
    python -m collector.run collect --offline --dry-run
    python -m collector.run remind           promemoria scadenze
    python -m collector.run probe            diagnostica di tutte le fonti
    python -m collector.run test-telegram    verifica la configurazione del bot
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from .deadlines import due_reminders, mark_sent
from .digest import build_digest, build_reminders
from .notify.telegram import Telegram
from .pipeline import collect as run_collect, load_registry, run_all
from .store import Store, write_health
from .sources.base import Fetcher

ROOT = Path(__file__).resolve().parent.parent


def _telegram(args) -> Telegram:
    return Telegram(
        os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        os.environ.get("TELEGRAM_CHAT_ID", ""),
        dry_run=args.dry_run,
    )


def _today(args) -> date:
    return date.fromisoformat(args.today) if args.today else date.today()


def _paths(args) -> tuple[Path, Path, Path]:
    root = Path(args.root)
    return root / args.registry, root / args.data_dir / "events.json", root / args.data_dir / "health.json"


def cmd_collect(args) -> int:
    registry_path, events_path, health_path = _paths(args)
    today = _today(args)
    store = Store(events_path).load()
    before = len(store.events)

    fetcher = Fetcher(offline=args.offline, base_dir=args.root)
    diff, results, (links_ok, links_tried) = run_collect(registry_path, store, fetcher, today)

    pruned = store.prune_past(today)
    store.save(today)
    write_health(health_path, [r.to_health(today) for r in results], today)

    print(f"eventi: {before} → {len(store.events)} (nuovi {len(diff.new)}, "
          f"aggiornati {len(diff.updated)}, rimossi {pruned})")
    if links_tried:
        print(f"link ufficiali risolti: {links_ok} su {links_tried} schede aperte")
    for result in results:
        state = "OK " if result.ok else "ERR"
        note = result.skipped or result.warning or result.error
        print(f"  [{state}] {result.id:<20} {result.n_events:>4} eventi  {note}")

    message = build_digest(diff, results, today)
    if not message:
        print("nessuna novità: nessun messaggio inviato")
        return 0

    telegram = _telegram(args)
    if not telegram.configured and not args.dry_run:
        print("ATTENZIONE: Telegram non configurato, digest non inviato", file=sys.stderr)
        return 0
    return 0 if telegram.send(message) else 1


def cmd_remind(args) -> int:
    _, events_path, _ = _paths(args)
    today = _today(args)
    store = Store(events_path).load()

    reminders = due_reminders(store.upcoming(today), today)
    if not reminders:
        print("nessuna scadenza in soglia oggi")
        return 0
    print(f"{len(reminders)} promemoria da inviare")

    telegram = _telegram(args)
    if not telegram.configured and not args.dry_run:
        print("ATTENZIONE: Telegram non configurato, promemoria non inviati", file=sys.stderr)
        return 1

    if not telegram.send(build_reminders(reminders, today)):
        return 1
    # Si segna solo dopo un invio riuscito: un fallimento deve poter riprovare domani.
    if not args.dry_run:
        mark_sent(reminders)
        store.save(today)
    return 0


def cmd_probe(args) -> int:
    """Diagnostica: interroga ogni fonte e salva le risposte grezze.

    È il modo previsto per tarare i selettori CSS, che non è stato possibile
    verificare in fase di sviluppo (la rete non raggiungeva i siti delle società
    scientifiche). Va lanciato da GitHub Actions, che ha rete aperta.
    """
    registry_path, _, health_path = _paths(args)
    today = _today(args)
    out_dir = Path(args.root) / "probe-output"
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = load_registry(registry_path)
    results = run_all(entries, Fetcher(offline=args.offline, base_dir=args.root))

    print(f"{'fonte':<22}{'http':>6}{'bytes':>10}{'eventi':>8}  note")
    print("-" * 78)
    for result in results:
        if result.raw:
            (out_dir / f"{result.id}.raw").write_bytes(result.raw)
        note = result.skipped or result.warning or result.error
        print(f"{result.id:<22}{str(result.http_status or '-'):>6}{len(result.raw):>10}"
              f"{result.n_events:>8}  {note[:40]}")
        if result.events:
            print(f"{'':>46}  es.: {result.events[0].title[:60]}")

    write_health(health_path, [r.to_health(today) for r in results], today)
    print(f"\nrisposte grezze salvate in {out_dir}")
    broken = [r.id for r in results if not r.ok]
    if broken:
        print(f"fonti da sistemare: {', '.join(broken)}")
    return 0


def cmd_test_telegram(args) -> int:
    telegram = _telegram(args)
    if not telegram.configured and not args.dry_run:
        print("TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID non impostati", file=sys.stderr)
        return 1
    ok = telegram.send(
        "<b>✅ Photonic-event</b>\nIl bot è configurato correttamente: "
        "riceverai qui le novità e i promemoria delle scadenze."
    )
    return 0 if ok else 1


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=str(ROOT), help="radice del progetto")
    parser.add_argument("--registry", default="collector/registry.yaml")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--today", default=None, help="finge una data (AAAA-MM-GG), per i test")
    parser.add_argument("--dry-run", action="store_true", help="stampa i messaggi invece di inviarli")
    parser.add_argument("--offline", action="store_true", help="usa le fixture, nessuna richiesta di rete")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="collector.run", description=__doc__)
    _add_common(parser)

    # Le stesse opzioni sono accettate anche dopo il sottocomando: scrivere
    # `collect --offline` è la forma naturale, e argparse da solo la rifiuterebbe.
    sub = parser.add_subparsers(dest="command", required=True)
    for name, function in (
        ("collect", cmd_collect),
        ("remind", cmd_remind),
        ("probe", cmd_probe),
        ("test-telegram", cmd_test_telegram),
    ):
        child = sub.add_parser(name)
        _add_common(child)
        child.set_defaults(func=function)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
