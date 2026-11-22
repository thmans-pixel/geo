"""Petit client qui appelle l'application ASGI directement (pas besoin d'httpx)."""
import asyncio
import json


class Client:
    def __init__(self, app, entetes=None):
        self.app, self.cookies, self.entetes = app, {}, dict(entetes or {})

    async def _appel(self, methode, chemin, corps):
        donnees = json.dumps(corps).encode() if corps is not None else b""
        entetes = [(b"host", b"test"), (b"content-type", b"application/json")]
        entetes += [(k.lower().encode(), v.encode()) for k, v in self.entetes.items()]
        if self.cookies:
            entetes.append((b"cookie", "; ".join(f"{k}={v}" for k, v in self.cookies.items()).encode()))
        chemin_seul, _, requete = chemin.partition("?")
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": methode,
                 "path": chemin_seul, "raw_path": chemin_seul.encode(), "query_string": requete.encode(),
                 "headers": entetes, "scheme": "http", "server": ("test", 80), "client": ("127.0.0.1", 1)}
        envoye = False
        statut, sortie = 0, b""

        async def receive():
            nonlocal envoye
            if not envoye:
                envoye = True
                return {"type": "http.request", "body": donnees, "more_body": False}
            await asyncio.sleep(3600)

        async def send(m):
            nonlocal statut, sortie
            if m["type"] == "http.response.start":
                statut = m["status"]
                for k, v in m["headers"]:
                    if k == b"set-cookie":
                        nom, _, reste = v.decode().partition("=")
                        self.cookies[nom] = reste.split(";")[0]
            elif m["type"] == "http.response.body":
                sortie += m.get("body", b"")

        await self.app(scope, receive, send)
        return statut, sortie

    def appeler(self, methode, chemin, corps=None):
        statut, brut = asyncio.run(self._appel(methode, chemin, corps))
        try:
            return statut, json.loads(brut)
        except ValueError:
            return statut, brut

    def get(self, chemin):
        return self.appeler("GET", chemin)

    def post(self, chemin, corps=None):
        return self.appeler("POST", chemin, {} if corps is None else corps)

    def delete(self, chemin):
        return self.appeler("DELETE", chemin)
