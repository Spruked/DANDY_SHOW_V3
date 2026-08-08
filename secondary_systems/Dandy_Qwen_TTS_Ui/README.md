# Dandy Qwen TTS Package

Local operator package for Qwen TTS.

Modes:
- `CustomVoice`: built-in Qwen speakers such as Ryan, Aiden, Vivian, Eric.
- `VoiceClone`: reference audio cloning and reusable saved voice prompts.
- `VoiceDesign`: natural-language designed voices.

Only run one heavy Qwen model at a time on the RTX 3050.

## Operator UI

Start:

```bat
start_operator_ui.cmd
```

Open:

```text
http://127.0.0.1:7861
```

The operator UI is aimed at quick CustomVoice testing and saves generated files to `generated_audio`.

## Production Bridge

Start:

```bat
start_bridge.cmd
```

Health:

```text
http://127.0.0.1:8020/health
```

Dandy Show synthesis endpoint:

```text
http://127.0.0.1:8020/synthesize
```

The Dandy Show backend calls the bridge, not the Gradio UI directly. The bridge auto-detects the live Qwen Gradio backend and maps Dandy speakers to Qwen speakers from `config/voices.json`.

Long text is chunked before it reaches Qwen. Default chunk size is `220` characters and can be changed with `DANDY_QWEN_MAX_CHUNK_CHARS`.

Bridge limits:
- Text request hard limit: `2048` characters.
- Instruction hard limit: `1600` characters.
- Voice clone reference audio hard limit: `30` seconds.
- Reference audio is validated with `ffprobe` before the bridge calls Qwen.

## Qwen Model UIs

Built-in voices:

```bat
start_custom_voice.cmd
```

```text
http://127.0.0.1:8031
```

Voice cloning:

```bat
start_voice_clone.cmd
```

```text
http://127.0.0.1:8032
```

Voice design:

```bat
start_voice_design.cmd
```

```text
http://127.0.0.1:8033
```

Stop loaded Qwen models:

```bat
stop_qwen_tts_models.cmd
```

## Voice Cloning

Voice cloning is in the `start_voice_clone.cmd` / `http://127.0.0.1:8032` UI.

Use:
- `Clone & Generate` for immediate reference-audio cloning.
- `Save / Load Voice` to create reusable `.pt` voice prompt files.

Recommended:
- Use a clean 3-10 second reference clip.
- Provide the exact transcript when possible.
- Use `x-vector only` only when you do not have the transcript; quality may be lower.

## Paths

Qwen engine:

```text
R:\R_Drive_Substrate\Services\qwen_engine
```

Python venv:

```text
R:\R_Drive_Substrate\Services\qwen_tts_312
```

Generated wrapper audio:

```text
C:\dev\Desktop\platform\dandy_qwen_tts_ui\generated_audio
```

Logs:

```text
C:\dev\Desktop\platform\dandy_qwen_tts_ui\logs
```
