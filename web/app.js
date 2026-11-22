/* « Où suis-je ? » — écrans du jeu solo. JavaScript sans framework. */
(function () {
  "use strict";
  const app = document.getElementById("app");
  let config = { images: "factice" };
  let moi = { connecte: false };
  let succesEnAttente = [];   // succès gagnés, à montrer sur l'écran de résultat
  let cartes = [];
  let nettoyages = [];   // minuteurs, cartes, images à défaire en changeant d'écran

  const MODES = {
    classique:   { nom: "Classique", texte: "5 manches, jusqu'à 5 000 points par manche.", champs: ["carte", "contrainte", "chrono"], bouton: "Jouer" },
    defi_jour:   { nom: "Défi du jour", texte: "Les mêmes 5 lieux pour tout le monde, une seule tentative par jour.", champs: [], bouton: "Jouer le défi du jour" },
    defi:        { nom: "Défi à partager", texte: "Crée un lien : tes amis jouent les mêmes 5 lieux que toi.", champs: ["carte", "contrainte", "chrono"], bouton: "Créer le défi" },
    serie:       { nom: "Série de pays", texte: "Devine le pays. La série continue tant que tu as juste.", champs: ["carte", "contrainte", "chrono"], bouton: "Jouer" },
    exploration: { nom: "Exploration", texte: "Balade-toi sans score, révèle le lieu quand tu veux.", champs: ["carte", "contrainte"], bouton: "Explorer" },
  };
  const CONTRAINTES = { libre: "Libre", sans_deplacement: "Sans déplacement", fige: "Figé (ni déplacement, ni rotation, ni zoom)" };
  const CHRONOS = { 0: "Pas de chrono", 10: "10 secondes", 30: "30 secondes", 60: "1 minute", 120: "2 minutes", 300: "5 minutes" };

  // ---------------------------------------------------------------- outils
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function nombre(n) { return Math.round(n).toLocaleString("fr-FR"); }
  function distance(m) {
    if (m === null || m === undefined) return "—";
    if (m < 1000) return nombre(m) + " m";
    return (m / 1000).toLocaleString("fr-FR", { maximumFractionDigits: m < 10000 ? 1 : 0 }) + " km";
  }
  function pseudoStocke() { try { return localStorage.getItem("pseudo") || ""; } catch (_) { return ""; } }
  function stockerPseudo(v) { try { localStorage.setItem("pseudo", v); } catch (_) {} }
  function nettoyer() { nettoyages.forEach((f) => { try { f(); } catch (_) {} }); nettoyages = []; }

  async function api(chemin, corps) {
    // « X-Requete » : exigé par le serveur pour toute action qui modifie un compte ou une carte.
    const options = { headers: { "X-Requete": "ou-suis-je" } };
    if (corps === "SUPPRIMER") options.method = "DELETE";
    else if (corps !== undefined) {
      options.method = "POST"; options.headers["Content-Type"] = "application/json"; options.body = JSON.stringify(corps);
    }
    const r = await fetch(chemin, options);
    let data = {};
    try { data = await r.json(); } catch (_) {}
    if (!r.ok) { const e = new Error(data.erreur || "Une erreur est survenue."); e.statut = r.status; e.data = data; throw e; }
    return data;
  }

  function aller(url, remplacer) {
    if (remplacer) history.replaceState(null, "", url); else history.pushState(null, "", url);
    route();
  }

  function erreurFatale(e) {
    nettoyer();
    app.innerHTML = '<main class="centre"><h1>Oups</h1><p class="erreur" role="alert">' + esc(e.message || e) +
      '</p><p><a class="bouton" href="/">Retour à l\'accueil</a></p></main>';
  }

  // ---------------------------------------------------------------- barre du haut
  function barre() {
    const liens = moi.connecte
      ? `<a href="/?profil=1">👤 ${esc(moi.pseudo)} · niv. ${moi.niveau.niveau}</a><a href="/?classements=1">Classements</a>` +
        (moi.admin ? '<a href="/?editeur=1">Éditeur de cartes</a>' : "")
      : `<a href="/?classements=1">Classements</a><a href="${esc(moi.url_connexion || "/")}" id="connexion">Se connecter</a>`;
    return `<nav class="barre" aria-label="Menu"><a href="/" class="marque">Où suis-je ?</a><span>${liens}</span></nav>`;
  }
  function lierBarre() {
    app.querySelectorAll(".barre a, .retour").forEach((a) => {
      const h = a.getAttribute("href");
      if (h && h.startsWith("/") && !h.startsWith("/yunohost")) a.onclick = (e) => { e.preventDefault(); aller(h); };
    });
  }
  function annoncesSucces(liste) {
    if (!liste || !liste.length) return "";
    return `<div class="succes-gagne" role="status">${liste.map((x) => `🏅 Succès : <strong>${esc(x.nom)}</strong> (+50 XP)`).join("<br>")}</div>`;
  }

  // ---------------------------------------------------------------- accueil
  async function accueil() {
    nettoyer();
    const jour = await api("/api/defi-du-jour").catch(() => null);
    app.innerHTML = `
      ${barre()}
      <main class="accueil">
        <h1>Où suis-je ?</h1>
        <p class="sous-titre">Regarde autour de toi, repère-toi sur la carte, devine où tu es dans le monde.</p>
        <div class="modes" id="modes" role="group" aria-label="Mode de jeu">
          ${Object.entries(MODES).map(([id, m]) => `
            <button type="button" class="mode" data-mode="${id}" aria-pressed="false">
              <strong>${esc(m.nom)}</strong><span>${esc(m.texte)}</span>
            </button>`).join("")}
        </div>
        <form id="reglages" class="reglages" autocomplete="off">
          ${moi.connecte ? "" : `<label>Ton pseudo <input name="pseudo" maxlength="20" placeholder="Invité" value="${esc(pseudoStocke())}"><small>Écris un surnom, pas ton vrai nom.</small></label>`}
          <label data-champ="carte">Carte
            <select name="carte">${cartes.map((c) => `<option value="${esc(c.id)}"${c.nb_lieux < 5 ? " disabled" : ""}>${esc(c.nom)}</option>`).join("")}</select>
          </label>
          <label data-champ="contrainte">Déplacement
            <select name="contrainte">${Object.entries(CONTRAINTES).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
          </label>
          <label data-champ="chrono">Chrono par manche
            <select name="chrono">${Object.entries(CHRONOS).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
          </label>
          <button type="submit" class="bouton gros" id="jouer">Jouer</button>
        </form>
        <p id="message" class="erreur" role="alert" hidden></p>
        <section id="lien-defi" class="encadre" hidden></section>
        <section class="encadre" id="classement-jour">${jour ? classementHtml("Défi du jour", jour.classement) : ""}</section>
      </main>`;

    lierBarre();
    const form = document.getElementById("reglages");
    const message = document.getElementById("message");
    let mode = "classique";
    function choisir(m) {
      mode = m;
      document.querySelectorAll(".mode").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === m)));
      form.querySelectorAll("[data-champ]").forEach((l) => { l.hidden = !MODES[m].champs.includes(l.dataset.champ); });
      document.getElementById("jouer").textContent = MODES[m].bouton;
      document.getElementById("lien-defi").hidden = true;
      message.hidden = true;
    }
    document.getElementById("modes").addEventListener("click", (e) => {
      const b = e.target.closest(".mode"); if (b) choisir(b.dataset.mode);
    });
    choisir("classique");

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = new FormData(form);
      const pseudo = moi.connecte ? moi.pseudo : String(f.get("pseudo") || "").trim();
      if (!moi.connecte) stockerPseudo(pseudo);
      const reglages = { carte: f.get("carte"), contrainte: f.get("contrainte"), chrono: Number(f.get("chrono")), pseudo };
      message.hidden = true;
      try {
        if (mode === "defi") {
          const d = await api("/api/defis", reglages);
          const lien = location.origin + d.lien;
          const zone = document.getElementById("lien-defi");
          zone.hidden = false;
          zone.innerHTML = `<h2>Ton défi est prêt</h2><p>Envoie ce lien à tes amis :</p>
            <p><input id="lien" readonly value="${esc(lien)}" size="38"> <button type="button" class="bouton" id="copier">Copier</button></p>
            <p><a class="bouton gros" href="${esc(d.lien)}" id="jouer-defi">Jouer ce défi</a></p>`;
          document.getElementById("copier").onclick = () => {
            const i = document.getElementById("lien"); i.select();
            if (navigator.clipboard) navigator.clipboard.writeText(i.value).catch(() => {});
          };
          document.getElementById("jouer-defi").onclick = (ev) => { ev.preventDefault(); aller(d.lien); };
          return;
        }
        const p = await api("/api/parties", Object.assign({ mode }, mode === "defi_jour" ? { pseudo } : reglages));
        aller("/?partie=" + encodeURIComponent(p.id));
      } catch (err) {
        if (err.statut === 409 && err.data && err.data.partie_id) { aller("/?partie=" + encodeURIComponent(err.data.partie_id)); return; }
        message.textContent = err.message; message.hidden = false;
      }
    });
  }

  function classementHtml(titre, liste) {
    if (!liste || !liste.length) return `<h2>${esc(titre)}</h2><p class="discret">Personne n'a encore terminé ce défi.</p>`;
    return `<h2>${esc(titre)}</h2><ol class="classement">${liste.map((l) =>
      `<li><span>${esc(l.pseudo)}</span><strong>${nombre(l.total)} pts</strong></li>`).join("")}</ol>`;
  }

  // ---------------------------------------------------------------- page d'un défi
  async function pageDefi(id) {
    nettoyer();
    const d = await api("/api/defis/" + encodeURIComponent(id));
    app.innerHTML = `
      ${barre()}
      <main class="accueil">
        <h1>${esc(d.nom)}</h1>
        <p class="sous-titre">${d.nb_manches} lieux sur la carte « ${esc(d.carte_nom)} » — ${esc(CONTRAINTES[d.contrainte])} — ${esc(CHRONOS[d.chrono])}.</p>
        <form id="rejoindre" class="reglages">
          ${moi.connecte ? `<p>Tu joues sous le pseudo <strong>${esc(moi.pseudo)}</strong>.</p>` : `<label>Ton pseudo <input name="pseudo" maxlength="20" placeholder="Invité" value="${esc(pseudoStocke())}"><small>Écris un surnom, pas ton vrai nom.</small></label>`}
          ${d.deja_joue ? '<button type="submit" class="bouton gros" id="jouer">Voir ma partie</button>'
                        : '<button type="submit" class="bouton gros" id="jouer">Jouer ce défi</button>'}
        </form>
        <p id="message" class="erreur" role="alert" hidden></p>
        <section class="encadre">${classementHtml("Classement", d.classement)}</section>
        <p><a href="/">Autres modes de jeu</a></p>
      </main>`;
    lierBarre();
    document.getElementById("rejoindre").addEventListener("submit", async (e) => {
      e.preventDefault();
      if (d.deja_joue) { aller("/?partie=" + encodeURIComponent(d.deja_joue.partie_id)); return; }
      const pseudo = moi.connecte ? moi.pseudo : String(new FormData(e.target).get("pseudo") || "").trim();
      if (!moi.connecte) stockerPseudo(pseudo);
      try {
        const p = await api("/api/parties", { mode: "defi", defi_id: id, pseudo });
        aller("/?partie=" + encodeURIComponent(p.id));
      } catch (err) {
        if (err.statut === 409 && err.data && err.data.partie_id) { aller("/?partie=" + encodeURIComponent(err.data.partie_id)); return; }
        const m = document.getElementById("message"); m.textContent = err.message; m.hidden = false;
      }
    });
  }

  // ---------------------------------------------------------------- partie
  async function partie(id, recap) {
    let etat;
    try { etat = await api("/api/parties/" + encodeURIComponent(id)); } catch (e) { return erreurFatale(e); }
    nettoyer();
    if (recap) return ecranRecap(id);
    if (etat.phase === "question") return ecranQuestion(etat);
    return ecranResultat(etat);
  }

  function titreManche(etat) {
    const p = etat.partie;
    if (p.mode === "exploration") return "Exploration";
    if (p.mode === "serie") return "Série : " + etat.total;
    const n = (etat.manche || etat.resultat).numero;
    return "Manche " + n + " / " + p.nb_manches;
  }

  async function ecranQuestion(etat) {
    const p = etat.partie, expl = p.mode === "exploration", serie = p.mode === "serie";
    app.innerHTML = `
      <div class="jeu" data-contrainte="${esc(p.contrainte)}">
        <div id="pano" class="pano"></div>
        <div class="hud">
          <span id="hud-manche">${esc(titreManche(etat))}</span>
          ${expl ? "" : serie ? `<span id="hud-score">Carte : ${esc(p.carte.nom)}</span>` : `<span id="hud-score">${nombre(etat.total)} pts</span>`}
          <span id="hud-chrono" class="chrono" ${etat.manche.temps_restant === null ? "hidden" : ""}></span>
        </div>
        ${expl ? `<div class="actions-expl"><button class="bouton gros" id="reveler">Révéler le lieu</button></div>` : `
        <div class="mini" id="mini">
          <button type="button" class="mini-bascule" id="bascule" aria-label="Afficher la carte">🗺️ Carte</button>
          <div id="mini-carte" class="mini-carte"></div>
          <button type="button" class="bouton gros" id="valider" disabled>Choisis un endroit</button>
        </div>`}
        <p id="message" class="erreur flottant" role="alert" hidden></p>
      </div>`;

    const message = document.getElementById("message");
    let image = null;
    try {
      image = await Panorama.monter(document.getElementById("pano"), etat.manche.image, p.contrainte, config);
      nettoyages.push(() => image.detruire());
    } catch (e) { message.textContent = e.message; message.hidden = false; }

    if (expl) {
      document.getElementById("reveler").onclick = async () => {
        try { const rv = await api("/api/parties/" + encodeURIComponent(p.id) + "/reveler", {}); succesEnAttente = rv.nouveaux_succes || []; await partie(p.id); }
        catch (e) { message.textContent = e.message; message.hidden = false; }
      };
      return;
    }

    // mini-carte et validation
    let choix = null, envoye = false;
    const mini = document.getElementById("mini");
    const bouton = document.getElementById("valider");
    const carte = new Carte(document.getElementById("mini-carte"), {
      actif: true,
      onClic: (lat, lon) => {
        if (envoye) return;
        choix = { lat, lon };
        carte.repere("moi", lat, lon, { couleur: "#2a7de1" });
        bouton.disabled = false; bouton.textContent = "Valider";
      },
    });
    nettoyages.push(() => carte.detruire());
    const [s, w, n, e] = p.carte.bbox;
    carte.cadrer([[s, w], [n, e]], 8);
    document.getElementById("bascule").onclick = () => { mini.classList.toggle("ouverte"); setTimeout(() => carte.dessiner(), 50); };

    async function valider() {
      if (envoye) return; envoye = true; bouton.disabled = true;
      try {
        const rep = await api("/api/parties/" + encodeURIComponent(p.id) + "/reponse", choix ? { lat: choix.lat, lon: choix.lon } : {});
        succesEnAttente = rep.nouveaux_succes || [];
      } catch (err) { if (err.statut !== 409) { envoye = false; message.textContent = err.message; message.hidden = false; return; } }
      await partie(p.id);
    }
    bouton.onclick = valider;

    if (etat.manche.temps_restant !== null) {
      const fin = Date.now() + etat.manche.temps_restant * 1000, aff = document.getElementById("hud-chrono");
      const tic = () => {
        const reste = Math.max(0, Math.ceil((fin - Date.now()) / 1000));
        aff.textContent = Math.floor(reste / 60) + ":" + String(reste % 60).padStart(2, "0");
        aff.classList.toggle("urgent", reste <= 10);
        if (fin - Date.now() <= 0) { clearInterval(minuteur); valider(); }
      };
      const minuteur = setInterval(tic, 200); tic();
      nettoyages.push(() => clearInterval(minuteur));
    }
  }

  function ficheHtml(f) {
    return `<section class="fiche">
      <h3><span class="drapeau">${f.drapeau}</span> ${esc(f.nom)}</h3>
      ${f.capitale ? `<p>Capitale : <strong>${esc(f.capitale)}</strong></p>` : ""}
      ${f.langues && f.langues.length ? `<p>Langue${f.langues.length > 1 ? "s" : ""} : ${esc(f.langues.join(", "))}</p>` : ""}
      ${f.circulation ? `<p>On roule à ${esc(f.circulation)}.</p>` : ""}
      ${f.indices && f.indices.length ? `<ul>${f.indices.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : ""}
    </section>`;
  }

  function ecranResultat(etat) {
    const p = etat.partie, r = etat.resultat, fin = etat.phase === "fin";
    const serie = p.mode === "serie", expl = p.mode === "exploration";
    let haut;
    if (expl) haut = "<h2>Tu étais ici</h2>";
    else if (serie) {
      haut = r.juste ? `<h2 class="bravo">Bravo, c'est bien ça !</h2><p>La série continue : <strong>${etat.total}</strong></p>`
        : `<h2 class="rate">Raté</h2><p>C'était <strong>${esc(r.fiche.nom)}</strong>${r.pays_choisi ? `, tu avais choisi ${esc(r.pays_choisi)}` : r.reponse ? ", tu avais cliqué en mer" : ""}.</p>
           <p>Série terminée : <strong>${r.serie}</strong> — record : <strong>${r.record}</strong></p>`;
    } else {
      haut = r.reponse
        ? `<h2>À <strong id="res-distance">${esc(distance(r.distance_m))}</strong> du lieu</h2><p class="points">+ <span id="res-points">${nombre(r.points)}</span> points</p>`
        : `<h2>${r.temps_ecoule ? "Temps écoulé !" : "Pas de réponse"}</h2><p class="points">+ <span id="res-points">0</span> point</p>`;
      haut += `<p>Total : <strong>${nombre(etat.total)}</strong>${p.nb_manches ? " / " + nombre(5000 * p.nb_manches) : ""}</p>`;
    }
    let action;
    if (expl) action = '<button class="bouton gros" id="suite">Autre lieu</button>';
    else if (fin && serie) action = '<button class="bouton gros" id="suite">Nouvelle série</button> <a class="bouton" href="/">Accueil</a>';
    else if (fin) action = '<button class="bouton gros" id="suite">Voir le récapitulatif</button>';
    else action = `<button class="bouton gros" id="suite">${serie ? "Lieu suivant" : "Manche suivante"}</button>`;

    app.innerHTML = `
      <div class="resultat">
        <div id="res-carte" class="res-carte"></div>
        <aside class="res-panneau">
          <p class="manche-titre">${esc(titreManche(etat))}</p>
          ${haut}
          ${annoncesSucces(succesEnAttente)}
          ${ficheHtml(r.fiche)}
          <p id="message" class="erreur" role="alert" hidden></p>
          <div class="actions">${action}</div>
        </aside>
      </div>`;

    succesEnAttente = [];
    const carte = new Carte(document.getElementById("res-carte"), { actif: false });
    nettoyages.push(() => carte.detruire());
    const points = [[r.lieu.lat, r.lieu.lon]];
    carte.repere("vrai", r.lieu.lat, r.lieu.lon, { couleur: "#1f9d55", etiquette: "Lieu" });
    if (r.reponse) {
      points.push([r.reponse.lat, r.reponse.lon]);
      carte.repere("moi", r.reponse.lat, r.reponse.lon, { couleur: "#2a7de1", etiquette: "Toi" });
      carte.ligne("trait", points[0], points[1]);
    }
    if (points.length > 1) carte.cadrer(points, 70); else carte.vue(r.lieu.lat, r.lieu.lon, 8);

    document.getElementById("suite").onclick = async () => {
      const m = document.getElementById("message");
      try {
        if (fin && serie) {
          const nouvelle = await api("/api/parties", { mode: "serie", carte: p.carte.id, contrainte: p.contrainte, chrono: p.chrono, pseudo: p.pseudo });
          aller("/?partie=" + encodeURIComponent(nouvelle.id));
        } else if (fin) aller("/?partie=" + encodeURIComponent(p.id) + "&recap=1");
        else { await api("/api/parties/" + encodeURIComponent(p.id) + "/suivante", {}); await partie(p.id); }
      } catch (e) { m.textContent = e.message; m.hidden = false; }
    };
  }

  async function ecranRecap(id) {
    let r;
    try { r = await api("/api/parties/" + encodeURIComponent(id) + "/recap"); } catch (e) { return erreurFatale(e); }
    const lien = r.partie.defi_id ? location.origin + "/?defi=" + encodeURIComponent(r.partie.defi_id) : null;
    app.innerHTML = `
      <div class="resultat">
        <div id="res-carte" class="res-carte"></div>
        <aside class="res-panneau">
          <h2>Récapitulatif</h2>
          <p class="points"><span id="recap-total">${nombre(r.total)}</span> / ${nombre(r.maximum)}</p>
          <table class="recap"><thead><tr><th>#</th><th>Lieu</th><th>Distance</th><th>Points</th></tr></thead><tbody>
            ${r.manches.map((m) => `<tr><td>${m.numero}</td><td>${m.fiche.drapeau} ${esc(m.fiche.nom)}</td><td>${esc(distance(m.distance_m))}</td><td>${nombre(m.points)}</td></tr>`).join("")}
          </tbody></table>
          ${r.classement ? `<div class="encadre">${classementHtml("Classement du défi", r.classement)}</div>` : ""}
          ${lien ? `<p>Lien du défi : <input readonly value="${esc(lien)}" size="30"></p>` : ""}
          <div class="actions">
            ${lien ? "" : '<button class="bouton gros" id="rejouer">Rejouer</button>'}
            <a class="bouton" href="/">Accueil</a>
          </div>
        </aside>
      </div>`;
    const carte = new Carte(document.getElementById("res-carte"), { actif: false });
    nettoyages.push(() => carte.detruire());
    const tous = [];
    r.manches.forEach((m) => {
      carte.repere("v" + m.numero, m.lieu.lat, m.lieu.lon, { couleur: "#1f9d55", etiquette: String(m.numero) });
      tous.push([m.lieu.lat, m.lieu.lon]);
      if (m.reponse) {
        carte.repere("m" + m.numero, m.reponse.lat, m.reponse.lon, { couleur: "#2a7de1" });
        carte.ligne("l" + m.numero, [m.lieu.lat, m.lieu.lon], [m.reponse.lat, m.reponse.lon]);
        tous.push([m.reponse.lat, m.reponse.lon]);
      }
    });
    carte.cadrer(tous, 50);
    const rej = document.getElementById("rejouer");
    if (rej) rej.onclick = async () => {
      const etat = await api("/api/parties/" + encodeURIComponent(id));
      const q = etat.partie;
      const nouvelle = await api("/api/parties", { mode: q.mode, carte: q.carte.id, contrainte: q.contrainte, chrono: q.chrono, pseudo: q.pseudo });
      aller("/?partie=" + encodeURIComponent(nouvelle.id));
    };
  }

  // ---------------------------------------------------------------- profil
  async function pageProfil() {
    nettoyer();
    if (!moi.connecte) { location.href = moi.url_connexion || "/"; return; }
    const p = await api("/api/moi/profil");
    const n = p.niveau, pct = Math.round(100 * (n.xp - n.xp_debut) / Math.max(1, n.xp_suivant - n.xp_debut));
    const paysLi = (l) => l.length ? `<ol class="classement">${l.map((x) =>
      `<li><span>${esc(x.nom)}</span><strong>${Math.round(100 * x.taux)} % (${x.manches} manches)</strong></li>`).join("")}</ol>`
      : '<p class="discret">Pas encore assez de manches (3 par pays).</p>';
    const modes = { classique: "Classique", defi: "Défi", defi_jour: "Défi du jour", serie: "Série", exploration: "Exploration" };
    app.innerHTML = `${barre()}
      <main class="accueil">
        <h1>${esc(p.compte.pseudo)}</h1>
        <p class="sous-titre">Compte « ${esc(p.compte.identifiant)} » — niveau <strong>${n.niveau}</strong>, ${nombre(n.xp)} XP</p>
        <div class="jauge" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div style="width:${pct}%"></div></div>
        <p class="discret">Prochain niveau à ${nombre(n.xp_suivant)} XP.</p>
        <form id="form-pseudo" class="reglages">
          <label>Mon pseudo <input name="pseudo" maxlength="20" value="${esc(p.compte.pseudo)}"><small>Un surnom, pas ton vrai nom. Il est visible dans les classements.</small></label>
          <button class="bouton" type="submit">Changer</button>
        </form>
        <p id="message" class="erreur" role="alert" hidden></p>
        <section class="encadre"><h2>Statistiques</h2>
          <p>Parties terminées : <strong>${p.parties_jouees}</strong> — distance moyenne : <strong>${esc(distance(p.distance_moyenne_m))}</strong></p>
          ${p.meilleurs_scores.length ? `<h3>Meilleurs scores</h3><ol class="classement">${p.meilleurs_scores.map((x) =>
            `<li><span>${esc(x.nom)}</span><strong>${nombre(x.total)} pts</strong></li>`).join("")}</ol>` : ""}
          ${Object.keys(p.records_serie).length ? `<h3>Records en Série</h3><ul>${Object.entries(p.records_serie).map(([k, v]) =>
            `<li>${esc(k)} : <strong>${v}</strong></li>`).join("")}</ul>` : ""}
          <h3>Pays les mieux reconnus</h3>${paysLi(p.pays_mieux_reconnus)}
          <h3>Pays à retravailler</h3>${paysLi(p.pays_moins_bien_reconnus)}
        </section>
        <section class="encadre"><h2>Succès</h2>
          <ul class="succes">${p.succes.map((x) => `<li class="${x.obtenu ? "obtenu" : ""}"><strong>${x.obtenu ? "🏅" : "🔒"} ${esc(x.nom)}</strong><span>${esc(x.description)}</span></li>`).join("")}</ul>
        </section>
        <section class="encadre"><h2>Dernières parties</h2>
          ${p.historique.length ? `<ol class="classement">${p.historique.map((h) =>
            `<li><span>${esc(modes[h.mode] || h.mode)} — ${esc(h.carte)} <small class="discret">${new Date(h.date * 1000).toLocaleDateString("fr-FR")}</small></span><strong>${nombre(h.total)}</strong></li>`).join("")}</ol>`
            : '<p class="discret">Aucune partie terminée.</p>'}
        </section>
      </main>`;
    lierBarre();
    document.getElementById("form-pseudo").addEventListener("submit", async (e) => {
      e.preventDefault();
      const m = document.getElementById("message");
      try {
        const r = await api("/api/moi/pseudo", { pseudo: String(new FormData(e.target).get("pseudo") || "") });
        moi.pseudo = r.pseudo; await pageProfil();
      } catch (err) { m.textContent = err.message; m.hidden = false; }
    });
  }

  // ---------------------------------------------------------------- classements
  async function pageClassements(carteId) {
    nettoyer();
    const d = await api("/api/classements?carte=" + encodeURIComponent(carteId || "monde"));
    const liste = (titre, l) => l.length ? classementHtml(titre, l) : `<h2>${esc(titre)}</h2><p class="discret">Personne pour l'instant.</p>`;
    app.innerHTML = `${barre()}
      <main class="accueil">
        <h1>Classements</h1>
        <p class="sous-titre">Seuls les joueurs connectés avec un compte y figurent.</p>
        <label class="reglages">Carte
          <select id="choix-carte">${cartes.map((c) => `<option value="${esc(c.id)}"${c.id === d.carte ? " selected" : ""}>${esc(c.nom)}</option>`).join("")}</select>
        </label>
        <section class="encadre">${liste("Meilleur score (Classique)", d.par_carte)}</section>
        <section class="encadre">${liste("Défi du jour", d.defi_du_jour)}</section>
        <section class="encadre">${liste("Record de la Série (pays d'affilée)", d.serie).replace(/ pts/g, "")}</section>
      </main>`;
    lierBarre();
    document.getElementById("choix-carte").onchange = (e) => aller("/?classements=1&carte=" + encodeURIComponent(e.target.value));
  }

  // ---------------------------------------------------------------- éditeur de cartes (administrateur)
  async function pageEditeur() {
    nettoyer();
    if (!moi.admin) { aller("/", true); return; }
    const existantes = (await api("/api/admin/cartes")).cartes;
    app.innerHTML = `${barre()}
      <main class="accueil editeur">
        <h1>Éditeur de cartes</h1>
        <p class="sous-titre">Clique sur la carte pour poser des lieux, ou trace une zone. Seuls les endroits où Street View existe sont gardés.</p>
        <div class="reglages">
          <label>Nom de la carte <input id="e-nom" maxlength="40"></label>
          <label>Description <input id="e-desc" maxlength="120"></label>
          <label>Façon de faire
            <select id="e-mode"><option value="points">Des lieux précis (clic)</option><option value="zone">Une zone (polygone)</option></select>
          </label>
          <label id="e-nombre-l" hidden>Nombre de lieux à trouver <input id="e-nombre" type="number" min="5" max="150" value="60"></label>
        </div>
        <div id="e-carte" class="e-carte"></div>
        <p id="e-compte" class="discret"></p>
        <div class="actions"><button class="bouton" id="e-annuler">Retirer le dernier point</button>
          <button class="bouton" id="e-vider">Tout effacer</button>
          <button class="bouton gros" id="e-creer">Créer la carte</button></div>
        <p id="message" class="erreur" role="alert" hidden></p>
        <p id="e-ok" class="succes-gagne" role="status" hidden></p>
        <section class="encadre"><h2>Cartes créées</h2>
          ${existantes.length ? `<ul class="succes">${existantes.map((c) => `<li><strong>${esc(c.nom)}</strong><span>${c.lieux} lieux · par ${esc(c.auteur)} ·
            <button class="bouton archiver" data-id="${esc(c.id)}">Archiver</button></span></li>`).join("")}</ul>` : '<p class="discret">Aucune carte personnalisée.</p>'}
        </section>
      </main>`;
    lierBarre();
    const carte = new Carte(document.getElementById("e-carte"), { actif: true, onClic: (lat, lon) => { pts.push([lat, lon]); maj(); } });
    nettoyages.push(() => carte.detruire());
    carte.vue(30, 10, 2);
    const pts = [];
    const modeSel = document.getElementById("e-mode");
    function maj() {
      carte.effacer();
      const zone = modeSel.value === "zone";
      pts.forEach((x, i) => {
        carte.repere("p" + i, x[0], x[1], { couleur: "#2a7de1", etiquette: String(i + 1) });
        if (zone && i > 0) carte.ligne("l" + i, pts[i - 1], x);
      });
      if (zone && pts.length > 2) carte.ligne("fin", pts[pts.length - 1], pts[0]);
      document.getElementById("e-compte").textContent = pts.length + (zone ? " sommet(s) (3 à 100)" : " lieu(x) (1 à 200)");
      document.getElementById("e-nombre-l").hidden = !zone;
    }
    modeSel.onchange = () => { pts.length = 0; maj(); };
    document.getElementById("e-annuler").onclick = () => { pts.pop(); maj(); };
    document.getElementById("e-vider").onclick = () => { pts.length = 0; maj(); };
    maj();
    const m = document.getElementById("message"), ok = document.getElementById("e-ok");
    document.getElementById("e-creer").onclick = async (ev) => {
      const b = ev.target; m.hidden = ok.hidden = true; b.disabled = true; b.textContent = "Vérification en cours…";
      const corps = { nom: document.getElementById("e-nom").value, description: document.getElementById("e-desc").value, mode: modeSel.value };
      if (modeSel.value === "zone") { corps.zone = pts; corps.nombre = Number(document.getElementById("e-nombre").value); } else corps.points = pts;
      try {
        const r = await api("/api/admin/cartes", corps);
        cartes = (await api("/api/cartes")).cartes;
        ok.textContent = "Carte « " + r.nom + " » créée avec " + r.retenus + " lieux."; ok.hidden = false;
      } catch (err) { m.textContent = err.message; m.hidden = false; }
      b.disabled = false; b.textContent = "Créer la carte";
    };
    app.querySelectorAll(".archiver").forEach((b) => { b.onclick = async () => {
      try { await api("/api/admin/cartes/" + encodeURIComponent(b.dataset.id), "SUPPRIMER"); cartes = (await api("/api/cartes")).cartes; await pageEditeur(); }
      catch (err) { m.textContent = err.message; m.hidden = false; }
    }; });
  }

  // ---------------------------------------------------------------- démarrage
  async function route() {
    const q = new URLSearchParams(location.search);
    try {
      if (q.get("partie")) await partie(q.get("partie"), q.get("recap") === "1");
      else if (q.get("defi")) await pageDefi(q.get("defi"));
      else if (q.get("profil")) await pageProfil();
      else if (q.get("classements")) await pageClassements(q.get("carte"));
      else if (q.get("editeur")) await pageEditeur();
      else await accueil();
    } catch (e) { erreurFatale(e); }
  }

  window.addEventListener("popstate", route);
  (async function init() {
    try {
      config = await api("/api/config");
      moi = await api("/api/moi");
      cartes = (await api("/api/cartes")).cartes;
    } catch (e) { return erreurFatale(e); }
    route();
  })();
})();
