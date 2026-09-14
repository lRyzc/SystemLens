"""Native Windows window around the local dashboard; no external browser needed."""

import ctypes
import logging
from pathlib import Path
import threading

from .collector import Collector
from .server import create_server


def run(webview):
    collector = Collector()
    server = create_server(collector, port=0)
    worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .2},
                              name='systemlens-http', daemon=True)
    try:
        collector.start()
        worker.start()
        webview.settings['ALLOW_DOWNLOADS'] = True
        webview.create_window(
            'SystemLens', f'http://127.0.0.1:{server.server_address[1]}',
            width=1360, height=900, min_size=(800, 600), background_color='#101110',
            text_select=True,
        )
        webview.start(gui='edgechromium', private_mode=True,
                      icon=str(Path(__file__).parent / 'static' / 'systemlens.ico'))
    finally:
        if worker.is_alive():
            server.shutdown()
            worker.join(timeout=3)
        server.server_close()
        collector.stop()


def main():
    logging.basicConfig(handlers=[logging.NullHandler()])
    try:
        import webview
        run(webview)
    except Exception:
        ctypes.windll.user32.MessageBoxW(
            None,
            'Não foi possível abrir o SystemLens.\n\n'
            'O aplicativo requer Windows 10/11 de 64 bits e Microsoft Edge WebView2 Runtime.\n'
            'Verifique se o WebView2 está instalado e tente novamente.\n\n'
            'Ajuda: github.com/lRyzc/SystemLens',
            'SystemLens — falha ao iniciar', 0x10,
        )
        raise SystemExit(1)


if __name__ == '__main__':
    main()
