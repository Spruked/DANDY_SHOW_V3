// SlideshowBuilder.jsx — 3-panel deck builder.
// Left: slide list (add/dup/delete/reorder, auto-generate)
// Center: live slide preview + editable fields + style controls
// Right: timing + snap-to-script + export options

import { useEffect, useState, useCallback } from "react";

const EMPTY_SLIDE = () => ({
  id: `slide_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
  title: "",
  subtitle: "",
  body: "",
  background: "",
  overlays: [],
  start: 0,
  end: 10,
  style: {
    fontSize: 48,
    align: "center",
    color: "#ffffff",
    animation: "fade",
  },
});

export default function SlideshowBuilder({ episode, assetSlots }) {
  const [slides, setSlides] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [aspect, setAspect] = useState("16:9");
  const [format, setFormat] = useState("mp4");

  // Load existing slideshow.json for this episode
  useEffect(() => {
    if (!episode?.id) return;
    fetch(`/api/social/slideshow/load?episode_id=${episode.id}`)
      .then((r) => r.json())
      .then((d) => {
        setSlides(d.slides || []);
        setSelectedId(d.slides?.[0]?.id || null);
      });
  }, [episode?.id]);

  const selected = slides.find((s) => s.id === selectedId);

  const updateSelected = useCallback(
    (patch) => {
      setSlides((prev) =>
        prev.map((s) => (s.id === selectedId ? { ...s, ...patch } : s))
      );
      setDirty(true);
    },
    [selectedId]
  );

  const updateSelectedStyle = (patch) => {
    updateSelected({ style: { ...selected.style, ...patch } });
  };

  const addSlide = () => {
    const s = EMPTY_SLIDE();
    setSlides((prev) => [...prev, s]);
    setSelectedId(s.id);
    setDirty(true);
  };

  const duplicateSlide = () => {
    if (!selected) return;
    const copy = { ...selected, id: `slide_${Date.now()}` };
    const idx = slides.findIndex((s) => s.id === selectedId);
    setSlides((prev) => [...prev.slice(0, idx + 1), copy, ...prev.slice(idx + 1)]);
    setSelectedId(copy.id);
    setDirty(true);
  };

  const deleteSlide = () => {
    if (!selected) return;
    setSlides((prev) => prev.filter((s) => s.id !== selectedId));
    setSelectedId(slides[0]?.id || null);
    setDirty(true);
  };

  const moveSlide = (id, dir) => {
    setSlides((prev) => {
      const idx = prev.findIndex((s) => s.id === id);
      const swap = idx + dir;
      if (swap < 0 || swap >= prev.length) return prev;
      const next = [...prev];
      [next[idx], next[swap]] = [next[swap], next[idx]];
      return next;
    });
    setDirty(true);
  };

  const autoGenerateFromScript = async () => {
    const res = await fetch(
      `/api/social/slideshow/auto-generate?episode_id=${episode.id}`,
      { method: "POST" }
    );
    const data = await res.json();
    setSlides(data.slides || []);
    setSelectedId(data.slides?.[0]?.id || null);
    setDirty(true);
  };

  const saveDeck = async () => {
    await fetch("/api/social/slideshow/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ episode_id: episode.id, slides }),
    });
    setDirty(false);
  };

  const renderDeck = async () => {
    setRendering(true);
    try {
      if (dirty) await saveDeck();
      const res = await fetch("/api/social/slideshow/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ episode_id: episode.id, aspect, format }),
      });
      const data = await res.json();
      if (data.download_url) window.open(data.download_url, "_blank");
    } finally {
      setRendering(false);
    }
  };

  return (
    <div className="slideshow-builder">
      {/* LEFT PANEL — slide list */}
      <div className="panel panel-left">
        <div className="panel-header">
          <span>SLIDES ({slides.length})</span>
          <button onClick={addSlide} title="Add slide">+</button>
        </div>

        <div className="slide-list">
          {slides.map((s, i) => (
            <div
              key={s.id}
              className={`slide-list-item ${s.id === selectedId ? "active" : ""}`}
              onClick={() => setSelectedId(s.id)}
            >
              <span className="slide-idx">{String(i + 1).padStart(2, "0")}</span>
              <span className="slide-title">{s.title || "Untitled"}</span>
              <div className="slide-actions">
                <button onClick={(e) => { e.stopPropagation(); moveSlide(s.id, -1); }}>▲</button>
                <button onClick={(e) => { e.stopPropagation(); moveSlide(s.id,  1); }}>▼</button>
              </div>
            </div>
          ))}
        </div>

        <div className="panel-footer">
          <button onClick={duplicateSlide} disabled={!selected}>Duplicate</button>
          <button onClick={deleteSlide} disabled={!selected}>Delete</button>
          <button onClick={autoGenerateFromScript} className="btn-auto">
            Auto-generate from script
          </button>
        </div>
      </div>

      {/* CENTER PANEL — live preview + editor */}
      <div className="panel panel-center">
        {!selected ? (
          <div className="preview-empty">Select or add a slide to begin</div>
        ) : (
          <>
            <div
              className="slide-preview"
              style={{
                aspectRatio: aspect === "9:16" ? "9/16" : aspect === "1:1" ? "1/1" : "16/9",
                backgroundImage: selected.background ? `url(/assets/${selected.background})` : "none",
                backgroundSize: "cover",
                backgroundPosition: "center",
                color: selected.style.color,
                textAlign: selected.style.align,
              }}
            >
              <div className="slide-preview-content" style={{ fontSize: selected.style.fontSize }}>
                <h2>{selected.title || "Title"}</h2>
                {selected.subtitle && <h3>{selected.subtitle}</h3>}
                {selected.body && <p>{selected.body}</p>}
              </div>
            </div>

            <div className="slide-editor">
              <label>Title
                <input value={selected.title} onChange={(e) => updateSelected({ title: e.target.value })} />
              </label>
              <label>Subtitle
                <input value={selected.subtitle} onChange={(e) => updateSelected({ subtitle: e.target.value })} />
              </label>
              <label>Body
                <textarea value={selected.body} onChange={(e) => updateSelected({ body: e.target.value })} />
              </label>
              <label>Background
                <select value={selected.background} onChange={(e) => updateSelected({ background: e.target.value })}>
                  <option value="">— none —</option>
                  {(assetSlots || []).map((a) => (
                    <option key={a.id} value={a.filename}>{a.name}</option>
                  ))}
                </select>
              </label>

              <div className="style-row">
                <label>Font size
                  <input type="number" value={selected.style.fontSize}
                    onChange={(e) => updateSelectedStyle({ fontSize: Number(e.target.value) })} />
                </label>
                <label>Align
                  <select value={selected.style.align}
                    onChange={(e) => updateSelectedStyle({ align: e.target.value })}>
                    <option value="left">Left</option>
                    <option value="center">Center</option>
                    <option value="right">Right</option>
                  </select>
                </label>
                <label>Color
                  <input type="color" value={selected.style.color}
                    onChange={(e) => updateSelectedStyle({ color: e.target.value })} />
                </label>
                <label>Animation
                  <select value={selected.style.animation}
                    onChange={(e) => updateSelectedStyle({ animation: e.target.value })}>
                    <option value="none">None</option>
                    <option value="fade">Fade</option>
                    <option value="slide">Slide</option>
                    <option value="zoom">Zoom</option>
                  </select>
                </label>
              </div>
            </div>
          </>
        )}
      </div>

      {/* RIGHT PANEL — timing + export */}
      <div className="panel panel-right">
        <div className="panel-header">TIMING</div>
        {selected && (
          <>
            <label>Start (s)
              <input type="number" min="0" step="0.1" value={selected.start}
                onChange={(e) => updateSelected({ start: Number(e.target.value) })} />
            </label>
            <label>End (s)
              <input type="number" min="0" step="0.1" value={selected.end}
                onChange={(e) => updateSelected({ end: Number(e.target.value) })} />
            </label>
            <div className="duration-readout">
              Duration: {(selected.end - selected.start).toFixed(1)}s
            </div>

            <button onClick={async () => {
              const res = await fetch(`/api/social/slideshow/snap?episode_id=${episode.id}&slide_id=${selected.id}`, { method: "POST" });
              const data = await res.json();
              if (data.start != null) updateSelected({ start: data.start, end: data.end });
            }}>
              Snap to script
            </button>
          </>
        )}

        <div className="panel-header" style={{ marginTop: 24 }}>EXPORT</div>
        <label>Aspect
          <select value={aspect} onChange={(e) => setAspect(e.target.value)}>
            <option value="16:9">16:9 (Horizontal)</option>
            <option value="1:1">1:1 (Square)</option>
            <option value="9:16">9:16 (Vertical)</option>
          </select>
        </label>
        <label>Format
          <select value={format} onChange={(e) => setFormat(e.target.value)}>
            <option value="mp4">MP4 Video</option>
            <option value="png_sequence">PNG Carousel</option>
          </select>
        </label>

        <div className="export-actions">
          <button onClick={saveDeck} disabled={!dirty}>
            {dirty ? "Save" : "Saved ✓"}
          </button>
          <button className="btn-render" onClick={renderDeck} disabled={rendering || slides.length === 0}>
            {rendering ? "Rendering..." : "⚡ Render"}
          </button>
        </div>
      </div>
    </div>
  );
}
