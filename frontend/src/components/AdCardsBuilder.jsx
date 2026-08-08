// AdCardsBuilder.jsx — template-driven sponsor/CTA visual cards.
// The Ads tab owns audio; this owns the visual companion.

import { useEffect, useState } from "react";

const CARD_TEMPLATES = [
  { id: "sponsor",     label: "Sponsor Card" },
  { id: "cta",         label: "CTA Card" },
  { id: "product",     label: "Product Teaser" },
  { id: "brought_by",  label: "Brought to you by..." },
  { id: "end_roll",    label: "End-Roll" },
  { id: "qr",          label: "QR Code" },
  { id: "truemark",    label: "TrueMark Mint Promo" },
  { id: "goat",        label: "GOAT Promo" },
  { id: "orb",         label: "ORB Promo" },
];

const EMPTY_CARD = (type = "sponsor") => ({
  id: `adcard_${Date.now()}`,
  type,
  sponsor: "",
  cta: "",
  url: "",
  offer_code: "",
  product_image: "",
  background: "",
  logo: "",
});

export default function AdCardsBuilder({ episode, assetSlots }) {
  const [cards, setCards] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [aspect, setAspect] = useState("1:1");
  const [format, setFormat] = useState("png");
  const [rendering, setRendering] = useState(false);

  useEffect(() => {
    fetch(`/api/social/adcards/load?episode_id=${episode?.id || ""}`)
      .then((r) => r.json())
      .then((d) => {
        setCards(d.cards || []);
        setSelectedId(d.cards?.[0]?.id || null);
      });
  }, [episode?.id]);

  const selected = cards.find((c) => c.id === selectedId);

  const updateSelected = (patch) => {
    setCards((prev) =>
      prev.map((c) => (c.id === selectedId ? { ...c, ...patch } : c))
    );
  };

  const addCard = (type) => {
    const c = EMPTY_CARD(type);
    setCards((prev) => [...prev, c]);
    setSelectedId(c.id);
  };

  const deleteCard = () => {
    setCards((prev) => prev.filter((c) => c.id !== selectedId));
    setSelectedId(null);
  };

  const saveCards = async () => {
    await fetch("/api/social/adcards/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ episode_id: episode?.id, cards }),
    });
  };

  const renderCard = async () => {
    if (!selected) return;
    setRendering(true);
    try {
      await saveCards();
      const res = await fetch("/api/social/adcards/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ card_id: selected.id, aspect, format }),
      });
      const data = await res.json();
      if (data.download_url) window.open(data.download_url, "_blank");
    } finally {
      setRendering(false);
    }
  };

  return (
    <div className="adcards-builder">
      {/* LEFT — template gallery + card list */}
      <div className="panel panel-left">
        <div className="panel-header">TEMPLATES</div>
        <div className="template-gallery">
          {CARD_TEMPLATES.map((t) => (
            <button key={t.id} className="template-tile" onClick={() => addCard(t.id)}>
              {t.label}
            </button>
          ))}
        </div>

        <div className="panel-header" style={{ marginTop: 16 }}>
          CARDS ({cards.length})
        </div>
        <div className="card-list">
          {cards.map((c) => (
            <div
              key={c.id}
              className={`card-list-item ${c.id === selectedId ? "active" : ""}`}
              onClick={() => setSelectedId(c.id)}
            >
              <span className="card-type">{c.type}</span>
              <span className="card-sponsor">{c.sponsor || "(untitled)"}</span>
            </div>
          ))}
        </div>
      </div>

      {/* CENTER — preview + editor */}
      <div className="panel panel-center">
        {!selected ? (
          <div className="preview-empty">
            Pick a template on the left to start a new ad card
          </div>
        ) : (
          <>
            <div
              className="adcard-preview"
              style={{
                aspectRatio: aspect === "9:16" ? "9/16" : aspect === "16:9" ? "16/9" : "1/1",
                backgroundImage: selected.background ? `url(/assets/${selected.background})` : "none",
                backgroundSize: "cover",
              }}
            >
              <div className="adcard-overlay">
                {selected.logo && <img src={`/assets/${selected.logo}`} alt="" className="adcard-logo" />}
                <div className="adcard-sponsor">{selected.sponsor}</div>
                <div className="adcard-cta">{selected.cta}</div>
                {selected.offer_code && <div className="adcard-offer">Code: {selected.offer_code}</div>}
                {selected.url && <div className="adcard-url">{selected.url}</div>}
              </div>
            </div>

            <div className="adcard-editor">
              <label>Sponsor
                <input value={selected.sponsor} onChange={(e) => updateSelected({ sponsor: e.target.value })} />
              </label>
              <label>CTA text
                <input value={selected.cta} onChange={(e) => updateSelected({ cta: e.target.value })} />
              </label>
              <label>URL
                <input value={selected.url} onChange={(e) => updateSelected({ url: e.target.value })} />
              </label>
              <label>Offer code
                <input value={selected.offer_code} onChange={(e) => updateSelected({ offer_code: e.target.value })} />
              </label>
              <label>Background
                <select value={selected.background} onChange={(e) => updateSelected({ background: e.target.value })}>
                  <option value="">— none —</option>
                  {(assetSlots || []).map((a) => (
                    <option key={a.id} value={a.filename}>{a.name}</option>
                  ))}
                </select>
              </label>
              <label>Logo overlay
                <select value={selected.logo} onChange={(e) => updateSelected({ logo: e.target.value })}>
                  <option value="">— none —</option>
                  {(assetSlots || []).map((a) => (
                    <option key={a.id} value={a.filename}>{a.name}</option>
                  ))}
                </select>
              </label>
            </div>
          </>
        )}
      </div>

      {/* RIGHT — export */}
      <div className="panel panel-right">
        <div className="panel-header">EXPORT</div>
        <label>Aspect
          <select value={aspect} onChange={(e) => setAspect(e.target.value)}>
            <option value="1:1">1:1 Square</option>
            <option value="9:16">9:16 Vertical</option>
            <option value="16:9">16:9 Horizontal</option>
          </select>
        </label>
        <label>Format
          <select value={format} onChange={(e) => setFormat(e.target.value)}>
            <option value="png">PNG (static)</option>
            <option value="mp4">MP4 (animated)</option>
          </select>
        </label>

        <div className="export-actions">
          <button onClick={saveCards}>Save</button>
          <button onClick={deleteCard} disabled={!selected}>Delete</button>
          <button className="btn-render" onClick={renderCard} disabled={!selected || rendering}>
            {rendering ? "Rendering..." : "⚡ Render"}
          </button>
        </div>
      </div>
    </div>
  );
}
