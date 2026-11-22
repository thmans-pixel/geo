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


class ClientWS:
    """Ouvre un WebSocket sur l'application ASGI, dans la boucle d'événements courante."""

    def __init__(self, app, chemin, entetes=None, cookies=None):
        chemin_seul, _, requete = chemin.partition("?")
        h = [(b"host", b"test")] + [(k.lower().encode(), v.encode()) for k, v in (entetes or {}).items()]
        if cookies:
            h.append((b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode()))
        self.scope = {"type": "websocket", "asgi": {"version": "3.0"}, "scheme": "ws", "path": chemin_seul,
                      "raw_path": chemin_seul.encode(), "query_string": requete.encode(), "headers": h,
                      "server": ("test", 80), "client": ("127.0.0.1", 1), "subprotocols": []}
        self.app, self.entrant, self.sortant = app, None, None
        self.accepte, self.code_fermeture, self.tache = False, None, None

    async def __aenter__(self):
        import asyncio
        self.entrant, self.sortant = asyncio.Queue(), asyncio.Queue()
        await self.entrant.put({"type": "websocket.connect"})

        async def send(m):
            await self.sortant.put(m)
        self.tache = asyncio.ensure_future(self.app(self.scope, self.entrant.get, send))
        if getattr(self, "entree", None):
            await self.envoyer(self.entree)
        return self

    async def __aexit__(self, *a):
        import asyncio
        await self.entrant.put({"type": "websocket.disconnect", "code": 1000})
        try:
            await asyncio.wait_for(self.tache, 2)
        except Exception:
            self.tache.cancel()

    async def recevoir(self, delai=2):
        """Prochain message JSON du serveur, ou None si le serveur a fermé."""
        import asyncio
        while True:
            m = await asyncio.wait_for(self.sortant.get(), delai)
            if m["type"] == "websocket.accept":
                self.accepte = True
            elif m["type"] == "websocket.close":
                self.code_fermeture = m.get("code", 1000)
                return None
            elif m["type"] == "websocket.send":
                return json.loads(m["text"]) if m.get("text") else m.get("bytes")

    async def envoyer(self, message):
        await self.entrant.put({"type": "websocket.receive", "text": json.dumps(message)})

    async def jusqu_a(self, type_, delai=2):
        """Lit les messages jusqu'à en trouver un du type demandé (le plus récent d'une rafale d'états)."""
        while True:
            m = await self.recevoir(delai)
            if m is None or m.get("t") == type_:
                return m
