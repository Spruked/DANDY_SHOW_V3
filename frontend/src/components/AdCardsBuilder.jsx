// AdCardsBuilder.jsx — template-driven sponsor/CTA visual cards.
// The Ads tab owns audio; this owns the visual companion.

import { useEffect, useState } from "react";
import { req } from "../lib/api";

const CARD_TEMPLATES = [
  { id: "sponsor", label: "Sponsor Card" },
  { id: "cta", label: "CTA Card" },
  { id: "product", label: "Product Teaser" },
  { id: "brought_by", label: "Brought to you by..." },
  { id: "end_roll", label: "End-Roll" },
  { id: "qr", label: "QR Code" },
  { id: "truemark", label: "TrueMark Mint Promo" },
  { id: "goat", label: "GOAT Promo" },
  { id: "orb", label: "ORB Promo" },
];

const EMPTY_CARD = (type = "sponsor") => ({
  id: `adcard_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
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
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!episode?.id) {
        setCards([]);
        setSelectedId(null);
        setDirty(false);
        return;
      }
      setLoading(true);
      setError("");
      setNotice("");
      try {
        const data = await req(`/social/adcards/load?episode_id=${encodeURIComponent(episode.id)}`);
        if (cancelled) return;
        const nextCards = data.cards || [];
        setCards(nextCards);
        setSelectedId(nextCards[0]?.id || null);
        setDirty(false);
      } catch (e) {
        if (!cancelled) setError(`Could not load ad cards: ${e.message}`);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [episode?.id]);

  const selected = cards.find((c) => c.id === selectedId);
  const backgroundAsset = (assetSlots || []).find((a) => a.filename === selected?.background);
  const logoAsset = (assetSlots || []).find((a) => a.filename === selected?.logo);

  const flash = (message) => {
    setNotice(message);
    setError("");
  };

  const updateSelected = (patch) => {
    setCards((prev) => prev.map((c) => (c.id === selectedId ? { ...c, ...patch } : c)));
    setDirty(true);
    setNotice("");
  };

  const addCard = (type) => {
    const c = EMPTY_CARD(type);
    setCards((prev) => [...prev, c]);
    setSelectedId(c.id);
    setDirty(true);
    setNotice("");
  };

  const deleteCard = () => {
    if (!selected) return;
    setCards((prev) => {
      const idx = prev.findIndex((c) => c.id === selectedId);
      const next = prev.filter((c) => c.id !== selectedId);
      setSelectedId(next[Math.min(Math.max(idx, 0), next.length - 1)]?.id || null);
      return next;
    });
    setDirty(true);
    setNotice("");
  };

  const saveCards = async ({ quiet = false } = {}) => {
    if (!episode?.id) throw new Error("Select an episode first");
    setSaving(true);
    setError("");
    try {
      await req("/social/adcards/save", {
        method: "POST",
        body: JSON.stringify({ episode_id: episode.id, cards }),
      });
      setDirty(false);
      if (!quiet) flash("Ad cards saved.");
      return true;
    } catch (e) {
      setError(`Save failed: ${e.message}`);
      throw e;
    } finally {
      setSaving(false);
    }
  };

  const renderCard = async () => {
    if (!selected || !episode?.id) return;
    setRendering(true);
    setError("");
    setNotice("");
    try {
      if (dirty) await saveCards({ quiet: true });
      const data = await req("/social/adcards/render", {
        method: "POST",
        body: JSON.stringify({ episode_id: episode.id, card_id: selected.id, aspect, format }),
      });
      if (!data.download_url) throw new Error("Renderer completed without a download URL");
      flash("Ad card rendered.");
      window.open(data.download_url, "_blank", "noopener,noreferrer");
    } catch (e) {
      setError(`Render failed: ${e.message}`);
    } finally {
      setRendering(false);
    }
  };

  return (
    <div className="adcards-builder">
      <div className="panel panel-left">
        <div className="panel-header">TEMPLATES</div>
        <div className="template-gallery">
          {CARD_TEMPLATES.map((t) => (
            <button key={t.id} className="template-tile" onClick={() => addCard(t.id)} disabled={!episode?.id}>
              {t.label}
            </button>
          ))}
        </div>

        <div className="panel-header" style={{ marginTop: 16 }}>
          CARDS ({cards.length})
        </div>
        {loading && <div className="preview-empty">Loading ad cards…</div>}
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

      <div className="panel panel-center">
        {error && <div style={{ color: "var(--red)", marginBottom: 8 }}>{error}</div>}
        {notice && <div style={{ color: "var(--green)", marginBottom: 8 }}>{notice}</div>}
        {!selected ? (
          <div className="preview-empty">Pick a template on the left to start a new ad card</div>
        ) : (
          <>
            <div
              className="adcard-preview"
              style={{
                aspectRatio: aspect === "9:16" ? "9/16" : aspect === "16:9" ? "16/9" : "1/1",
                backgroundImage: backgroundAsset?.preview_url ? `url(${backgroundAsset.preview_url})` : "none",
                backgroundSize: "cover",
              }}
            >
              <div className="adcard-overlay">
                {selected.logo && logoAsset?.preview_url && <img src={logoAsset.preview_url} alt="" className="adcard-logo" />}
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
                    <option key={a.id} value={a.filename} disabled={a.available === false}>{a.name}{a.available === false ? " (missing)" : ""}</option>
                  ))}
                </select>
              </label>
              <label>Logo overlay
                <select value={selected.logo} onChange={(e) => updateSelected({ logo: e.target.value })}>
                  <option value="">— none —</option>
                  {(assetSlots || []).map((a) => (
                    <option key={a.id} value={a.filename} disabled={a.available === false}>{a.name}{a.available === false ? " (missing)" : ""}</option>
                  ))}
                </select>
              </label>
            </div>
          </>
        )}
      </div>

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
          <button onClick={() => saveCards()} disabled={!dirty || saving || !episode?.id}>
            {saving ? "Saving…" : dirty ? "Save" : "Saved ✓"}
          </button>
          <button onClick={deleteCard} disabled={!selected}>Delete</button>
          <button className="btn-render" onClick={renderCard} disabled={!selected || rendering || saving || !episode?.id}>
            {rendering ? "Rendering..." : "⚡ Render"}
          </button>
        </div>
      </div>
    </div>
  );
}
