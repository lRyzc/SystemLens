import argparse
import logging
import webbrowser

from .collector import Collector
from .server import create_server


def main():
    parser = argparse.ArgumentParser(description="SystemLens — monitor local de hardware e desempenho")
    parser.add_argument("--port", type=int, default=8765, help="porta local (padrão: 8765)")
    parser.add_argument("--no-browser", action="store_true", help="não abrir o navegador automaticamente")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("a porta deve estar entre 1 e 65535")
    logging.basicConfig(level=logging.WARNING)
    collector = Collector()
    try:
        server = create_server(collector, args.port)
    except OSError as exc:
        parser.exit(1, f"Não foi possível abrir a porta {args.port}. Use --port com outra porta.\n{exc}\n")
    collector.start()
    url = f"http://127.0.0.1:{args.port}"
    print(f"SystemLens  |  {url}\nCtrl+C para encerrar.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        collector.stop()


if __name__ == "__main__":
    main()
