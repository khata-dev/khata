/* khata rich-note editor — EasyMDE wrapper with paste/drop image upload. */
(function () {
  "use strict";

  function upload(uploadUrl, file, onSuccess, onError) {
    const fd = new FormData();
    fd.append("file", file);
    fetch(uploadUrl, { method: "POST", body: fd })
      .then(async (r) => {
        if (!r.ok) {
          const txt = await r.text().catch(() => "");
          throw new Error(`upload ${r.status}: ${txt.slice(0, 120)}`);
        }
        return r.json();
      })
      .then((j) => onSuccess((j && j.url) || (j && j.data && j.data.filePath)))
      .catch((e) => onError(String(e)));
  }

  function wire(textarea) {
    if (textarea.dataset.khataMounted) return;
    textarea.dataset.khataMounted = "1";

    const uploadUrl = textarea.dataset.upload;
    const hasUpload = !!uploadUrl;

    const easy = new EasyMDE({
      element: textarea,
      autoDownloadFontAwesome: false,
      spellChecker: false,
      status: ["lines", "words"],
      minHeight: "200px",
      // Enables paste + drag-drop + the 'upload-image' toolbar button.
      uploadImage: hasUpload,
      imageAccept: "image/png, image/jpeg, image/webp, image/gif",
      imageMaxSize: 10 * 1024 * 1024,
      imagePathAbsolute: true,
      imageUploadFunction: hasUpload
        ? (file, onSuccess, onError) => upload(uploadUrl, file, onSuccess, onError)
        : undefined,
      // Toolbar items must use 'upload-image' (not 'image') to trigger the
      // file-picker + imageUploadFunction flow. 'image' only inserts a stub
      // `![alt](url)` line, which was the source of "can't upload" confusion.
      toolbar: [
        "bold", "italic", "heading", "|",
        "quote", "unordered-list", "ordered-list", "|",
        "link", hasUpload ? "upload-image" : "image", "code", "|",
        {
          // Custom preview-toggle button with an explicit title so users can
          // see how to come *back* from preview mode.
          name: "preview",
          action: EasyMDE.togglePreview,
          className: "fa fa-eye no-disable",
          title: "Toggle preview (click again to go back)",
          noDisable: true,
        },
        "side-by-side", "fullscreen", "|",
        "guide",
      ],
      previewRender: (text) => easy.markdown(text),
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
