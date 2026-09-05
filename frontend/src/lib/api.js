// lib/api.js — Dandy Studio API client
// Backend: FastAPI through the active Vite /api proxy

const BASE = '/api'
const jobCache = new Map()

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text || `HTTP ${res.status}`)
  }
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return res.json()
  return res.text()
}

function normalizeDurationToAdBucket(seconds) {
  const value = Number(seconds) || 30
  if (value <= 17) return 15
  if (value <= 25) return 20
  return 30
}

function normalizeAd(ad = {}) {
  const adScript = Array.isArray(ad.script)
    ? ad.script.map((line) => `${String(line.speaker || 'speaker').toUpperCase()}: ${line.text || ''}`).join(' ')
    : (ad.script || '')
  return {
    ...ad,
    voice: ad.voice || ad.announcer_key || ad.announcer || '',
    status: ad.status || 'done',
    script: adScript,
    audio_file: ad.audio_file || ad.audio_path || ad.audio || '',
  }
}

async function ensureJob(episodeId) {
  const cached = jobCache.get(episodeId)
  if (cached) return cached

  let detail = {}
  try {
    detail = await req(`/episodes/${encodeURIComponent(episodeId)}`)
  } catch {
    detail = {}
  }

  const config = detail.config || {}
  const title = config.title || detail.title || episodeId
  const topic = (config.topic || detail.topic || title || episodeId).trim()
  const payload = {
    episode_id: episodeId,
    title,
    topic: topic || title || episodeId,
    description: config.description || '',
    key_points: Array.isArray(config.key_points) ? config.key_points : [],
    target_duration: Number(config.target_duration) || 2400,
    intensity: config.intensity || 'medium',
    generation_mode: config.generation_mode || 'ai_generate',
  }
  if (config.target_word_count) payload.target_word_count = Number(config.target_word_count)

  const created = await req('/episodes/create', { method: 'POST', body: JSON.stringify(payload) })
  if (!created?.job_id) throw new Error('Could not create generation job')
  jobCache.set(episodeId, created.job_id)
  return created.job_id
}

async function normalizeEditPayload(body) {
  const action = body.action || body.edit_type
  const episodeId = body.episode_id

  if (action === 'modify_line') {
    return {
      episode_id: episodeId,
      edit_type: 'modify_line',
      line_index: body.line_index,
      new_content: {
        speaker: String(body.speaker || 'phil').toLowerCase(),
        text: body.text || '',
        emotion: body.emotion || 'neutral',
        pause_after: typeof body.pause_after === 'number' ? body.pause_after : 0.5,
      },
    }
  }

  if (action === 'add_line') {
    const insertIndex =
      typeof body.after_index === 'number'
        ? body.after_index + 1
        : (typeof body.line_index === 'number' ? body.line_index : undefined)
    return {
      episode_id: episodeId,
      edit_type: 'add_line',
      line_index: insertIndex,
      new_content: {
        speaker: String(body.speaker || 'phil').toLowerCase(),
        text: body.text || '',
        emotion: body.emotion || 'neutral',
        pause_after: typeof body.pause_after === 'number' ? body.pause_after : 0.5,
      },
    }
  }

  if (action === 'delete_line' || action === 'remove_line') {
    return {
      episode_id: episodeId,
      edit_type: 'remove_line',
      line_index: body.line_index,
    }
  }

  if (action === 'move_line') {
    const scriptData = await req(`/episodes/${encodeURIComponent(episodeId)}/script`)
    const lines = scriptData?.script || []
    const from = Number(body.line_index)
    const to = body.direction === 'down' ? from + 1 : from - 1
    if (!Number.isInteger(from) || from < 0 || from >= lines.length || to < 0 || to >= lines.length) {
      throw new Error('Invalid line move')
    }
    const order = Array.from({ length: lines.length }, (_, idx) => idx)
    const [moved] = order.splice(from, 1)
    order.splice(to, 0, moved)
    return {
      episode_id: episodeId,
      edit_type: 'reorder_lines',
      new_order: order,
    }
  }

  return body
}

export const api = {
  // ── Health ──────────────────────────────────────────────────────────
  health: () => req('/health'),
  writerStatus: () => req('/writer-status'),
  voices: async () => {
    const data = await req('/voices')
    const voices = [
      ...(Array.isArray(data?.kokoro) ? data.kokoro.map((v) => ({ ...v, id: v.id || v.voice })) : []),
      ...(Array.isArray(data?.edge) ? data.edge.map((v) => ({ ...v, id: v.id || v.voice })) : []),
    ]
    return { voices, raw: data }
  },

  // ── Episodes ─────────────────────────────────────────────────────────
  listEpisodes: () => req('/episodes'),
  createEpisode: async (body) => {
    const episodeId = String(body.episode_id || `ep_${Date.now()}`).trim()
    const title = String(body.title || episodeId).trim()
    const topic = String(body.topic || title || episodeId).trim()
    const payload = {
      ...body,
      episode_id: episodeId,
      title,
      topic: topic || title || episodeId,
      key_points: Array.isArray(body.key_points) ? body.key_points : [],
      target_duration: Number(body.target_duration) || 2400,
      intensity: body.intensity || 'medium',
      generation_mode: body.generation_mode || 'ai_generate',
    }
    const created = await req('/episodes/create', { method: 'POST', body: JSON.stringify(payload) })
    if (created?.job_id) jobCache.set(episodeId, created.job_id)
    return created
  },
  getEpisode: (id) => req(`/episodes/${encodeURIComponent(id)}`),
  updateEpisodeConfig: (id, body) =>
    req(`/episodes/${encodeURIComponent(id)}/config`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  // ── Script ───────────────────────────────────────────────────────────
  getScript: (id) => req(`/episodes/${encodeURIComponent(id)}/script`),
  generateScript: async (id, body = {}) => {
    const jobId = await ensureJob(id)
    return req(`/episodes/generate-script?job_id=${encodeURIComponent(jobId)}`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
  cancelEpisodeJob: async (id) => {
    let jobId = jobCache.get(id)
    if (!jobId) {
      const detail = await req(`/episodes/${encodeURIComponent(id)}`).catch(() => ({}))
      jobId = detail.job_id
    }
    if (!jobId) throw new Error('No active job found for this episode')
    return req(`/episodes/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' })
  },
  editScript: async (body) => {
    const normalized = await normalizeEditPayload(body)
    return req('/episodes/edit-script', { method: 'POST', body: JSON.stringify(normalized) })
  },
  exportEpisode: (id, fmt) => req(`/episodes/${encodeURIComponent(id)}/export?format=${encodeURIComponent(fmt)}`),

  // ── Versions ─────────────────────────────────────────────────────────
  getVersions: (id) => req(`/episodes/${encodeURIComponent(id)}/script-versions`),
  rollback: (id, version) => req(`/episodes/${encodeURIComponent(id)}/rollback?version=${encodeURIComponent(version)}`, { method: 'POST' }),

  // ── Production ───────────────────────────────────────────────────────
  produce: async (id, body = {}) => {
    const jobId = await ensureJob(id)
    return req(`/episodes/produce?job_id=${encodeURIComponent(jobId)}`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
  produceStatus: () => Promise.resolve({ status: 'not_supported' }),

  // ── Assets ───────────────────────────────────────────────────────────
  listAssets: (id) => req(`/episodes/${encodeURIComponent(id)}/assets`),
  uploadAsset: (id, formData) =>
    fetch(`${BASE}/episodes/${encodeURIComponent(id)}/assets`, { method: 'POST', body: formData }).then((r) => r.json()),
  assetUrl: (id, assetId) => `${BASE}/episodes/${encodeURIComponent(id)}/assets/${encodeURIComponent(assetId)}/file`,

  // ── Media cues ───────────────────────────────────────────────────────
  addMediaCue: (id, body) =>
    req(`/episodes/${encodeURIComponent(id)}/media-cues`, {
      method: 'POST',
      body: JSON.stringify({
        asset_id: body.asset_id,
        line_number: body.line_number ?? body.line_index,
        start_seconds: body.start_seconds ?? null,
        end_seconds: body.end_seconds ?? null,
        display_label: body.display_label || body.cue_type || '',
        notes: body.notes || body.note || '',
      }),
    }),

  // ── Feedback ─────────────────────────────────────────────────────────
  submitFeedback: (id, text) =>
    req(`/episodes/${encodeURIComponent(id)}/customer-feedback`, { method: 'POST', body: JSON.stringify({ feedback: text }) }),

  // ── Ads ──────────────────────────────────────────────────────────────
  listAds: async (id) => {
    const data = await req(`/episodes/${encodeURIComponent(id)}/ads`)
    const ads = Array.isArray(data) ? data : (data.ads || [])
    return ads.map(normalizeAd)
  },
  generateAd: async (id, body) => {
    const payload = {
      sponsor: body.product || 'Dandy Studio',
      product: body.product || '',
      offer: body.tagline || '',
      cta: body.cta || 'Visit the link in the show notes.',
      duration_seconds: normalizeDurationToAdBucket(body.duration_seconds),
      tone: body.tone || 'confident',
      label: body.ad_type || 'custom',
      announcer_key: body.voice === 'INTRO_FEMALE' ? 'announcer_female' : (body.voice ? 'announcer_male' : null),
      insert_into_script: false,
    }
    const data = await req(`/episodes/${encodeURIComponent(id)}/ads`, { method: 'POST', body: JSON.stringify(payload) })
    return normalizeAd(data.ad || data)
  },
  adPresets: async () => {
    try {
      const data = await req('/ads/presets')
      const presets = Array.isArray(data) ? data : (data.presets || [])
      return presets
    } catch {
      const data = await req('/ads/catalog')
      const entries = Object.entries(data.ads || {})
      return entries.map(([preset_id, value]) => ({ preset_id, ...value }))
    }
  },
  adAudioUrl: (id, adId) => `${BASE}/episodes/${encodeURIComponent(id)}/ads/${encodeURIComponent(adId)}/audio`,
  produceAd: async (epId, adId) => {
    const data = await req(`/episodes/${encodeURIComponent(epId)}/ads/${encodeURIComponent(adId)}/produce`, { method: 'POST' })
    return normalizeAd(data.ad || data)
  },
  insertAd: async (epId, adId, lineIndex) => {
    return req(`/episodes/${encodeURIComponent(epId)}/ads/${encodeURIComponent(adId)}/insert`, {
      method: 'POST',
      body: JSON.stringify({ line_index: lineIndex }),
    })
  },
  listAdAssets: async (epId, adId) => {
    const data = await req(`/episodes/${encodeURIComponent(epId)}/ads/${encodeURIComponent(adId)}/assets`)
    return data.assets || []
  },
  uploadAdAsset: async (epId, adId, file, label = '') => {
    const form = new FormData()
    form.append('file', file)
    form.append('label', label)
    const res = await fetch(`${BASE}/episodes/${encodeURIComponent(epId)}/ads/${encodeURIComponent(adId)}/assets`, {
      method: 'POST', body: form,
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  },
  adAssetFileUrl: (epId, adId, assetId) =>
    `${BASE}/episodes/${encodeURIComponent(epId)}/ads/${encodeURIComponent(adId)}/assets/${encodeURIComponent(assetId)}/file`,

  // ── Social ───────────────────────────────────────────────────────────
  socialPresets: async () => {
    const data = await req('/social/presets')
    return Array.isArray(data) ? data : (data.presets || [])
  },
  generateSocial: (body) =>
    req('/social/generate', { method: 'POST', body: JSON.stringify(body) }),
  listSocialExports: (id) => req(`/episodes/${encodeURIComponent(id)}/social`),
  socialDownloadUrl: (exportId) => `${BASE}/social/${encodeURIComponent(exportId)}/download`,

  // ── Audio ────────────────────────────────────────────────────────────
  audioUrl: (id) => `${BASE}/audio/${encodeURIComponent(id)}/final.mp3`,

  // ── Intro/Outro config ───────────────────────────────────────────────
  getIntroOutroConfig: () => req('/intro-outro-config'),
  saveIntroOutroConfig: (body) =>
    req('/intro-outro-config', { method: 'POST', body: JSON.stringify(body) }),
  previewIntroOutro: async (section, topic = '') => {
    const res = await fetch(`${BASE}/intro-outro-preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ section, topic }),
    })
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText)
      throw new Error(text || `HTTP ${res.status}`)
    }
    const blob = await res.blob()
    return URL.createObjectURL(blob)
  },
}

// ── Helpers ─────────────────────────────────────────────────────────────────
// ~160 words per minute average speech
export function wordsToSeconds(text = '') {
  const words = text.trim().split(/\s+/).filter(Boolean).length
  return Math.round((words / 160) * 60)
}

export function secondsToDisplay(sec) {
  const m = Math.floor(sec / 60)
  const s = String(Math.floor(sec % 60)).padStart(2, '0')
  return `${m}:${s}`
}
