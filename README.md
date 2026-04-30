## ML Brightness (Home Assistant custom integration)

Learns brightness you set manually and applies it later based on context (time/sun, presence, lux, other device states). Smooth changes to avoid sudden jumps. Color temperature follows a circadian target and is clamped by per-room/per-light min/max.

### Features
- Online learning from **manual brightness changes** (per light).
- Context inputs (all optional): time-of-day (cyclic), sun elevation, presence entities, lux entities, other context entities.
- Robust model option: **kNN weighted median** (default) to resist one-off spikes.
- Smooth control: cooldown after manual change, hysteresis, debounce, max delta per minute, optional transition.
- Color temperature: circadian `color_temp` target, clamped by configured min/max (global + per area + per light).
- Safety: optional “do not turn on lights that are off”.

### Install (HACS)
1. Add this repository as a **custom repository** in HACS (category: Integration).\n+2. Install **ML Brightness**.\n+3. Restart Home Assistant.\n+4. Add integration: **Settings → Devices & services → Add integration → ML Brightness**.

### Install (manual)
- Copy `custom_components/ml_brightness/` into your Home Assistant `config/custom_components/ml_brightness/`.\n+- Restart Home Assistant.\n+- Add integration: **Settings → Devices & services → Add integration → ML Brightness**.

### Configure
- Select target areas and/or lights.\n+- (Optional) select presence sensors, lux sensors, and other context entities.\n+- Tune smoothing and CT bounds.

