# Hyprland Configuration

**Status:** Verified against Hyprland 0.56.2 on the reference deployment.

## Purpose

Defines the active Hyprland compositor configuration, companion daemons, and
the legacy configuration retained for reference.

## Scope

In scope:

- `hyprland.lua`
- `hypridle.conf`
- `hyprlock.conf`
- `hyprpaper.conf`
- `hyprland.conf.backup` (legacy only)

Out of scope:

- Helper script internals (see
  [hyprland-automation-scripts.md](hyprland-automation-scripts.md)).
- Wallpaper/theme engine internals (see
  [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md)).
- Monitor hardware setup beyond the configured mode and scale.

## Files and paths

| Repository path | Deployed path | Role |
| --- | --- | --- |
| `hypr/.config/hypr/hyprland.lua` | `~/.config/hypr/hyprland.lua` | Active compositor configuration |
| `hypr/.config/hypr/hypridle.conf` | `~/.config/hypr/hypridle.conf` | Idle, sleep, and lid behavior |
| `hypr/.config/hypr/hyprlock.conf` | `~/.config/hypr/hyprlock.conf` | Lock-screen layout and fallback colors |
| `hypr/.config/hypr/hyprpaper.conf` | `~/.config/hypr/hyprpaper.conf` | Fallback wallpaper backend |
| `hypr/.config/hypr/hyprland.conf.backup` | not deployed | Legacy hyprlang configuration |
| `hypr/.config/hypr/scripts/*` | `~/.config/hypr/scripts/*` | Helper scripts |
| `hypr/.config/hypr/themes/wallpapers/` | `~/.config/hypr/themes/wallpapers/` | Wallpaper assets and thumbnail cache |

## Hyprland API and version

The configuration targets Hyprland 0.56.x, which uses the Lua configuration
parser. It uses:

- `hl.monitor`, `hl.env`
- `hl.on("hyprland.start", ...)`, `hl.on("config.reloaded", ...)`
- `hl.config`
- `hl.curve`, `hl.animation`
- `hl.device`, `hl.gesture`
- `hl.bind` with `hl.dsp.exec_cmd`, `hl.dsp.window.*`, `hl.dsp.focus`,
  `hl.dsp.workspace.*`, `hl.dsp.layout`
- `hl.window_rule`

Hyprland 0.56 rejects `hyprctl keyword` for non-legacy parser options. Runtime
border changes must use `hyprctl eval` with `hl.config`, as implemented by the
autotheme engine.

## Monitor and environment

### Monitor

```lua
hl.monitor({
  output   = "",
  mode     = "1920x1080@60",
  position = "auto",
  scale    = 1.5,
})
```

This applies the same mode and scale to every output.

The helper scripts assume:

- Base scale: `1.5`
- Typical usable area: approximately `1276 × 674` logical pixels

### Environment

```lua
hl.env("XCURSOR_SIZE", "21")
hl.env("HYPRCURSOR_SIZE", "21")
hl.env("QT_QPA_PLATFORMTHEME", "gtk3")

hl.env("ELECTRON_OZONE_PLATFORM_HINT", "auto")
hl.env("GDK_BACKEND", "wayland")
hl.env("QT_QPA_PLATFORM", "wayland")
hl.env("MOZ_ENABLE_WAYLAND", "1")
hl.env("ELECTRON_USE_WAYLAND", "1")
hl.env("GDK_BACKEND", "wayland")
hl.env("QT_QPA_PLATFORM", "wayland")
hl.env("MOZ_ENABLE_WAYLAND", "1")
```

`GDK_BACKEND`, `QT_QPA_PLATFORM`, and `MOZ_ENABLE_WAYLAND` are set twice. The
duplication is harmless.

### Autostart

`hl.on("hyprland.start", ...)` launches:

| Command | Purpose |
| --- | --- |
| `battery-notify.sh` | Compile/run the UPower battery notifier |
| `adaptive-font.py` | Adaptive Kitty font/padding daemon |
| `nm-applet` | NetworkManager tray applet |
| `waybar-scale.py start` | Start Waybar with scaled/themed CSS |
| `wallpaper_switch.sh restore` | Restore wallpaper, backend, palette, and themed surfaces |
| `hyprpolkitagent` | PolicyKit agent |
| `blueman-applet` | Bluetooth tray applet |
| `wl-paste --type text --watch cliphist store` | Text clipboard history |
| `wl-paste --type image --watch cliphist store` | Image clipboard history |
| `/usr/bin/hyprpolkitagent` | PolicyKit agent, launched a second time |

The duplicate PolicyKit launch is redundant.

### Config reload hook

```lua
hl.on("config.reloaded", function()
  hl.exec_cmd("~/.config/hypr/scripts/wallpaper_switch.sh borders")
end)
```

A reload applies the static border colors from `hl.config`, then this hook
reapplies the generated accent/border colors.

## Appearance

```lua
hl.config({
  general = {
    gaps_in = 1,
    gaps_out = 1,
    border_size = 1,
    ["col.active_border"] = "rgba(4b9fe8ff)",
    ["col.inactive_border"] = "rgba(010101ff)",
    resize_on_border = true,
    allow_tearing = false,
    layout = "dwindle",
  },
  decoration = {
    rounding = 10,
    rounding_power = 2,
    active_opacity = 1.0,
    inactive_opacity = 1.0,
    shadow = {
      enabled = true,
      range = 4,
      render_power = 3,
      color = "rgba(1a1a1aee)",
    },
    blur = {
      enabled = true,
      size = 6,
      passes = 2,
      vibrancy = 0.1696,
    },
  },
  dwindle = { preserve_split = true },
  master = { new_status = "master" },
  animations = { enabled = true },
  misc = {
    force_default_wallpaper = 0,
    disable_hyprland_logo = true,
  },
  input = {
    kb_layout = "us",
    kb_variant = "",
    kb_model = "",
    kb_options = "",
    kb_rules = "",
    follow_mouse = 1,
    sensitivity = 0,
    touchpad = { natural_scroll = true },
  },
  xwayland = { force_zero_scaling = false },
})
```

The static border colors are fallbacks. The autotheme engine overwrites them at
runtime.

### Animation curves

| Name | Points |
| --- | --- |
| `easeOutQuint` | `0.23,1  0.32,1` |
| `easeInOutCubic` | `0.65,0.05  0.36,1` |
| `linear` | `0,0  1,1` |
| `almostLinear` | `0.5,0.5  0.75,1.0` |
| `quick` | `0.15,0  0.1,1` |

### Animation leaves

| Leaf | Speed | Bezier / style |
| --- | --- | --- |
| global | 10 | default |
| border | 5.39 | easeOutQuint |
| windows | 4.79 | easeOutQuint |
| windowsIn | 4.1 | easeOutQuint, `popin 87%` |
| windowsOut | 1.49 | linear, `popin 87%` |
| fadeIn | 1.73 | almostLinear |
| fadeOut | 1.46 | almostLinear |
| fade | 3.03 | quick |
| layers | 3.81 | easeOutQuint |
| layersIn | 4 | easeOutQuint, fade |
| layersOut | 1 | linear, fade |
| fadeLayersIn | 1.79 | almostLinear |
| fadeLayersOut | 1.39 | almostLinear |
| workspaces | 1.94 | almostLinear, fade |
| workspacesIn | 1.21 | almostLinear, fade |
| workspacesOut | 1.94 | almostLinear, fade |

### Peripherals and gestures

```lua
hl.device({ name = "epic-mouse-v1", sensitivity = -0.5 })
hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })
```

The mouse sensitivity applies only to a device named `epic-mouse-v1`.

## Keybindings

`mainMod = "SUPER"`.

| Key | Action |
| --- | --- |
| `SUPER+Return` | Launch `kitty` |
| `SUPER+Q` | `confirm_close.sh` |
| `SUPER+E` | Launch Thunar |
| `SUPER+R` | `wofi --show drun` |
| `SUPER+T` | Wallpaper picker |
| `SUPER+B` | Browser picker |
| `SUPER+N` | Toggle `hyprsunset -t 3000` |
| `SUPER+Shift+V` | Clipboard history picker |
| `SUPER+M` | Exit Hyprland |
| `SUPER+L` | Power menu |
| `SUPER+=` / `SUPER+Shift+=` | Increase UI scale |
| `SUPER+-` / `SUPER+Shift+-` | Decrease UI scale |
| `SUPER+F` | Toggle floating |
| `SUPER+P` | Toggle pseudo-tiling |
| `SUPER+J` | Toggle split |
| `SUPER+Left` / `SUPER+Right` | Previous/next populated workspace |
| `SUPER+1..0` | Focus workspace 1..10 |
| `SUPER+Shift+1..0` | Move window to workspace 1..10 |
| `SUPER+Tab` | Focus max workspace ID + 1 |
| `SUPER+D` | Compact workspace IDs |
| `ALT+Tab` | Cycle populated workspaces |
| `SUPER+S` | Toggle special workspace `magic` |
| `SUPER+Shift+S` | Move window to `special:magic` |
| `SUPER+mouse_down` / `SUPER+mouse_up` | Workspace `e+1` / `e-1` |
| `SUPER+LMB` | Drag window |
| `SUPER+RMB` | Resize window |
| `Print` | Region screenshot to `~/Pictures` |
| `SUPER+Print` | Active-output screenshot to `~/Pictures` |
| `XF86AudioRaiseVolume` | Raise sink volume |
| `XF86AudioLowerVolume` | Lower sink volume |
| `XF86AudioMute` | Toggle sink mute |
| `XF86AudioMicMute` | Toggle source mute |
| `XF86MonBrightnessUp/Down` | Adjust brightness |
| `XF86AudioNext/Pause/Play/Prev` | Control media |

There is no `SUPER+I` dashboard binding in the active configuration.

## Window rules

```lua
hl.window_rule({
  name = "suppress-maximize",
  match = { class = ".*" },
  suppress_event = "maximize",
})

hl.window_rule({
  name = "apply-something",
  match = { class = "my-window" },
  border_size = 10,
})

hl.window_rule({
  name = "kitty-no-blur",
  match = { class = "^kitty$" },
  no_blur = true,
})
```

- Maximize requests are suppressed for all windows.
- Class `my-window` receives a 10 px border.
- Kitty windows have compositor blur disabled.

## Hypridle

`hypridle.conf`:

```ini
general {
    before_sleep_cmd = hyprlock
    after_sleep_cmd = hyprctl dispatch dpms on
    ignore_dbus_inhibit = false
    lock_cmd = pidof hyprlock || hyprlock
}

listener {
    event = lid_switch
    on-close = hyprlock
    on-open = hyprctl dispatch dpms on
}
```

No idle timers are configured. `hypridle.service` exists in the package but is
disabled on the reference deployment; it is not started by `hyprland.lua`.

## Hyprlock

`hyprlock.conf` defines:

- General grace: 1 second; cursor hidden; fades enabled; empty input ignored.
- Background: current screenshot with 2 blur passes, blur size 6, brightness
  0.65, contrast 0.90, vibrancy 0.15, vibrancy_darkness 0.10.
- Clock: 80 px JetBrains Mono, 5000 ms update, top center, y −60.
- Date: 13 px sans-serif, 600000 ms update, top center, y −190.
- Prompt: 10 px, bottom center, y 150.
- Input field: 280×48, bottom center, y 90, radius 10, outline 1, dots 0.22.
- Caps Lock indicator: 10 px, bottom center, y 50, amber.
- Static input colors: white outer/inner, green check, red fail.
- Generated source:

```conf
source = /home/aditya/.cache/autotheme/hyprlock-colors.conf
```

The generated block overrides only `input-field` colors. Label colors remain
static.

## Hyprpaper fallback

`hyprpaper.conf`:

```ini
preload = /home/aditya/dotfiles/hypr/.config/hypr/themes/wallpapers/assets/wallpaper.png

wallpaper {
    monitor = eDP-1
    path = /home/aditya/dotfiles/hypr/.config/hypr/themes/wallpapers/assets/wallpaper.png
    fit_mode = cover
}

splash = false
ipc = on
```

Hyprpaper is used only when `awww` is unavailable or explicitly selected. The
static file preloads only `eDP-1`; the wallpaper script applies the current
wallpaper to every monitor by IPC.

## Legacy configuration

`hyprland.conf.backup` is a pre-Lua hyprlang configuration. It is not loaded.

It contains:

- Everforest border colors.
- `exec-once = waybar` rather than the scaled launcher.
- Old `bind` syntax.
- Removed `system-dashboard` rules and a `SUPER+I` bind.
- Duplicate `SUPER+P` binds.
- `xwayland { force_zero_scaling = true }`.
- Extra `GDK_SCALE`, `QT_WAYLAND_FORCE_DPI`, and `_JAVA_OPTIONS` variables.
- Cliphist and PolicyKit autostart lines.

Do not use this file as the active configuration reference.

## Dependencies

Required:

- `hyprland` 0.56.x
- `hypridle`, `hyprlock`, `hyprpaper`
- `waybar`, `wofi`, `kitty`, `thunar`
- `brightnessctl`, `playerctl`, `wpctl`, `grim`, `slurp`, `hyprshot`,
  `hyprsunset`, `cliphist`, `wl-clipboard`
- `hyprpolkitagent`, `nm-applet`, `blueman-applet`
- `jq`, `python3`, `gcc`, `pkg-config`, GIO development files
- `awww`, `matugen`, `python-pillow` for autotheme

## Reproduction

1. Install packages from
   [installation-and-package-management.md](installation-and-package-management.md).
2. Stow or copy `hypr/.config/hypr` to `~/.config/hypr`.
3. Make scripts executable:
   ```bash
   chmod +x ~/.config/hypr/scripts/*.sh ~/.config/hypr/scripts/*.py
   ```
4. Seed autotheme:
   ```bash
   ~/.config/hypr/scripts/wallpaper_switch.sh init
   ```
5. Start Hyprland 0.56+ with this configuration.
6. Reload and inspect:
   ```bash
   hyprctl reload
   hyprctl configerrors
   hyprctl binds -j | jq '.[] | select(.key=="T")'
   hyprctl getoption general:col.active_border -j
   ```
7. Start `hypridle` separately if idle/lid locking is required.

## Verification

Verified on the reference deployment:

- Hyprland 0.56.2 accepts `hyprland.lua`.
- `hyprctl reload` reports no config errors.
- `SUPER+T` is registered.
- The reload hook reapplies generated border colors.
- `awww` and the Hyprpaper fallback both work.
- Waybar starts through `waybar-scale.py`.

Not verified:

- Hyprlock’s visual input-field override.
- Multi-monitor behavior beyond the single `eDP-1` reference output.
- `hypridle` runtime behavior on the reference deployment.

## Known limitations

- Monitor mode and scale are fixed to `1920x1080@60` and `1.5`.
- `hypridle` is not started by `hyprland.lua`; its service is disabled.
- PolicyKit is launched twice.
- Three environment variables are set twice.
- The night-light bind uses an absolute `/home/aditya` path.
- `hyprpaper.conf` preloads only `eDP-1`.
- `hyprland.conf.backup` and the repository-level `README.md` contain stale
  references.
- Hyprlock’s `source` override is format-validated but not visually confirmed.

## Related documentation

- [hyprland-automation-scripts.md](hyprland-automation-scripts.md)
- [autotheme-and-wallpaper-engine.md](autotheme-and-wallpaper-engine.md)
- [notifications-gtk-and-lock-screen.md](notifications-gtk-and-lock-screen.md)
- [waybar-status-bar.md](waybar-status-bar.md)
