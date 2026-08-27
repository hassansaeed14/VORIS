# Model and Backend Licences

Every weight file and binary the media generation subsystem touches, with its
licence and the URL that licence was read from.

VORIS is heading toward a source-available commercial licence. Anything
copyleft or non-commercial in this table would be a commercial blocker, so the
selection below is constrained rather than chosen on quality alone.

Verified 26 Aug 2026.

---

## Generation backend

| Component | Licence | Source | How it is used |
|---|---|---|---|
| **leejet/stable-diffusion.cpp** | **MIT** | https://github.com/leejet/stable-diffusion.cpp/blob/master/LICENSE | Compiled binary, invoked as a **subprocess** |

The subprocess boundary is deliberate. It is the same aggregation boundary used
for Piper TTS: the binary is a separate program reached over a process
boundary, not linked into the Python process. MIT would not have required this,
but keeping the boundary uniform means the rule holds if a backend is ever
swapped for a copyleft one.

### Explicitly rejected

| Rejected | Licence | Why |
|---|---|---|
| ComfyUI | GPL-3.0 | Copyleft. Not imported, not vendored, not run. |
| AUTOMATIC1111 / stable-diffusion-webui | AGPL-3.0 | Copyleft, and the network clause is worse for a hosted product. |

Neither appears anywhere in this repository.

---

## Image weights — FLUX.1-schnell

All four files are Apache-2.0.

| File | Licence | Repository | Approx size |
|---|---|---|---|
| `flux1-schnell-Q4_K.gguf` | Apache-2.0 | https://huggingface.co/city96/FLUX.1-schnell-gguf | 6.8 GB |
| `ae.safetensors` (VAE) | Apache-2.0 | https://huggingface.co/black-forest-labs/FLUX.1-schnell | 335 MB |
| `clip_l.safetensors` | Apache-2.0 | https://huggingface.co/comfyanonymous/flux_text_encoders | 246 MB |
| `t5xxl_fp8_e4m3fn.safetensors` | Apache-2.0 | https://huggingface.co/comfyanonymous/flux_text_encoders | 4.9 GB |

Licence text: https://huggingface.co/black-forest-labs/FLUX.1-schnell/blob/main/LICENSE.md

### The VAE trap

`black-forest-labs/FLUX.1-schnell` and `black-forest-labs/FLUX.1-dev` both ship
a VAE file named exactly **`ae.safetensors`**. They are not interchangeable:

- FLUX.1-**schnell** → Apache-2.0 → commercial use permitted
- FLUX.1-**dev** → FLUX.1 Non-Commercial License → **commercial use prohibited**

Because the filenames match, a `dev` VAE dropped into `models/flux/` would work
perfectly and silently make the output non-commercial. The only reliable check
is provenance, not the file on disk. When fetching, always name the repo
explicitly:

```bash
huggingface-cli download black-forest-labs/FLUX.1-schnell ae.safetensors --local-dir models/flux
```

If you cannot say which repo a local `ae.safetensors` came from, re-download it.

### Why schnell, beyond licensing

FLUX.1-schnell is timestep-distilled to about 4 sampling steps, against roughly
20–50 for dev. On a CPU backend that difference is the whole feasibility
argument, not an optimisation.

---

## Video weights — none

No video model is used. See SYSTEM_AUDIT.md for the hardware reason.

Licence-clean options, held for when the hardware supports them:

| Candidate | Licence | Status |
|---|---|---|
| Wan2.2 | Apache-2.0 | Acceptable, not installed |
| LTX-Video | Apache-2.0 | Acceptable, not installed |

### Rejected

| Rejected | Licence | Why |
|---|---|---|
| HunyuanVideo | NOASSERTION | No clear grant. Unusable commercially without one. |
| LTX-2 | NOASSERTION | Same. Note LTX-**Video** and LTX-**2** differ here — the version matters. |

---

## Adding a model

1. Read the licence at the source and record the URL above.
2. Reject anything copyleft, non-commercial, or `NOASSERTION`.
3. Note any filename that collides with a differently-licensed file, as
   `ae.safetensors` does.
4. Confirm the weights are gitignored. They must never be committed, and must
   not be added to git-lfs either.
