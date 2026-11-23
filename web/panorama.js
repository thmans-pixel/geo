/* Affichage de l'image de rue. Deux fournisseurs :
   - « google » : vrai Street View (clé Google, panorama désigné par son identifiant) ;
   - « factice » : image de remplacement pour essayer le jeu sans rien payer.
   Contraintes : libre / sans_deplacement (pas de flèches ni de clic pour avancer) / fige (rien ne bouge). */
(function () {
  "use strict";
  let chargementGoogle = null;

  function chargerGoogle(cle) {
    if (window.google && window.google.maps) return Promise.resolve();
    if (chargementGoogle) return chargementGoogle;
    chargementGoogle = new Promise((ok, ko) => {
      window.__googleMapsPret = ok;
      const s = document.createElement("script");
      s.src = "https://maps.googleapis.com/maps/api/js?key=" + encodeURIComponent(cle) +
              "&v=weekly&language=fr&callback=__googleMapsPret";
      s.async = true;
      s.onerror = () => { chargementGoogle = null; ko(new Error("Impossible de charger Google Street View.")); };
      document.head.appendChild(s);
    });
    return chargementGoogle;
  }

  /* Monte l'image dans `el`. Renvoie une promesse de { detruire() }. */
  async function monter(el, image, contrainte, config) {
    el.innerHTML = "";
    el.dataset.contrainte = contrainte;
    if (image.type === "factice") {
      const d = document.createElement("div");
      d.className = "pano-factice";
      d.style.background = "linear-gradient(135deg, hsl(" + image.motif + ",55%,35%), hsl(" + ((image.motif + 70) % 360) + ",60%,55%))";
      d.innerHTML = '<div class="pano-factice-texte">Image factice<br><small>mode essai, sans Street View</small></div>';
      if (contrainte === "libre") d.insertAdjacentHTML("beforeend", '<div class="fleches" aria-label="Flèches de déplacement">▲ ▼</div>');
      el.appendChild(d);
      return { detruire() { el.innerHTML = ""; } };
    }
    if (!config.cle_google) throw new Error("Clé Google absente : le jeu n'est pas configuré pour Street View.");
    await chargerGoogle(config.cle_google);
    // Google signale un refus de clé (quota du jour atteint, clé limitée…) par cette fonction globale.
    window.gm_authFailure = function () {
      el.innerHTML = '<div class="pano-factice"><div class="pano-factice-texte">Plus d\'images pour aujourd\'hui, reviens demain.</div></div>';
    };
    const libre = contrainte === "libre", fige = contrainte === "fige";
    const pano = new google.maps.StreetViewPanorama(el, {
      pano: image.pano_id,
      addressControl: false, showRoadLabels: false, fullscreenControl: false, enableCloseButton: false,
      motionTracking: false, motionTrackingControl: false, panControl: !fige, zoomControl: !fige,
      linksControl: libre, clickToGo: libre, scrollwheel: !fige, disableDoubleClickZoom: !libre,
      keyboardShortcuts: libre,
    });
    pano.setVisible(true);
    let verrou = null;
    if (fige) {
      verrou = document.createElement("div");
      verrou.className = "pano-verrou";
      el.parentNode.appendChild(verrou);
    }
    return { detruire() { if (verrou) verrou.remove(); el.innerHTML = ""; } };
  }

  window.Panorama = { monter: monter };
})();
