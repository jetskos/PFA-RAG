/* Téléchargement de fichiers fiable en PWA / mobile.
 *
 * Problème résolu : un <a href> vers une URL d'export fait une navigation.
 * Dans une PWA installée (mode standalone), Android sort alors de l'application
 * pour ouvrir le navigateur, et le téléchargement échoue souvent.
 *
 * Ici on récupère le fichier en Blob (aucune navigation), puis :
 *   - mobile : feuille de partage native si dispo (navigator.share) → l'utilisateur
 *     choisit « Enregistrer dans Fichiers », Drive, WhatsApp… sans quitter l'app ;
 *   - sinon : <a download> sur le Blob (garanti sans navigation).
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

  function saveViaAnchor(blob, filename) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename || "export";
    a.rel = "noopener";
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    setTimeout(function () {
      try { document.body.removeChild(a); } catch (e) {}
      URL.revokeObjectURL(url);
    }, 1500);
  }

  function saveBlob(blob, filename) {
    filename = filename || "export";

    // Anciens Edge / IE
    if (window.navigator && window.navigator.msSaveOrOpenBlob) {
      window.navigator.msSaveOrOpenBlob(blob, filename);
      return Promise.resolve();
    }

    // Mobile : feuille de partage native (reste dans l'app)
    var file = null;
    try { file = new File([blob], filename, { type: blob.type || "application/octet-stream" }); }
    catch (e) { file = null; }

    if (file && isTouch() && navigator.share && navigator.canShare && navigator.canShare({ files: [file] })) {
      return navigator.share({ files: [file], title: filename }).catch(function (err) {
        if (err && err.name === "AbortError") return;   // annulé par l'utilisateur : ne rien faire
        saveViaAnchor(blob, filename);                    // autre erreur : repli
      });
    }

    saveViaAnchor(blob, filename);
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
      var prev = triggerEl.getAttribute("aria-busy");
      triggerEl.setAttribute("aria-busy", "true");
      triggerEl.style.opacity = "0.6";
      triggerEl.style.pointerEvents = "none";
      restore = function () {
        triggerEl.style.opacity = "";
        triggerEl.style.pointerEvents = "";
        if (prev === null) triggerEl.removeAttribute("aria-busy"); else triggerEl.setAttribute("aria-busy", prev);
      };
    }
    return fetch(url, { credentials: "same-origin" })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.blob().then(function (blob) { return saveBlob(blob, filename || filenameFromResponse(res)); });
      })
      .catch(function () {
        // Dernier recours : navigation classique.
        window.location.href = url;
      })
      .finally(function () { if (restore) restore(); });
  };

  document.addEventListener("click", function (e) {
    var a = e.target.closest ? e.target.closest("a[data-download]") : null;
    if (!a) return;
    e.preventDefault();
    window.appDownload(a.href, a.getAttribute("data-filename") || "", a);
  });
})();
