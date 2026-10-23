#!/usr/bin/env python3
"""Локальный прод-подобный стенд ekotov-wiki: один origin, цепочка как у nginx.

/static/*  -> http.server (docroot frontend/static, префикс /static срезается)
остальное  -> uvicorn (APP_PORT) с пробросом Cookie/Set-Cookie/Location

Зачем: web-сьют проекта сам эмулирует веб-сервер, поэтому расхождения
«стенд ≠ прод» (кеш, заголовки, порядок загрузки модулей) ловятся только
такой ручной репликой. Запуск: uvicorn на APP_PORT отдельно, затем этот файл.
"""
import http.server, urllib.request, socketserver, threading

STATIC_PORT = 8898   # внутренний, статика
APP_PORT = 8899      # внутренний, uvicorn
PROXY_PORT = 8900    # внешний, сюда ходит браузер
FRONTEND_STATIC = "/home/openclaw/ekotov-wiki/frontend/static"

class StaticHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=FRONTEND_STATIC, **kw)
    def parse_request(self):
        ok = super().parse_request()
        if self.path.startswith("/static/"):
            self.path = self.path[len("/static"):]
        return ok
    def log_message(self, *a):
        pass

class Proxy(http.server.BaseHTTPRequestHandler):
    def _pipe(self, method):
        body = b""
        if method == "POST":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b""
        if self.path.startswith("/static/"):
            req = urllib.request.Request(f"http://127.0.0.1:{STATIC_PORT}{self.path}", method="GET")
        else:
            req = urllib.request.Request(f"http://127.0.0.1:{APP_PORT}{self.path}", data=body or None, method=method)
            req.add_header("Cookie", self.headers.get("Cookie", ""))
            if body:
                req.add_header("Content-Type", self.headers.get("Content-Type", "application/json"))
        try:
            with urllib.request.urlopen(req) as r:
                resp = r.read()
                self.send_response(r.status)
                for h, v in r.headers.items():
                    if h.lower() in ("set-cookie", "location", "content-type"):
                        self.send_header(h, v)
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
        except urllib.error.HTTPError as e:
            resp = e.read()
            self.send_response(e.code)
            for h, v in e.headers.items():
                if h.lower() in ("set-cookie", "location", "content-type"):
                    self.send_header(h, v)
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

    def do_GET(self):
        self._pipe("GET")

    def do_POST(self):
        self._pipe("POST")

socketserver.TCPServer.allow_reuse_address = True
socketserver.ThreadingTCPServer.allow_reuse_address = True
threading.Thread(target=lambda: socketserver.TCPServer(("127.0.0.1", STATIC_PORT), StaticHandler).serve_forever(), daemon=True).start()
socketserver.ThreadingTCPServer(("127.0.0.1", PROXY_PORT), Proxy).serve_forever()
