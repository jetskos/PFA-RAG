/* Téléchargement de fichiers fiable en PWA / mobile.
 *
 * Problème résolu : un <a href> vers une URL d'export fait une navigation.
 * Dans une PWA installée (ou un raccourci d'écran d'accueil), le navigateur
 * sort alors du contexte de l'app, et le téléchargement échoue souvent.
 *
 * Ici on récupère le fichier en Blob (aucune navigation), puis :
 *   - mobile en contexte sécurisé : feuille de partage native (navigator.share)
 *     → « Enregistrer dans Fichiers », Drive, WhatsApp… sans quitter l'app ;
 *   - sinon : <a download> sur le Blob (garanti sans navigation).
 *
 * Ce helper ne fait JAMAIS de window.location = … (ce serait la cause du
 * « ça bascule sur le navigateur »). En dernier recours il affiche un message.
 *
 * Usage :
 *   - <a href="…" data-download>  (nom de fichier lu dans Content-Disposition)
 *   - window.appDownloadBlob(blob, "fichier.xlsx")  (fichiers générés côté client)
 */
(function () {
  "use strict";

  function isTouch() {
    try { return window.matchMedia("(pointer: coarse)").matches; }
    catch (e) { return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || ""); }
  }

  // PWA installée (écran d'accueil) : le <a download> y est inerte sous Android
  // et la page se contente de « sortir » vers rien. Il FAUT la feuille de partage.
  function isStandalone() {
    try {
      return window.matchMedia("(display-mode: standalone)").matches
        || window.matchMedia("(display-mode: fullscreen)").matches
        || window.matchMedia("(display-mode: minimal-ui)").matches
        || window.navigator.standalone === true;
    } catch (e) { return false; }
  }

  function toast(msg, isError) {
    try {
      var t = document.createElement("div");
      t.textContent = msg;
      t.setAttribute("role", "status");
      t.style.cssText =
        "position:fixed;left:50%;bottom:calc(72px + env(safe-area-inset-bottom,0px));" +
        "transform:translateX(-50%);z-index:99999;max-width:90vw;" +
        "padding:10px 16px;border-radius:10px;font:600 13px/1.4 system-ui,sans-serif;" +
        "color:#fff;background:" + (isError ? "#b5372a" : "#0d9488") + ";" +
        "box-shadow:0 8px 24px rgba(0,0,0,.35);text-align:center;";
      document.body.appendChild(t);
      setTimeout(function () { t.style.transition = "opacity .3s"; t.style.opacity = "0"; }, 2600);
      setTimeout(function () { try { document.body.removeChild(t); } catch (e) {} }, 3000);
    } catch (e) {}
  }

  function saveViaAnchor(blobOrUrl, filename) {
    var isBlob = (typeof blobOrUrl !== "string");
    var url = isBlob ? URL.createObjectURL(blobOrUrl) : blobOrUrl;
    var a = document.createElement("a");
    a.href = url;
    a.download = filename || "export";
    a.rel = "noopener";
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    setTimeout(function () {
      try { document.body.removeChild(a); } catch (e) {}
      if (isBlob) URL.revokeObjectURL(url);
    }, 1500);
  }

  function saveBlob(blob, filename, sourceUrl) {
    filename = filename || "export";

    if (window.navigator && window.navigator.msSaveOrOpenBlob) {
      window.navigator.msSaveOrOpenBlob(blob, filename);
      return Promise.resolve();
    }

    var file = null;
    try { file = new File([blob], filename, { type: blob.type || "application/octet-stream" }); }
    catch (e) { file = null; }

    // `canShare` est un indice, pas une garantie : certains Chrome Android le
    // renvoient à false alors que le partage de fichier marche. On tente donc
    // dès qu'on a un File + navigator.share, et le catch gère l'échec réel.
    var shareable = false;
    try {
      shareable = !!(file && isTouch() && navigator.share &&
        (!navigator.canShare || navigator.canShare({ files: [file] })));
    } catch (e) { shareable = !!(file && isTouch() && navigator.share); }

    if (shareable) {
      return navigator.share({ files: [file], title: filename }).catch(function (err) {
        if (err && err.name === "AbortError") return;   // l'utilisateur a fermé la feuille
        saveViaAnchor(blob, filename);                   // TWA / navigateur : téléchargement direct
      });
    }

    // `<a download>` sur un Blob : marche sur desktop ET dans une app Android
    // empaquetée (TWA) — la TWA passe le téléchargement au gestionnaire Android.
    saveViaAnchor(blob, filename);
    return Promise.resolve();
  }

  // Repli quand un fetch d'export échoue en contexte standalone : rouvrir
  // l'URL dans le navigateur système, qui sait toujours télécharger.
  function _openInBrowser(sourceUrl) {
    if (sourceUrl) {
      try { window.open(sourceUrl, "_blank", "noopener"); return Promise.resolve(); }
      catch (e) {}
    }
    toast("Téléchargement impossible. Réessaie ou ouvre dans Chrome.", true);
    return Promise.resolve();
  }

  function filenameFromResponse(res, fallback) {
    var cd = res.headers.get("Content-Disposition") || "";
    var m = cd.match(/filename\*=(?:UTF-8'')?["']?([^"';]+)/i) || cd.match(/filename=["']?([^"';]+)/i);
    if (m) { try { return decodeURIComponent(m[1]); } catch (e) { return m[1]; } }
    return fallback || "export";
  }

  window.appDownloadBlob = saveBlob;

  window.appDownload = function (url, filename, triggerEl) {
    var restore = null;
    if (triggerEl) {
      var prevBusy = triggerEl.getAttribute("aria-busy");
      triggerEl.setAttribute("aria-busy", "true");
      triggerEl.style.opacity = "0.55";
      triggerEl.style.pointerEvents = "none";
      restore = function () {
        triggerEl.style.opacity = "";
        triggerEl.style.pointerEvents = "";
        if (prevBusy === null) triggerEl.removeAttribute("aria-busy");
        else triggerEl.setAttribute("aria-busy", prevBusy);
      };
    }
    return fetch(url, { credentials: "same-origin" })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        var name = filename || filenameFromResponse(res);
        // `url` est passé en 3e arg : repli PWA = rouvrir cette URL dans Chrome.
        return res.blob().then(function (blob) { return saveBlob(blob, name, url); });
      })
      .catch(function (err) {
        // Le fetch a échoué : <a download> direct sur l'URL même origine
        // (marche desktop + TWA) ; en dernier recours, ouvrir dans le navigateur.
        try { saveViaAnchor(url, filename || "export"); }
        catch (e) { return _openInBrowser(url); }
        toast("Export impossible (" + (err && err.message ? err.message : "erreur") + ")", true);
      })
      .finally(function () { if (restore) restore(); });
  };

  document.addEventListener("click", function (e) {
    var a = e.target.closest ? e.target.closest("a[data-download]") : null;
    if (!a) return;
    // En app installée / TWA : laisser le navigateur suivre le lien. La réponse
    // porte `Content-Disposition: attachment`, donc la TWA la remet au
    // gestionnaire de téléchargement Android — c'est le chemin le plus fiable.
    // Ailleurs (desktop, onglet mobile) : fetch -> Blob -> pas de flash d'onglet.
    if (isStandalone()) return;
    e.preventDefault();
    window.appDownload(a.href, a.getAttribute("data-filename") || "", a);
  });
})();
