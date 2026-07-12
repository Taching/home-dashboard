# Training a responsive "Hey Chili" wake word

The dashboard voice worker uses [openWakeWord](https://github.com/dscripka/openWakeWord) locally. **Hey Jarvis** ships as an official pre-trained model (large negative dataset, tuned thresholds). **Hey Chili** is custom — responsiveness depends entirely on how well that `.tflite` file was trained.

If Jarvis feels snappy but Chili does not, the fix is a **better `hey_chee_lee.tflite`**, not more threshold tuning alone.

## Recommended: Google Colab (~1 hour)

This is the same flow Home Assistant documents. No ML setup on the Pi.

1. Open the [openWakeWord Colab trainer](https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing).
2. **Runtime → Run all** (or step through cells).
3. When prompted for the wake phrase, use **`hey chee lee`** (lowercase, phonetic spelling of "chili" for clearer TTS).
4. Listen to the synthetic preview clips. Re-run the TTS cell if the phrase sounds wrong.
5. Use the **default sample counts** for a first pass, or increase training samples if Colab offers it (more data → usually better recall).
6. When finished, download **`hey_chee_lee.tflite`** (or similarly named `.tflite`).

### Install on the Pi

Copy the file into the repo and restart the voice worker:

```sh
cp ~/Downloads/hey_chee_lee.tflite ~/Work/home-dashboard/assets/voice/hey_chee_lee.tflite
./deploy/install-wakeword-model.sh ~/Work/home-dashboard/assets/voice/hey_chee_lee.tflite
```

Or manually:

```sh
docker compose -f compose.yaml -f compose.pi.yaml --profile voice up -d --force-recreate voice
```

### Tune threshold after install

Official models often work well at **0.5**. For `hey_chee_lee` in a quiet room, start near **0.30** and raise if you get false wakes:

```env
VOICE_WAKEWORD_THRESHOLD=0.30  # lower = easier to trigger, more false positives
VOICE_WAKEWORD_REARM_SECONDS=0.5
```

## Compare models on the live mic

Download the official Jarvis model for A/B testing:

```sh
docker compose -f compose.yaml -f compose.pi.yaml --profile voice run --rm voice \
  python tools/download_pretrained_wakeword.py hey_jarvis
```

Benchmark scores while you speak (say **Hey Chili** and **Hey Jarvis** separately):

```sh
docker compose -f compose.yaml -f compose.pi.yaml --profile voice run --rm voice \
  python tools/benchmark_wakeword.py \
  /models/hey_chee_lee.tflite /models/hey_jarvis_v0.1.tflite
```

You want **Hey Chili** peaks above your threshold when you say it, and stay low during normal room speech. If Jarvis peaks high but Chili does not, retrain Chili (or add more synthetic samples in Colab).

## Temporary fallback: Hey Jarvis

For debugging only — the worker will listen for **"Hey Jarvis"**, not Chili:

```env
VOICE_WAKEWORD_MODEL=/models/hey_jarvis_v0.1.tflite
VOICE_WAKEWORD_LABEL=Hey Jarvis
VOICE_WAKEWORD_THRESHOLD=0.5
```

Mount the downloaded model in `compose.pi.yaml` or copy it to `assets/voice/` and point `VOICE_WAKEWORD_MODEL` there.

## Why not train on the Pi?

openWakeWord training needs PyTorch, synthetic speech generation, and large negative feature files. The voice Docker image is inference-only (small, fast). Training belongs on Colab or a PC with a GPU.

## Tips for a good Chili model

- Phrase: **`hey chee lee`** — phonetic "chili"; clear pause after "hey".
- Train in a quiet room first; false-positive tuning comes later.
- If it triggers on TV speech, **raise** `VOICE_WAKEWORD_THRESHOLD` slightly (e.g. 0.45–0.55).
- If it misses your voice, **retrain** with more samples before lowering threshold too far.
