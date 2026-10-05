export function fmtTime(secs = 0) {
  const m = Math.floor(Number(secs) / 60)
  const s = Math.floor(Number(secs) % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

export function buildAudacityScript(slots, epName) {
  const lines = [
    '; ============================================================',
    '; Phil & Jim Dandy Show — Audacity Assembly Macro',
    `; Episode: ${epName}`,
    `; Generated: ${new Date().toLocaleString()}`,
    '; ============================================================',
    '',
  ]

  slots.forEach((slot, i) => {
    const fname = slot.audio || `[MISSING — ${slot.label}]`
    lines.push(`; --- ${i + 1}. ${slot.label} (${fmtTime(slot.dur)}) ---`)
    lines.push(`Import2:Filename="${fname}"`)
    if (i < slots.length - 1) lines.push('Select:End="End"')
    lines.push('')
  })

  lines.push('; --- Final Export ---')
  lines.push(`Export2:Filename="${epName.replace(/[^a-zA-Z0-9 _-]/g, '_')}.mp3":NumChannels="2":Quality="5"`)
  return lines.join('\n')
}

export function buildSlideManifest(slots, epName) {
  const manifest = {
    episode: epName,
    generated: new Date().toISOString(),
    totalDuration: slots.reduce((t, s) => t + (Number(s.dur) || 0), 0),
    slideSequence: [],
  }

  let cursor = 0
  slots.forEach((slot) => {
    const slides = slot.slides || []
    if (slides.length) {
      const durPerSlide = Math.max(1, Math.floor((Number(slot.dur) || 60) / slides.length))
      slides.forEach((slide, i) => manifest.slideSequence.push({
        startTime: cursor + i * durPerSlide,
        duration: durPerSlide,
        slotLabel: slot.label,
        file: slide.filename || slide.original_name || slide.name || String(slide),
        caption: slide.caption || '',
        type: 'ad_visual',
      }))
    }
    cursor += Number(slot.dur) || 0
  })

  return JSON.stringify(manifest, null, 2)
}

export function buildM3U(slots, epName) {
  const lines = ['#EXTM3U', `#PLAYLIST:${epName}`, '']
  slots.forEach((slot) => {
    lines.push(`#EXTINF:${Number(slot.dur) || 0},${slot.label}`)
    lines.push(slot.audio || `[unassigned — ${slot.label}]`)
  })
  return lines.join('\n')
}

export function downloadText(content, filename, type = 'text/plain') {
  const blob = new Blob([content], { type })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}
