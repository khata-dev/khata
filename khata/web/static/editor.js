/* khata rich-note editor — EasyMDE wrapper with paste/drop image upload. */
(function () {
  "use strict";

  function uploadImage(uploadUrl, file, onSuccess, onError) {
    const fd = new FormData();
    fd.append("file", file);
    fetch(uploadUrl, { method: "POST", body: fd })
      .then(async (r) => {
        if (!r.ok) throw new Error(`Upload failed: ${r.status}`);
        return r.json();
      })
      .then((j) => onSuccess((j && j.url) || (j && j.data && j.data.filePath)))
      .catch((e) => onError(String(e)));
  }

  function wire(textarea) {
    if (textarea.dataset.khataMounted) return;
    textarea.dataset.khataMounted = "1";

    const uploadUrl = textarea.dataset.upload;

    const easy = new EasyMDE({
      element: textarea,
      autoDownloadFontAwesome: false,
      spellChecker: false,
      status: ["lines", "words"],
      minHeight: "160px",
      uploadImage: !!uploadUrl,
      imageUploadFunction: uploadUrl
        ? (file, onSuccess, onError) => uploadImage(uploadUrl, file, onSuccess, onError)
        : undefined,
      imagePathAbsolute: true,
      toolbar: [
        "bold", "italic", "heading", "|",
        "quote", "unordered-list", "ordered-list", "|",
        "link", "image", "code", "|",
        "preview", "side-by-side", "|",
        "guide",
      ],
      previewRender: (text) => {
        // Use marked if available — otherwise EasyMDE's default. marked ships
        // inside EasyMDE.
        return easy.markdown(text);
      },
    });

    // Keep the native textarea's value in sync so HTMX form submission works.
    easy.codemirror.on("change", () => easy.codemirror.save());

    // Keep a handle so form submit can flush before send.
    window._khataEasyMDE = easy;

    // HTMX replaces #note-block after POST → the old CodeMirror DOM gets
    // unmounted. On htmx:afterSwap, re-wire whatever landed.
    document.body.addEventListener("htmx:afterSwap", (ev) => {
      if (ev.target && ev.target.id === "note-block") {
        const t = document.querySelector("#note-block textarea.khata-editor");
        if (t) {
          delete t.dataset.khataMounted;
          wire(t);
        }
      }
    });
  }

  function init() {
    if (typeof EasyMDE === "undefined") return;
    document.querySelectorAll("textarea.khata-editor").forEach(wire);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
