## ML Brightness — Claude Guidance

This repository is a Home Assistant custom integration designed to learn and apply lighting preferences (brightness + circadian color temperature) with smooth behavior and safety guardrails. It is intended for distribution via HACS as a standalone repository.

## Project goals
- Provide a “set it and forget it” adaptive lighting behavior that learns from manual brightness changes.
- Keep ML lightweight (no heavy dependencies, no external services).
- Prefer robustness over cleverness (resist one-off spikes, avoid oscillation, don’t fight the user).
- Make everything configurable in UI (Config Flow) and safe by default.
- Work even when some inputs are missing (no lux sensor, no TV, etc.).

## High-level behavior
### What it does
- Learns brightness from **manual changes** (default: state context has `user_id`; optional: learn any non-self change).
- Predicts brightness from current context and (optionally) turns on lights on presence.
- Applies smoothing: cooldown after manual change, hysteresis, debounce, max delta per minute, transition time.
- Applies circadian `color_temp` target, then clamps by configured bounds (global + per area + per light).

### What it should not do
- Never rapidly “thrash” lights (avoid frequent toggles or oscillation).
- Never override recent manual intent (cooldown + override button).
- Never require any specific sensor to function (all signals optional).

## Repository layout (HACS)
- Repo root contains:
  - `custom_components/ml_brightness/` (integration code)
  - `hacs.json`, `README.md`, `info.md`
- HACS config:
  - `hacs.json` must stay in repo root.
  - Use `"content_in_root": false` when manifest is under `custom_components/ml_brightness/` (`true` means HACS expects `manifest.json` at repo root only).
  - Integration domain is `ml_brightness`.

## Key files and responsibilities
- `custom_components/ml_brightness/__init__.py`
  - Integration entry setup/unload; forwards platforms.
- `custom_components/ml_brightness/config_flow.py`
  - Initial `ConfigFlow` plus `OptionsFlow` for reconfiguration without reinstall.
  - `DEFAULT_CONFIG` / `entry_cfg()` live in `const.py`; merged view = defaults + `entry.data` + `entry.options`.
- `custom_components/ml_brightness/utils.py`
  - Pure helpers (clamp, time windows, kNN median) importable without loading package `__init__.py` (tests).
- `custom_components/ml_brightness/storage.py`
  - Persists models + `meta` (e.g. history bootstrap done). Debounced `async_schedule_save()` to limit disk I/O.
- `custom_components/ml_brightness/coordinator.py`
  - Owns store, update loop, listens to light changes, calls control logic.
  - Triggers bootstrap on startup (history seed) if store empty.
  - Holds “override until” state for pause button.
- `custom_components/ml_brightness/light_control.py`
  - Context building, model prediction, smoothing, CT circadian clamp, autodiscovery + blacklists.
  - Applies service calls to lights.
- `custom_components/ml_brightness/trainer.py`
  - Learns from manual changes (strong weight) and history bootstrap (weak weight).
  - Writes examples to store; trains per light and per area.
- `custom_components/ml_brightness/storage.py`
  - Persists model state to HA storage (weights + example buffers).
- `custom_components/ml_brightness/bootstrap.py`
  - Pulls recorder history to seed examples when fresh install.
- `custom_components/ml_brightness/button.py`
  - “Override (pause auto)” button to pause automation for N minutes.
- `custom_components/ml_brightness/sensor.py`, `switch.py`
  - Expose recommended brightness, confidence, and enable toggle.

## Configuration philosophy
### Keep knobs meaningful
- Prefer fewer, high-impact settings:
  - cooldown seconds
  - hysteresis (pct)
  - max delta per minute
  - transition seconds (+ night/sleep variants)
  - presence turn-on behavior
  - sleep window + caps
  - context autodiscovery + blacklist (entities + domains)
  - per-area presence mapping
- If a setting is confusing, either remove it or add a short label/description (translations) later.

### Optional inputs
- Integration must run with:
  - no lux sensors
  - no presence sensors (then no presence-based turn-on)
  - no context entities (then model uses time/sun only)
- Feature extraction should gracefully handle missing values.

## ML model guidance
### Current models
- Default: **kNN weighted median** (robust)
  - Stores recent examples; predicts via nearest contexts, uses weighted median.
  - Naturally robust to one-off spikes.
- Optional: **online ridge** (linear)
  - Lightweight online update with robust weighting.

### Area + light modeling
- Maintain both:
  - per-area model (captures “room intent”)
  - per-light model (captures lamp-specific preferences)
- Prediction blends area and light based on confidence/sample counts.

### Training rules
- Manual brightness changes:
  - store example always
  - train both per-light and per-area models
- History bootstrap:
  - weak weight (no manual context), should not overpower real manual learning

### Outlier/spike handling
- Prefer robust statistics:
  - weighted medians
  - downweight extremes by default
- Spikes should only matter if repeated (many similar examples).

## Smoothing and safety rules
- Cooldown after manual change per light.
- Debounce: require predicted target stable for at least 2 cycles before applying.
- Hysteresis: ignore small differences.
- Rate limiting: clamp max delta per minute.
- Transition: use `light.turn_on` with `transition` when possible.
- Night behavior: slower ramps at night.
- Sleep window:
  - cap max brightness
  - extra slow ramp factor

## Presence behavior (per-area)
- Support global presence entities and per-area presence mapping.
- If per-area presence configured:
  - use it for deciding whether to turn on/adjust lights in that area
- Default should be conservative:
  - do not turn on lights that are off unless presence turn-on is enabled.

## Context autodiscovery + blacklist
- If areas selected and autodiscovery enabled:
  - collect entities in those areas as context signals
  - exclude light + sun + internal integration entities
- Blacklist support:
  - explicit entity blacklist
  - domain blacklist (e.g., exclude `vacuum`, `update`, etc.)

## Development workflow
### Local testing
- Use `python -m compileall custom_components/ml_brightness` for syntax sanity.
- Prefer runtime testing in Home Assistant with a small set of lights first.
- Keep update interval reasonable (avoid high-frequency service calls).

### Logging / debug
- Keep logs minimal by default.
- Prefer adding “explainability” via entity attributes or a debug sensor rather than noisy logs.

## Roadmap ideas (keep possible)
- Better UI: multi-step config flow with per-area sections and nicer selectors.
- Explainability sensor: “why did it pick this brightness?”
- Export/import training data.
- Recorder-based “manual-only” heuristic improvements.
- Device capability detection for CT/Kelvin and transition support.

