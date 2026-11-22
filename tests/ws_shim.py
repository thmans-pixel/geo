"""Relais de TEST : parle le vrai protocole WebSocket (RFC 6455) au navigateur et passe les connexions à l'application
ASGI, parce que la bibliothèque `websockets` (nécessaire à uvicorn) n'est pas installable dans l'environnement de
développement. Tout le reste (HTTP) est relayé tel quel vers uvicorn. Ne sert qu'aux tests, jamais en production."""
import asyncio
import base64
import hashlib
import struct
from urllib.parse import unquote

GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


async def _lire_trame(r):
    b = await r.readexactly(2)
    op, masque, n = b[0] & 0x0F, b[1] & 0x80, b[1] & 0x7F
    if n == 126:
        n = struct.unpack(">H", await r.readexactly(2))[0]
    elif n == 127:
        n = struct.unpack(">Q", await r.readexactly(8))[0]
    cle = await r.readexactly(4) if masque else b""
    d = await r.readexactly(n)
    if masque:
        d = bytes(x ^ cle[i % 4] for i, x in enumerate(d))
    return op, d


def _trame(op, d=b""):
    n = len(d)
    tete = bytes([0x80 | op]) + (bytes([n]) if n < 126 else b"\x7e" + struct.pack(">H", n) if n < 65536 else b"\x7f" + struct.pack(">Q", n))
    return tete + d


async def _tuyau(r, w):
    try:
        while data := await r.read(65536):
            w.write(data)
            await w.drain()
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass


def serveur_relais(app, port_uvicorn):
    async def gerer(r, w):
        try:
            tete = await r.readuntil(b"\r\n\r\n")
        except Exception:
            w.close()
            return
        lignes = tete.decode("latin-1").split("\r\n")
        _, chemin, _ = lignes[0].split(" ", 2)
        h = {}
        for l in lignes[1:]:
            if ": " in l:
                k, v = l.split(": ", 1)
                h[k.lower()] = v
        if h.get("upgrade", "").lower() != "websocket":
            ur, uw = await asyncio.open_connection("127.0.0.1", port_uvicorn)
            uw.write(tete)
            await asyncio.gather(_tuyau(r, uw), _tuyau(ur, w))
            return
        chemin_seul, _, requete = chemin.partition("?")
        scope = {"type": "websocket", "asgi": {"version": "3.0"}, "scheme": "ws", "path": unquote(chemin_seul),
                 "raw_path": chemin_seul.encode(), "query_string": requete.encode(), "subprotocols": [],
                 "headers": [(k.encode("latin-1"), v.encode("latin-1")) for k, v in h.items()],
                 "server": ("127.0.0.1", 0), "client": ("127.0.0.1", 1)}
        entrant = asyncio.Queue()
        await entrant.put({"type": "websocket.connect"})

        async def lecteur():
            try:
                while True:
                    op, d = await _lire_trame(r)
                    if op == 1:
                        await entrant.put({"type": "websocket.receive", "text": d.decode()})
                    elif op == 8:
                        break
                    elif op == 9:
                        w.write(_trame(10, d))
            except Exception:
                pass
            await entrant.put({"type": "websocket.disconnect", "code": 1000})

        async def send(m):
            if m["type"] == "websocket.accept":
                accept = base64.b64encode(hashlib.sha1(h["sec-websocket-key"].encode() + GUID).digest()).decode()
                w.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                         f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
            elif m["type"] == "websocket.send":
                w.write(_trame(1, m["text"].encode()) if m.get("text") is not None else _trame(2, m["bytes"]))
            elif m["type"] == "websocket.close":
                w.write(_trame(8, struct.pack(">H", m.get("code", 1000))))
            elif m["type"] == "websocket.http.response.start":
                w.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            await w.drain()

        tache = asyncio.ensure_future(lecteur())
        try:
            await app(scope, entrant.get, send)
        except Exception:
            pass
        finally:
            tache.cancel()
            try:
                w.close()
            except Exception:
                pass

    return gerer
