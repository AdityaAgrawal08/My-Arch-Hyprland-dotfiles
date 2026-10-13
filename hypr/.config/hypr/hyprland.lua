---@diagnostic disable: undefined-global

local mainMod = "SUPER"
local terminal = "kitty"
local fileManager = "thunar"
local menu = "wofi --show drun"


------------------
---- MONITORS ----
------------------

hl.monitor({
  output   = "",
  mode     = "1920x1080@60",
  position = "auto",
  scale    = 1.5,
})


------------------
-- ENVIRONMENT ---
------------------

hl.env("XCURSOR_SIZE", "21")
hl.env("HYPRCURSOR_SIZE", "21")
hl.env("QT_QPA_PLATFORMTHEME", "gtk3")

hl.env("GDK_SCALE", "2")
hl.env("QT_WAYLAND_FORCE_DPI", "192")
hl.env("_JAVA_OPTIONS", "-Dsun.java2d.uiScale=2 -Dawt.useSystemAAFontSettings=on -Dswing.aatext=true")
hl.env("ELECTRON_USE_WAYLAND", "1")
hl.env("GDK_BACKEND", "wayland")
hl.env("QT_QPA_PLATFORM", "wayland")
hl.env("MOZ_ENABLE_WAYLAND", "1")


------------------
--- AUTOSTART ----
------------------

hl.on("hyprland.start", function()
  hl.exec_cmd("~/.config/hypr/scripts/battery-notify.sh")
  hl.exec_cmd("nm-applet")
  hl.exec_cmd("waybar")
  hl.exec_cmd("hyprpaper -c ~/.config/hypr/hyprpaper.conf")
  hl.exec_cmd("hyprpolkitagent")
  hl.exec_cmd("blueman-applet")
  hl.exec_cmd("wl-paste --type text --watch cliphist store")
  hl.exec_cmd("wl-paste --type image --watch cliphist store")
  hl.exec_cmd("/usr/bin/hyprpolkitagent")
end)


------------------
-- LOOK & FEEL ---
------------------

hl.config({
  general = {
    gaps_in                 = 1,
    gaps_out                = 1,
    border_size             = 1,

    -- Focused window gets a blue outer edge; inactive stays near-black so
    -- focus is obvious at a glance.
    ["col.active_border"]   = "rgba(4b9fe8ff)",
    ["col.inactive_border"] = "rgba(010101ff)",
    resize_on_border        = true,
    allow_tearing           = false,
    layout                  = "dwindle",
  },

  decoration = {
    rounding         = 10,
    rounding_power   = 2,

    active_opacity   = 1.0,
    inactive_opacity = 1.0,

    shadow           = {
      enabled      = true,
      range        = 4,
      render_power = 3,
      color        = "rgba(1a1a1aee)",
    },

    blur             = {
      enabled  = true,
      size     = 6,
      passes   = 2,
      vibrancy = 0.1696,
    },
  },

  dwindle = {
    preserve_split = true,
  },

  master = {
    new_status = "master",
  },

  animations = {
    enabled = true,
  },

  misc = {
    force_default_wallpaper = 0,
    disable_hyprland_logo   = true,
  },

  input = {
    kb_layout    = "us",
    kb_variant   = "",
    kb_model     = "",
    kb_options   = "",
    kb_rules     = "",
    follow_mouse = 1,
    sensitivity  = 0,

    touchpad     = {
      natural_scroll = true,
    },
  },

  xwayland = {
    force_zero_scaling = true,
  },
})


------------------
--- ANIMATIONS ---
------------------

hl.curve("easeOutQuint", { type = "bezier", points = { { 0.23, 1 }, { 0.32, 1 } } })
hl.curve("easeInOutCubic", { type = "bezier", points = { { 0.65, 0.05 }, { 0.36, 1 } } })
hl.curve("linear", { type = "bezier", points = { { 0, 0 }, { 1, 1 } } })
hl.curve("almostLinear", { type = "bezier", points = { { 0.5, 0.5 }, { 0.75, 1.0 } } })
hl.curve("quick", { type = "bezier", points = { { 0.15, 0 }, { 0.1, 1 } } })

hl.animation({ leaf = "global", enabled = true, speed = 10, bezier = "default" })
hl.animation({ leaf = "border", enabled = true, speed = 5.39, bezier = "easeOutQuint" })
hl.animation({ leaf = "windows", enabled = true, speed = 4.79, bezier = "easeOutQuint" })
hl.animation({ leaf = "windowsIn", enabled = true, speed = 4.1, bezier = "easeOutQuint", style = "popin 87%" })
hl.animation({ leaf = "windowsOut", enabled = true, speed = 1.49, bezier = "linear", style = "popin 87%" })
hl.animation({ leaf = "fadeIn", enabled = true, speed = 1.73, bezier = "almostLinear" })
hl.animation({ leaf = "fadeOut", enabled = true, speed = 1.46, bezier = "almostLinear" })
hl.animation({ leaf = "fade", enabled = true, speed = 3.03, bezier = "quick" })
hl.animation({ leaf = "layers", enabled = true, speed = 3.81, bezier = "easeOutQuint" })
hl.animation({ leaf = "layersIn", enabled = true, speed = 4, bezier = "easeOutQuint", style = "fade" })
hl.animation({ leaf = "layersOut", enabled = true, speed = 1, bezier = "linear", style = "fade" })
hl.animation({ leaf = "fadeLayersIn", enabled = true, speed = 1.79, bezier = "almostLinear" })
hl.animation({ leaf = "fadeLayersOut", enabled = true, speed = 1.39, bezier = "almostLinear" })
hl.animation({ leaf = "workspaces", enabled = true, speed = 1.94, bezier = "almostLinear", style = "fade" })
hl.animation({ leaf = "workspacesIn", enabled = true, speed = 1.21, bezier = "almostLinear", style = "fade" })
hl.animation({ leaf = "workspacesOut", enabled = true, speed = 1.94, bezier = "almostLinear", style = "fade" })


------------------
--- PERIPHERALS --
------------------

hl.device({
  name        = "epic-mouse-v1",
  sensitivity = -0.5,
})


------------------
--- GESTURES -----
------------------

hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })


------------------
-- KEYBINDINGS ---
------------------

-- Apps
hl.bind(mainMod .. " + RETURN", hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + Q", hl.dsp.exec_cmd("~/.config/hypr/scripts/confirm_close.sh"))
hl.bind(mainMod .. " + E", hl.dsp.exec_cmd(fileManager))
hl.bind(mainMod .. " + R", hl.dsp.exec_cmd(menu))
hl.bind(mainMod .. " + B", hl.dsp.exec_cmd("~/.config/wofi/browser-launcher.sh"))
hl.bind(mainMod .. " + N", hl.dsp.exec_cmd("/home/aditya/.config/hypr/scripts/night_light_toggle.sh"))
hl.bind(mainMod .. " + I", hl.dsp.exec_cmd("~/.config/hypr/scripts/system-dashboard.sh"))
hl.bind(mainMod .. " + SHIFT + V", hl.dsp.exec_cmd("cliphist list | wofi --dmenu | cliphist decode | wl-copy"))

-- Session
hl.bind(mainMod .. " + M", hl.dsp.exit())
hl.bind("SUPER + L", hl.dsp.exec_cmd("~/.config/hypr/scripts/power-menu.sh"))

-- Window actions
hl.bind(mainMod .. " + F", hl.dsp.window.float({ action = "toggle" }))
hl.bind(mainMod .. " + P", hl.dsp.window.pseudo())

-- Layout
hl.bind(mainMod .. " + J", hl.dsp.layout("togglesplit"))

-- SUPER + {ARROW} to move around the workspace
hl.bind(mainMod .. " + left", hl.dsp.exec_cmd("~/.config/hypr/scripts/switch_workspace.sh prev"))
hl.bind(mainMod .. " + right", hl.dsp.exec_cmd("~/.config/hypr/scripts/switch_workspace.sh next"))

-- Workspaces (focus)
hl.bind(mainMod .. " + 1", hl.dsp.focus({ workspace = 1 }))
hl.bind(mainMod .. " + 2", hl.dsp.focus({ workspace = 2 }))
hl.bind(mainMod .. " + 3", hl.dsp.focus({ workspace = 3 }))
hl.bind(mainMod .. " + 4", hl.dsp.focus({ workspace = 4 }))
hl.bind(mainMod .. " + 5", hl.dsp.focus({ workspace = 5 }))
hl.bind(mainMod .. " + 6", hl.dsp.focus({ workspace = 6 }))
hl.bind(mainMod .. " + 7", hl.dsp.focus({ workspace = 7 }))
hl.bind(mainMod .. " + 8", hl.dsp.focus({ workspace = 8 }))
hl.bind(mainMod .. " + 9", hl.dsp.focus({ workspace = 9 }))
hl.bind(mainMod .. " + 0", hl.dsp.focus({ workspace = 10 }))

-- Workspaces (move window)
hl.bind(mainMod .. " + SHIFT + 1", hl.dsp.window.move({ workspace = 1 }))
hl.bind(mainMod .. " + SHIFT + 2", hl.dsp.window.move({ workspace = 2 }))
hl.bind(mainMod .. " + SHIFT + 3", hl.dsp.window.move({ workspace = 3 }))
hl.bind(mainMod .. " + SHIFT + 4", hl.dsp.window.move({ workspace = 4 }))
hl.bind(mainMod .. " + SHIFT + 5", hl.dsp.window.move({ workspace = 5 }))
hl.bind(mainMod .. " + SHIFT + 6", hl.dsp.window.move({ workspace = 6 }))
hl.bind(mainMod .. " + SHIFT + 7", hl.dsp.window.move({ workspace = 7 }))
hl.bind(mainMod .. " + SHIFT + 8", hl.dsp.window.move({ workspace = 8 }))
hl.bind(mainMod .. " + SHIFT + 9", hl.dsp.window.move({ workspace = 9 }))
hl.bind(mainMod .. " + SHIFT + 0", hl.dsp.window.move({ workspace = 10 }))

-- Workspace cycling scripts
hl.bind("SUPER + TAB", hl.dsp.exec_cmd("~/.config/hypr/scripts/increase_workspace.sh"))
hl.bind("SUPER + D", hl.dsp.exec_cmd("~/.config/hypr/scripts/delete_and_shift_workspaces.sh"))
hl.bind("ALT + TAB", hl.dsp.exec_cmd("~/.config/hypr/scripts/circular_workspace.sh"))

-- Special workspace
hl.bind(mainMod .. " + S", hl.dsp.workspace.toggle_special("magic"))
hl.bind(mainMod .. " + SHIFT + S", hl.dsp.window.move({ workspace = "special:magic" }))

-- Mouse workspace scrolling
hl.bind(mainMod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
hl.bind(mainMod .. " + mouse_up", hl.dsp.focus({ workspace = "e-1" }))

-- Mouse window drag/resize
hl.bind(mainMod .. " + mouse:272", hl.dsp.window.drag(), { mouse = true })
hl.bind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

-- Screenshot
hl.bind("PRINT", hl.dsp.exec_cmd("hyprshot -m region -o ~/Pictures"))
hl.bind(mainMod .. " + PRINT", hl.dsp.exec_cmd("hyprshot -m output -m active -o ~/Pictures"))

-- Volume (repeating + locked)
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"),
  { repeating = true, locked = true })
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"),
  { repeating = true, locked = true })
hl.bind("XF86AudioMute", hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"),
  { repeating = true, locked = true })
hl.bind("XF86AudioMicMute", hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"),
  { repeating = true, locked = true })

-- Brightness (repeating + locked)
hl.bind("XF86MonBrightnessUp", hl.dsp.exec_cmd("brightnessctl -e4 -n2 set 5%+"), { repeating = true, locked = true })
hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd("brightnessctl -e4 -n2 set 5%-"), { repeating = true, locked = true })

-- Media (locked)
hl.bind("XF86AudioNext", hl.dsp.exec_cmd("playerctl next"), { locked = true })
hl.bind("XF86AudioPause", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPlay", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPrev", hl.dsp.exec_cmd("playerctl previous"), { locked = true })


----------------------------
-- WINDOW RULES ------------
----------------------------

-- Ignore maximize requests from all apps, so no window can ever open
-- maximized/fullscreen-sized over the others.
hl.window_rule({
  name           = "suppress-maximize",
  match          = { class = ".*" },

  suppress_event = "maximize",
})

hl.window_rule({
  name        = "apply-something",
  match       = { class = "my-window" },
  border_size = 10,
})

hl.window_rule({
  name   = "system-dashboard-rules",
  match  = { class = "^(com\\.system\\.dashboard|system-dashboard)$" },
  float  = true,
  size   = { 1100, 850 },
  center = true,
})
