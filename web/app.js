/* « Où suis-je ? » — écrans du jeu solo. JavaScript sans framework. */
(function () {
  "use strict";
  const app = document.getElementById("app");
  let config = { images: "factice" };
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
    const options = corps === undefined ? {} :
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) };
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

  // ---------------------------------------------------------------- accueil
  async function accueil() {
    nettoyer();
    const jour = await api("/api/defi-du-jour").catch(() => null);
    app.innerHTML = `
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
          <label>Ton pseudo <input name="pseudo" maxlength="20" placeholder="Invité" value="${esc(pseudoStocke())}"><small>Écris un surnom, pas ton vrai nom.</small></label>
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
      const pseudo = String(f.get("pseudo") || "").trim();
      stockerPseudo(pseudo);
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
      <main class="accueil">
        <h1>${esc(d.nom)}</h1>
        <p class="sous-titre">${d.nb_manches} lieux sur la carte « ${esc(d.carte_nom)} » — ${esc(CONTRAINTES[d.contrainte])} — ${esc(CHRONOS[d.chrono])}.</p>
        <form id="rejoindre" class="reglages">
          <label>Ton pseudo <input name="pseudo" maxlength="20" placeholder="Invité" value="${esc(pseudoStocke())}"><small>Écris un surnom, pas ton vrai nom.</small></label>
          ${d.deja_joue ? '<button type="submit" class="bouton gros" id="jouer">Voir ma partie</button>'
                        : '<button type="submit" class="bouton gros" id="jouer">Jouer ce défi</button>'}
        </form>
        <p id="message" class="erreur" role="alert" hidden></p>
        <section class="encadre">${classementHtml("Classement", d.classement)}</section>
        <p><a href="/">Autres modes de jeu</a></p>
      </main>`;
    document.getElementById("rejoindre").addEventListener("submit", async (e) => {
      e.preventDefault();
      if (d.deja_joue) { aller("/?partie=" + encodeURIComponent(d.deja_joue.partie_id)); return; }
      const pseudo = String(new FormData(e.target).get("pseudo") || "").trim();
      stockerPseudo(pseudo);
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
        try { await api("/api/parties/" + encodeURIComponent(p.id) + "/reveler", {}); await partie(p.id); }
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
        await api("/api/parties/" + encodeURIComponent(p.id) + "/reponse", choix ? { lat: choix.lat, lon: choix.lon } : {});
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
          ${ficheHtml(r.fiche)}
          <p id="message" class="erreur" role="alert" hidden></p>
          <div class="actions">${action}</div>
        </aside>
      </div>`;

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

  // ---------------------------------------------------------------- démarrage
  async function route() {
    const q = new URLSearchParams(location.search);
    try {
      if (q.get("partie")) await partie(q.get("partie"), q.get("recap") === "1");
      else if (q.get("defi")) await pageDefi(q.get("defi"));
      else await accueil();
    } catch (e) { erreurFatale(e); }
  }

  window.addEventListener("popstate", route);
  (async function init() {
    try {
      config = await api("/api/config");
      cartes = (await api("/api/cartes")).cartes;
    } catch (e) { return erreurFatale(e); }
    route();
  })();
})();
