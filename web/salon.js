/* « Où suis-je ? » — écran d'un salon multijoueur (Partie entre amis). Le serveur décide de tout : ici on affiche
   l'état reçu et on envoie des intentions (régler, lancer, répondre, écrire). Tout texte venant d'autrui passe par
   textContent ou esc() : jamais de HTML, jamais de lien cliquable dans le chat. */
(function () {
  "use strict";
  const COULEURS = ["#2a7de1", "#e5484d", "#f5a524", "#8e4ec6", "#12a594", "#d6409f", "#6e56cf", "#ef5f00", "#0d74ce", "#7c9a1f"];
  const EMOJIS = ["😀", "😂", "😮", "😎", "👍", "👏", "🎉", "🤔"];
  const ATTENTE_MAX_MS = 60000;

  function ouvrir(ctx, code, spectateur) {
    const { app, esc, api, aller, nombre, distance } = ctx;
    code = String(code || "").toUpperCase();
    let ws = null, etat = null, ferme = false, tentativeDepuis = null, minuteurRetour = null;
    let signature = "", cleManche = "", reponseEnvoyee = false, choix = null, carteJeu = null, fin = 0;
    let chatOuvert = false, nonLus = 0;
    const nettoyer = [];
    ctx.nettoyages.push(() => { ferme = true; clearTimeout(minuteurRetour); nettoyer.forEach((f) => { try { f(); } catch (_) {} }); try { ws && ws.close(); } catch (_) {} });

    const pseudoStocke = (() => { try { return localStorage.getItem("pseudo") || ""; } catch (_) { return ""; } })();

    function pageErreur(message) {
      ferme = true;
      app.innerHTML = '<main class="centre"><h1>Salon</h1><p class="erreur" role="alert">' + esc(message) +
        '</p><p><a class="bouton" href="/">Retour à l\'accueil</a></p></main>';
    }

    // ---------------------------------------------------------------- entrée : pseudo des invités
    async function demarrer() {
      try { await api("/api/salons/" + encodeURIComponent(code)); } catch (e) { return pageErreur(e.message); }
      if (ctx.moi.connecte) return connecter(ctx.moi.pseudo);
      app.innerHTML = `<main class="accueil"><h1>Salon ${esc(code)}</h1>
        <form id="entree" class="reglages"><label>Ton pseudo <input name="pseudo" maxlength="20" placeholder="Invité" value="${esc(pseudoStocke)}">
        <small>Écris un surnom, pas ton vrai nom. Les autres personnes du salon le verront.</small></label>
        <button class="bouton gros" type="submit">${spectateur ? "Regarder" : "Entrer dans le salon"}</button></form>
        <p><a href="/">Retour</a></p></main>`;
      document.getElementById("entree").addEventListener("submit", (e) => {
        e.preventDefault();
        const p = String(new FormData(e.target).get("pseudo") || "").trim();
        try { localStorage.setItem("pseudo", p); } catch (_) {}
        connecter(p);
      });
    }

    // ---------------------------------------------------------------- liaison
    function connecter(pseudo) {
      construireCadre();
      const url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/salons/" + encodeURIComponent(code);
      let ouverte = false;
      ws = new WebSocket(url);
      ws.onopen = () => {
        ouverte = true; tentativeDepuis = null; bandeau("");
        ws.send(JSON.stringify({ t: "entrer", pseudo, role: spectateur ? "spectateur" : "joueur" }));   // pas dans l'adresse : jamais dans les journaux
      };
      ws.onmessage = (ev) => {
        let m; try { m = JSON.parse(ev.data); } catch (_) { return; }
        if (m.t === "etat") { etat = m; afficher(); }
        else if (m.t === "chat") ajouterChat(m);
        else if (m.t === "erreur") { if (m.fatale) { ferme = true; pageErreur(m.message); } else bandeau(m.message, 4000); }
        else if (m.t === "exclu") { ferme = true; pageErreur("L'hôte t'a exclu du salon."); }
      };
      ws.onclose = () => {
        if (ferme) return;
        tentativeDepuis = tentativeDepuis || Date.now();
        if (Date.now() - tentativeDepuis > ATTENTE_MAX_MS) return pageErreur("Connexion perdue : tu as été retiré du salon.");
        bandeau("Connexion perdue… reconnexion en cours.");
        minuteurRetour = setTimeout(() => connecter(pseudo), 2000);
      };
      ws.onerror = () => { if (!ouverte && !tentativeDepuis) bandeau("Connexion impossible pour l'instant."); };
    }

    function envoyer(m) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(m)); }

    // ---------------------------------------------------------------- cadre permanent (zone de jeu + chat)
    function construireCadre() {
      app.innerHTML = `<div class="salon">
        <div id="salon-zone"></div>
        <p id="salon-bandeau" class="erreur flottant" role="alert" hidden></p>
        <div class="chat" id="chat">
          <button type="button" class="bouton" id="chat-bascule" aria-expanded="false">💬 Chat <span id="chat-points" hidden>●</span></button>
          <div id="chat-corps" hidden>
            <div id="chat-liste" class="chat-liste" aria-live="polite"></div>
            <div class="chat-emojis">${EMOJIS.map((e) => `<button type="button" class="emoji" data-e="${e}" aria-label="Envoyer ${e}">${e}</button>`).join("")}</div>
            <form id="chat-form"><input id="chat-texte" maxlength="200" autocomplete="off" placeholder="Écris un message…"><button class="bouton" type="submit">Envoyer</button></form>
            <small class="discret">Visible seulement des personnes du salon, jamais enregistré.</small>
          </div>
        </div></div>`;
      const corps = document.getElementById("chat-corps");
      document.getElementById("chat-bascule").onclick = (ev) => {
        chatOuvert = corps.hidden; corps.hidden = !chatOuvert;
        ev.currentTarget.setAttribute("aria-expanded", String(chatOuvert));
        if (chatOuvert) { nonLus = 0; document.getElementById("chat-points").hidden = true; document.getElementById("chat-texte").focus(); }
      };
      document.getElementById("chat-form").addEventListener("submit", (e) => {
        e.preventDefault();
        const i = document.getElementById("chat-texte");
        if (i.value.trim()) envoyer({ t: "chat", texte: i.value });
        i.value = "";
      });
      document.querySelectorAll(".emoji").forEach((b) => { b.onclick = () => envoyer({ t: "chat", texte: b.dataset.e }); });
      signature = ""; cleManche = "";
    }

    function ajouterChat(m) {
      const liste = document.getElementById("chat-liste"); if (!liste) return;
      const p = document.createElement("p");
      const nom = document.createElement("strong"); nom.textContent = m.de + " : ";
      p.appendChild(nom); p.appendChild(document.createTextNode(m.texte));       // texte brut : aucun lien cliquable
      liste.appendChild(p);
      while (liste.children.length > 100) liste.removeChild(liste.firstChild);
      liste.scrollTop = liste.scrollHeight;
      if (!chatOuvert && etat && m.id !== etat.moi.id) { nonLus++; document.getElementById("chat-points").hidden = false; }
    }

    let delaiBandeau = null;
    function bandeau(texte, duree) {
      const b = document.getElementById("salon-bandeau"); if (!b) return;
      b.textContent = texte; b.hidden = !texte;
      clearTimeout(delaiBandeau);
      if (texte && duree) delaiBandeau = setTimeout(() => { b.hidden = true; }, duree);
    }

    // ---------------------------------------------------------------- affichage selon la phase
    function afficher() {
      const zone = document.getElementById("salon-zone"); if (!zone) return;
      if (etat.phase === "attente") return ecranAttente(zone);
      if (etat.phase === "manche") return ecranManche(zone);
      return ecranResultat(zone);
    }

    function liensMembres(hote) {
      return etat.membres.map((m) => {
        const actions = hote && m.id !== etat.moi.id
          ? `<button type="button" class="petit" data-muet="${esc(m.id)}" data-valeur="${!m.muet}">${m.muet ? "Rendre la parole" : "Rendre muet"}</button>
             <button type="button" class="petit" data-exclure="${esc(m.id)}">Exclure</button>` : "";
        return `<li class="${m.connecte ? "" : "absent"}"><span>${m.hote ? "👑 " : ""}${esc(m.pseudo)}${m.id === etat.moi.id ? " (toi)" : ""}
          ${m.role === "spectateur" ? '<small class="discret">spectateur</small>' : ""}${m.connecte ? "" : ' <small class="discret">déconnecté</small>'}${m.muet ? " 🔇" : ""}</span>
          <span>${actions}</span></li>`;
      }).join("");
    }

    function brancherActionsHote(zone) {
      zone.querySelectorAll("[data-muet]").forEach((b) => { b.onclick = () => envoyer({ t: "muet", id: b.dataset.muet, valeur: b.dataset.valeur === "true" }); });
      zone.querySelectorAll("[data-exclure]").forEach((b) => { b.onclick = () => { if (confirm("Exclure cette personne du salon ?")) envoyer({ t: "exclure", id: b.dataset.exclure }); }; });
    }

    function ecranAttente(zone) {
      const sig = "attente" + JSON.stringify(etat);
      cleManche = ""; nettoieJeu();
      if (sig === signature) return; signature = sig;
      const hote = etat.moi.hote, r = etat.reglages, joueurs = etat.membres.filter((m) => m.role === "joueur").length;
      const lien = location.origin + "/?salon=" + encodeURIComponent(code);
      zone.innerHTML = `<main class="accueil">
        <h1>Salon <span class="code" id="code-salon">${esc(code)}</span></h1>
        <p class="sous-titre">Donne ce code (ou ce lien) aux personnes que tu connais : toute personne qui l'a peut entrer et écrire dans le chat.</p>
        <p><input id="lien" readonly value="${esc(lien)}" size="36"> <button type="button" class="bouton" id="copier">Copier le lien</button></p>
        <section class="encadre"><h2>Réglages</h2>
          ${hote ? `<div class="reglages">
            <label>Carte <select id="r-carte">${ctx.cartes.map((c) => `<option value="${esc(c.id)}"${c.nb_lieux < 5 ? " disabled" : ""}${c.id === r.carte.id ? " selected" : ""}>${esc(c.nom)}</option>`).join("")}</select></label>
            <label>Déplacement <select id="r-contrainte">${Object.entries(ctx.CONTRAINTES).map(([k, v]) => `<option value="${k}"${k === r.contrainte ? " selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
            <label>Chrono par manche <select id="r-chrono">${Object.entries(ctx.CHRONOS).map(([k, v]) => `<option value="${k}"${Number(k) === r.chrono ? " selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
          </div>` : `<p>${esc(r.carte.nom)} — ${esc(ctx.CONTRAINTES[r.contrainte])} — ${esc(ctx.CHRONOS[r.chrono])}</p>`}
          <p class="discret">${r.nb_manches} manches.</p>
        </section>
        <section class="encadre"><h2>Dans le salon (${etat.membres.length})</h2><ul class="membres">${liensMembres(hote)}</ul>
          ${hote ? `<label class="interrupteur"><input type="checkbox" id="chat-actif"${etat.chat_actif ? " checked" : ""}> Chat autorisé</label>
            <label class="interrupteur"><input type="checkbox" id="verrou"${etat.verrouille ? " checked" : ""}> Salon verrouillé (plus personne de nouveau ne peut entrer)</label>` : (etat.chat_actif ? "" : '<p class="discret">L\'hôte a coupé le chat.</p>')}
        </section>
        ${etat.moi.role === "spectateur" ? '<p class="discret">Tu regardes la partie sans jouer.</p>' : ""}
        ${hote ? `<button class="bouton gros" id="lancer"${joueurs < 2 ? " disabled" : ""}>${joueurs < 2 ? "Il faut au moins 2 joueurs" : "Lancer la partie"}</button>`
               : '<p class="discret">En attente de l\'hôte…</p>'}
        <p><a href="/" id="quitter">Quitter le salon</a></p>
      </main>`;
      document.getElementById("copier").onclick = () => { const i = document.getElementById("lien"); i.select(); if (navigator.clipboard) navigator.clipboard.writeText(i.value).catch(() => {}); };
      document.getElementById("quitter").onclick = (e) => { e.preventDefault(); aller("/"); };
      if (hote) {
        const regler = () => envoyer({ t: "regler", carte: document.getElementById("r-carte").value,
          contrainte: document.getElementById("r-contrainte").value, chrono: Number(document.getElementById("r-chrono").value) });
        ["r-carte", "r-contrainte", "r-chrono"].forEach((id) => { document.getElementById(id).onchange = regler; });
        document.getElementById("chat-actif").onchange = (e) => envoyer({ t: "chat_actif", valeur: e.target.checked });
        document.getElementById("verrou").onchange = (e) => envoyer({ t: "verrouiller", valeur: e.target.checked });
        document.getElementById("lancer").onclick = () => envoyer({ t: "lancer" });
        brancherActionsHote(zone);
      }
    }

    // --- manche en cours
    let panorama = null, minuteurChrono = null;
    function nettoieJeu() {
      if (panorama) { try { panorama.detruire(); } catch (_) {} panorama = null; }
      if (carteJeu) { try { carteJeu.detruire(); } catch (_) {} carteJeu = null; }
      clearInterval(minuteurChrono); minuteurChrono = null;
    }
    nettoyer.push(nettoieJeu);

    function majHud() {
      const joueurs = etat.membres.filter((m) => m.role === "joueur");
      const faits = joueurs.filter((m) => m.a_repondu).length;
      const h = document.getElementById("hud-reponses");
      if (h) h.textContent = faits + " / " + joueurs.length + " ont répondu";
      const l = document.getElementById("hud-liste");
      if (l) l.innerHTML = joueurs.map((m) => `<li class="${m.a_repondu ? "fait" : ""}">${m.a_repondu ? "✔" : "…"} ${esc(m.pseudo)}</li>`).join("");
    }

    async function ecranManche(zone) {
      const man = etat.manche, jouable = etat.moi.role === "joueur";
      const cle = "manche" + man.numero;
      if (cle !== cleManche) {
        cleManche = cle; signature = ""; nettoieJeu(); reponseEnvoyee = !!man.a_repondu; choix = null;
        zone.innerHTML = `<div class="jeu" data-contrainte="${esc(etat.reglages.contrainte)}">
          <div id="pano" class="pano"></div>
          <div class="hud"><span>Manche ${man.numero} / ${etat.reglages.nb_manches}</span><span id="hud-reponses"></span>
            <span id="hud-chrono" class="chrono" ${man.temps_restant === null ? "hidden" : ""}></span></div>
          <ul id="hud-liste" class="hud-liste"></ul>
          ${jouable ? `<div class="mini" id="mini"><button type="button" class="mini-bascule" id="bascule" aria-label="Afficher la carte">🗺️ Carte</button>
            <div id="mini-carte" class="mini-carte"></div><button type="button" class="bouton gros" id="valider" disabled>Choisis un endroit</button></div>`
            : '<p class="spectateur-info">Tu regardes la partie.</p>'}
        </div>`;
        const mid = cle;
        try {
          const p = await Panorama.monter(document.getElementById("pano"), man.image, etat.reglages.contrainte, ctx.config);
          if (cleManche !== mid) p.detruire(); else panorama = p;
        } catch (e) { bandeau(e.message); }
        if (jouable) {
          const bouton = document.getElementById("valider"), mini = document.getElementById("mini");
          carteJeu = new Carte(document.getElementById("mini-carte"), { actif: true, onClic: (lat, lon) => {
            if (reponseEnvoyee) return;
            choix = { lat, lon }; carteJeu.repere("moi", lat, lon, { couleur: "#2a7de1" });
            bouton.disabled = false; bouton.textContent = "Valider";
          } });
          const [s, w, n, e] = etat.reglages.carte.bbox; carteJeu.cadrer([[s, w], [n, e]], 8);
          document.getElementById("bascule").onclick = () => { mini.classList.toggle("ouverte"); setTimeout(() => carteJeu.dessiner(), 50); };
          bouton.onclick = valider;
          if (reponseEnvoyee) { bouton.disabled = true; bouton.textContent = "Réponse envoyée"; }
        }
      }
      if (man.temps_restant !== null) {
        fin = Date.now() + man.temps_restant * 1000;
        if (!minuteurChrono) {
          const aff = document.getElementById("hud-chrono");
          minuteurChrono = setInterval(() => {
            const reste = Math.max(0, Math.ceil((fin - Date.now()) / 1000));
            if (aff) { aff.textContent = Math.floor(reste / 60) + ":" + String(reste % 60).padStart(2, "0"); aff.classList.toggle("urgent", reste <= 10); }
            if (reste <= 0 && etat.moi.role === "joueur" && !reponseEnvoyee) valider();
          }, 250);
        }
      }
      if (reponseEnvoyee) { const b = document.getElementById("valider"); if (b) { b.disabled = true; b.textContent = "Réponse envoyée"; } }
      majHud();
    }

    function valider() {
      if (reponseEnvoyee) return;
      reponseEnvoyee = true;
      const b = document.getElementById("valider"); if (b) { b.disabled = true; b.textContent = "Réponse envoyée"; }
      if (choix) envoyer({ t: "repondre", lat: choix.lat, lon: choix.lon });   // sans clic : rien à envoyer, le serveur compte 0
    }

    // --- résultat d'une manche ou fin de partie
    function ecranResultat(zone) {
      const sig = "res" + JSON.stringify(etat);
      cleManche = ""; if (sig === signature) return; signature = sig;
      nettoieJeu();
      const r = etat.resultat, final = etat.phase === "fin", hote = etat.moi.hote;
      const couleur = (id) => COULEURS[Math.max(0, etat.membres.findIndex((m) => m.id === id)) % COULEURS.length];
      zone.innerHTML = `<div class="resultat"><div id="res-carte" class="res-carte"></div>
        <aside class="res-panneau">
          <p class="manche-titre">${final ? "Partie terminée" : "Manche " + r.numero + " / " + etat.reglages.nb_manches}</p>
          <h2>C'était ${esc(r.fiche.drapeau)} ${esc(r.fiche.nom)}</h2>
          <table class="recap"><thead><tr><th>Joueur</th><th>Distance</th><th>Points</th></tr></thead><tbody>
            ${r.reponses.map((x) => `<tr><td><span class="pastille" style="background:${couleur(x.id)}"></span>${esc(x.pseudo)}</td><td>${x.distance_m === null ? "—" : esc(distance(x.distance_m))}</td><td>+${nombre(x.points)}</td></tr>`).join("")}
          </tbody></table>
          <h3>${final ? "Classement final" : "Classement"}</h3>
          <ol class="classement">${etat.classement.map((c) => `<li><span>${esc(c.pseudo)}</span><strong>${nombre(c.total)} pts</strong></li>`).join("")}</ol>
          <div class="actions">
            ${hote ? (final ? '<button class="bouton gros" id="rejouer">Rejouer dans ce salon</button>' : '<button class="bouton gros" id="suivante">Manche suivante</button>')
                   : '<span class="discret">En attente de l\'hôte…</span>'}
            <a class="bouton" href="/" id="quitter">Quitter</a>
          </div>
          <h3>Dans le salon</h3><ul class="membres">${liensMembres(hote)}</ul>
        </aside></div>`;
      carteJeu = new Carte(document.getElementById("res-carte"), { actif: false });
      const pts = [[r.lieu.lat, r.lieu.lon]];
      carteJeu.repere("vrai", r.lieu.lat, r.lieu.lon, { couleur: "#1f9d55", etiquette: "Lieu" });
      r.reponses.forEach((x) => {
        if (x.lat === null) return;
        carteJeu.repere("p" + x.id, x.lat, x.lon, { couleur: couleur(x.id), etiquette: x.pseudo });
        carteJeu.ligne("l" + x.id, [r.lieu.lat, r.lieu.lon], [x.lat, x.lon]); pts.push([x.lat, x.lon]);
      });
      if (pts.length > 1) carteJeu.cadrer(pts, 70); else carteJeu.vue(r.lieu.lat, r.lieu.lon, 8);
      document.getElementById("quitter").onclick = (e) => { e.preventDefault(); aller("/"); };
      const suiv = document.getElementById("suivante"), rej = document.getElementById("rejouer");
      if (suiv) suiv.onclick = () => envoyer({ t: "suivante" });
      if (rej) rej.onclick = () => envoyer({ t: "rejouer" });
      if (hote) brancherActionsHote(zone);
    }

    demarrer();
  }

  window.Salon = { ouvrir };
})();
