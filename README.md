## ML Brightness (Home Assistant custom integration)

Learns brightness you set manually and applies it later based on context (time/sun, presence, lux, other device states). Smooth changes to avoid sudden jumps. Color temperature follows a circadian target and is clamped by per-room/per-light min/max.

### Features
- **Models**: kNN weighted median (default, spike-resistant) or online ridge (linear).
- **Per-area + per-light**: area-level examples blended with per-light examples for prediction.
- **Presence**: global presence entities and/or `presence_by_area` map (area id → entity list). Used for feature vector and for optional **turn on when occupied**.
- **Two-stage off on clear** (optional): when presence for a light goes from occupied to clear, **dim** to a low level over `presence_clear_dim_transition_sec`, then **turn off** after `presence_clear_off_after_dim_sec` if still clear (cancels if motion returns). Tuned for flaky sensors / “still sitting still”.
- **Context**: manual entity list plus optional **autodiscover** entities in selected areas; **entity blacklist** and **domain blacklist**; autodiscover skips entities owned by this config entry.
- **Night / sleep**: slower ramps at night; optional sleep window with max brightness cap and extra ramp dampening.
- **Override**: button entity pauses automation for configurable minutes.
- **Learning**: default learns only when a change has a Home Assistant `user_id` on the state context. Optional **learn non-user changes** (any brightness change except those tagged as this integration’s own `light.turn_on` calls).
- **History bootstrap**: on first run with empty models, pulls recent recorder history for tracked lights (capped), then marks done so it does not repeat.
- **Persistence**: model state debounced to reduce disk writes.
- **Capabilities**: skips `brightness` / `color_temp` in service calls when the light does not support them.

### Install (HACS)
1. In HACS: **Integrations** → menu (⋮) → **Custom repositories** → add `https://github.com/druxbar/ML-Brightness` as type **Integration**.
2. Open the new repo entry → **Download** / **Install**.
3. Restart Home Assistant.
4. **Settings → Devices & services → Add integration → ML Brightness**.

**HACS error "No manifest.json" / path shows only `manifest.json`**: `hacs.json` must use `"content_in_root": false` when the manifest lives under `custom_components/<domain>/` (HACS treats `true` as “`manifest.json` at repo root”). Use repository type **Integration**. After a fix on GitHub, remove the custom repo in HACS and add it again (or redownload) so cached metadata refreshes.

### Install (manual)
- Copy `custom_components/ml_brightness/` into your Home Assistant `config/custom_components/ml_brightness/`.
- Restart Home Assistant.
- Add integration: **Settings → Devices & services → Add integration → ML Brightness**.

### Configure
- **Initial setup**: add integration once (single instance).
- **Change settings later**: **Settings → Devices & services → ML Brightness → Configure** (Options flow). Settings are stored on the config entry; no reinstall required.
- **Areas / lights**: select areas and/or explicit lights to control.
- **Presence**: global list and/or JSON-style `presence_by_area` (see examples below).
- **Smoothing**: cooldown, hysteresis, max delta per minute, transition; night and sleep factors.
- **Color temperature**: global min/max mired plus optional per-area / per-light maps.

#### JSON object field examples

These fields use Home Assistant’s object editor. Use **area IDs** (not names). You can find an area ID via **Settings → Areas → select area → URL**.

**`presence_by_area`** (area id → list of presence entities):

```json
{
  "kitchen": ["binary_sensor.kitchen_motion"],
  "living_room": ["binary_sensor.living_room_motion", "binary_sensor.living_room_presence"]
}
```

**`context_blacklist_domains`** (list of domains to ignore during context autodiscovery):

```json
["camera", "vacuum", "update"]
```

**`ct_bounds_by_area`** (area id → bounds in mired):

```json
{
  "bedroom": {"ct_min": 250, "ct_max": 500},
  "office": {"ct_min": 153, "ct_max": 370}
}
```

**`ct_bounds_by_light`** (light entity id → bounds in mired):

```json
{
  "light.bedside_lamp": {"ct_min": 300, "ct_max": 500},
  "light.desk_lamp": {"ct_min": 153, "ct_max": 350}
}
```

### Releases
- Bump `custom_components/ml_brightness/manifest.json` `version` for each user-visible release.
- Optional: tag the same version on GitHub for HACS users who track releases instead of the default branch.

### HACS validation (GitHub settings, not files)
[HACS Action](https://github.com/hacs/action) reads the **GitHub repository** metadata. Set these on [github.com/druxbar/ML-Brightness](https://github.com/druxbar/ML-Brightness) → **Settings → General**:
- **Description** (example): `Home Assistant custom integration: learns manual brightness and applies it from context with circadian color temp and smoothing.`
- **Topics** (add a few, e.g.): `home-assistant`, `homeassistant`, `hass`, `hacs`, `integration`, `brightness`, `lighting`, `machine-learning`

`hacs.json` must only use keys [documented for HACS](https://hacs.xyz/docs/publish/start/#hacsjson) (do not add `domains`; it fails `hacsjson` validation).

### Tests (developers)
```bash
cd "ML Brightness"
pip install -r requirements-test.txt
pytest
```
CI runs on push/PR (`.github/workflows/test.yml`). Tests load `model.py` and `utils.py` via importlib so **no `homeassistant` package** is required on the machine. Full integration tests still need a Home Assistant dev environment.
