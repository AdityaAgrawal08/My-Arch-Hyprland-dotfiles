local M = {}

local function cache_dir()
  return (vim.env.XDG_CACHE_HOME or (vim.env.HOME .. "/.cache")) .. "/autotheme"
end

M.theme_path = cache_dir() .. "/theme.json"

local fallback = {
  bg = "#101010",
  surface = "#1a1a1a",
  surfaceHigh = "#242424",
  border = "#3a3a3a",
  fg = "#e6e6e6",
  muted = "#9a9a9a",
  accent = "#d0d0d0",
  accentSoft = "#a8a8a8",
  onAccent = "#111111",
  critical = "#ff6b6b",
  warning = "#e6c07b",
  success = "#a6e3a1",
  ansi_red = "#d17a7a",
  ansi_green = "#9ecf8f",
  ansi_yellow = "#d6c07a",
  ansi_blue = "#8aa8d6",
  ansi_magenta = "#c99ac9",
  ansi_cyan = "#8fc9c9",
}

local function pick(theme, key)
  local value = theme[key]
  if type(value) == "string" and value ~= "" then
    return value
  end
  return fallback[key] or fallback.fg
end

function M.load()
  local ok, lines = pcall(vim.fn.readfile, M.theme_path)
  if not ok or not lines or #lines == 0 then
    return {}
  end
  local decoded_ok, decoded = pcall(vim.json.decode, table.concat(lines, "\n"))
  if not decoded_ok or type(decoded) ~= "table" then
    return {}
  end
  return decoded
end

function M.colors()
  if not M._theme then
    M._theme = M.load()
  end
  return M._theme
end

function M.color(key)
  return pick(M.colors(), key)
end

function M.mode()
  local pid = vim.env.KITTY_PID
  if not pid or pid == "" then
    return "opaque"
  end
  local path = (vim.env.XDG_RUNTIME_DIR or "/tmp") .. "/kitty-mode-" .. pid
  local file = io.open(path, "r")
  if not file then
    return "transparent"
  end
  local mode = file:read("*l") or "transparent"
  file:close()
  return mode
end

local function hl(name, options)
  vim.api.nvim_set_hl(0, name, options)
end

local function link(name, target)
  vim.api.nvim_set_hl(0, name, { link = target })
end

function M.apply(theme)
  theme = theme or {}
  local bg = pick(theme, "bg")
  local surface = pick(theme, "surface")
  local surface_high = pick(theme, "surfaceHigh")
  local border = pick(theme, "border")
  local fg = pick(theme, "fg")
  local muted = pick(theme, "muted")
  local accent = pick(theme, "accent")
  local accent_soft = pick(theme, "accentSoft")
  local on_accent = pick(theme, "onAccent")
  local critical = pick(theme, "critical")
  local warning = pick(theme, "warning")
  local success = pick(theme, "success")
  local ansi_red = pick(theme, "ansi_red")
  local ansi_green = pick(theme, "ansi_green")
  local ansi_yellow = pick(theme, "ansi_yellow")
  local ansi_blue = pick(theme, "ansi_blue")
  local ansi_magenta = pick(theme, "ansi_magenta")
  local ansi_cyan = pick(theme, "ansi_cyan")

  local transparent = M.mode() ~= "opaque"
  local normal_bg = transparent and "NONE" or bg

  vim.cmd("hi clear")
  vim.g.colors_name = "autotheme"
  vim.o.background = "dark"
  vim.o.termguicolors = true

  hl("Normal", { fg = fg, bg = normal_bg })
  hl("NormalNC", { fg = fg, bg = normal_bg })
  hl("NormalFloat", { fg = fg, bg = surface })
  hl("FloatBorder", { fg = border, bg = surface })
  hl("FloatTitle", { fg = accent, bg = surface, bold = true })
  hl("FloatShadow", { bg = bg })
  hl("FloatShadowThrough", { bg = bg })
  hl("Cursor", { fg = on_accent, bg = accent })
  hl("lCursor", { fg = on_accent, bg = accent })
  hl("CursorIM", { fg = on_accent, bg = accent })
  hl("TermCursor", { fg = on_accent, bg = accent })
  hl("TermCursorNC", { fg = on_accent, bg = accent_soft })
  hl("CursorLine", { bg = surface })
  hl("CursorColumn", { bg = surface })
  hl("ColorColumn", { bg = surface })
  hl("CursorLineNr", { fg = accent, bold = true })
  hl("LineNr", { fg = muted, bg = normal_bg })
  hl("LineNrAbove", { fg = muted })
  hl("LineNrBelow", { fg = muted })
  hl("SignColumn", { fg = muted, bg = normal_bg })
  hl("FoldColumn", { fg = muted, bg = normal_bg })
  hl("Folded", { fg = muted, bg = surface })
  hl("WinSeparator", { fg = border })
  hl("VertSplit", { fg = border })

  hl("StatusLine", { fg = fg, bg = surface })
  hl("StatusLineNC", { fg = muted, bg = surface })
  hl("TabLine", { fg = muted, bg = surface })
  hl("TabLineFill", { bg = surface })
  hl("TabLineSel", { fg = on_accent, bg = accent, bold = true })

  hl("Pmenu", { fg = fg, bg = surface })
  hl("PmenuSel", { fg = on_accent, bg = accent, bold = true })
  hl("PmenuSbar", { bg = surface_high })
  hl("PmenuThumb", { bg = border })
  hl("PmenuKind", { fg = accent_soft, bg = surface })
  hl("PmenuKindSel", { fg = on_accent, bg = accent })
  hl("PmenuExtra", { fg = muted, bg = surface })
  hl("PmenuExtraSel", { fg = on_accent, bg = accent })

  hl("Visual", { fg = fg, bg = surface_high })
  hl("VisualNOS", { fg = fg, bg = surface_high })
  hl("Search", { fg = on_accent, bg = accent })
  hl("IncSearch", { fg = on_accent, bg = accent_soft })
  hl("CurSearch", { fg = on_accent, bg = accent_soft })
  hl("MatchParen", { fg = accent, bg = surface_high, bold = true })

  hl("Directory", { fg = accent })
  hl("Title", { fg = accent, bold = true })
  hl("Question", { fg = success })
  hl("ModeMsg", { fg = fg, bold = true })
  hl("MoreMsg", { fg = success })
  hl("WarningMsg", { fg = warning })
  hl("ErrorMsg", { fg = critical })
  hl("Error", { fg = critical })
  hl("Todo", { fg = accent, bold = true })
  hl("QuickFixLine", { bg = surface_high })
  hl("SpellBad", { sp = critical, undercurl = true })
  hl("SpellCap", { sp = warning, undercurl = true })
  hl("SpellLocal", { sp = accent_soft, undercurl = true })
  hl("SpellRare", { sp = accent, undercurl = true })

  hl("Comment", { fg = muted, italic = true })
  hl("Constant", { fg = accent_soft })
  hl("String", { fg = ansi_green })
  hl("Character", { fg = ansi_green })
  hl("Number", { fg = ansi_yellow })
  hl("Boolean", { fg = ansi_yellow })
  hl("Float", { fg = ansi_yellow })
  hl("Identifier", { fg = fg })
  hl("Function", { fg = accent })
  hl("Statement", { fg = ansi_magenta })
  hl("Conditional", { fg = ansi_magenta })
  hl("Repeat", { fg = ansi_magenta })
  hl("Label", { fg = ansi_magenta })
  hl("Operator", { fg = muted })
  hl("Keyword", { fg = ansi_magenta })
  hl("Exception", { fg = ansi_magenta })
  hl("PreProc", { fg = ansi_cyan })
  hl("Include", { fg = ansi_cyan })
  hl("Define", { fg = ansi_cyan })
  hl("Macro", { fg = ansi_cyan })
  hl("PreCondit", { fg = ansi_cyan })
  hl("Type", { fg = ansi_yellow })
  hl("StorageClass", { fg = ansi_yellow })
  hl("Structure", { fg = ansi_yellow })
  hl("Typedef", { fg = ansi_yellow })
  hl("Special", { fg = accent_soft })
  hl("SpecialChar", { fg = accent_soft })
  hl("Tag", { fg = accent_soft })
  hl("Delimiter", { fg = fg })
  hl("SpecialComment", { fg = muted, italic = true })
  hl("Debug", { fg = ansi_red })
  hl("Underlined", { fg = ansi_blue, underline = true })
  hl("Ignore", { fg = muted })

  hl("DiagnosticError", { fg = critical })
  hl("DiagnosticWarn", { fg = warning })
  hl("DiagnosticInfo", { fg = accent_soft })
  hl("DiagnosticHint", { fg = muted })
  hl("DiagnosticOk", { fg = success })
  hl("DiagnosticUnderlineError", { sp = critical, undercurl = true })
  hl("DiagnosticUnderlineWarn", { sp = warning, undercurl = true })
  hl("DiagnosticUnderlineInfo", { sp = accent_soft, undercurl = true })
  hl("DiagnosticUnderlineHint", { sp = muted, undercurl = true })
  hl("DiagnosticVirtualTextError", { fg = critical, bg = surface })
  hl("DiagnosticVirtualTextWarn", { fg = warning, bg = surface })
  hl("DiagnosticVirtualTextInfo", { fg = accent_soft, bg = surface })
  hl("DiagnosticVirtualTextHint", { fg = muted, bg = surface })

  hl("LspReferenceText", { bg = surface_high })
  hl("LspReferenceRead", { bg = surface_high })
  hl("LspReferenceWrite", { bg = surface_high })
  hl("LspSignatureActiveParameter", { fg = accent, bold = true })

  hl("GitSignsAdd", { fg = success })
  hl("GitSignsChange", { fg = warning })
  hl("GitSignsDelete", { fg = critical })
  hl("GitSignsAddLn", { bg = surface })
  hl("GitSignsChangeLn", { bg = surface })
  hl("GitSignsDeleteLn", { bg = surface })
  hl("GitSignsAddInline", { bg = surface })
  hl("GitSignsChangeInline", { bg = surface })
  hl("GitSignsDeleteInline", { bg = surface })

  hl("TelescopeNormal", { fg = fg, bg = surface })
  hl("TelescopeBorder", { fg = border, bg = surface })
  hl("TelescopeTitle", { fg = accent, bg = surface, bold = true })
  hl("TelescopePromptNormal", { fg = fg, bg = surface })
  hl("TelescopePromptBorder", { fg = border, bg = surface })
  hl("TelescopePromptTitle", { fg = accent, bg = surface, bold = true })
  hl("TelescopeResultsNormal", { fg = fg, bg = surface })
  hl("TelescopeResultsBorder", { fg = border, bg = surface })
  hl("TelescopePreviewNormal", { fg = fg, bg = surface })
  hl("TelescopePreviewBorder", { fg = border, bg = surface })
  hl("TelescopeSelection", { fg = on_accent, bg = accent })
  hl("TelescopeSelectionCaret", { fg = on_accent, bg = accent })
  hl("TelescopeMatching", { fg = accent, bold = true })
  hl("TelescopeMultiSelection", { fg = accent_soft })

  hl("NeoTreeNormal", { fg = fg, bg = surface })
  hl("NeoTreeNormalNC", { fg = fg, bg = surface })
  hl("NeoTreeDirectoryName", { fg = accent })
  hl("NeoTreeDirectoryIcon", { fg = accent })
  hl("NeoTreeRootName", { fg = accent, bold = true })
  hl("NeoTreeFileName", { fg = fg })
  hl("NeoTreeFileIcon", { fg = muted })
  hl("NeoTreeIndentMarker", { fg = border })
  hl("NeoTreeGitAdded", { fg = success })
  hl("NeoTreeGitModified", { fg = warning })
  hl("NeoTreeGitDeleted", { fg = critical })
  hl("NeoTreeGitUntracked", { fg = accent_soft })
  hl("NeoTreeCursorLine", { bg = surface_high })

  hl("TroubleNormal", { fg = fg, bg = surface })
  hl("TroubleText", { fg = fg })
  hl("TroubleCount", { fg = accent })
  hl("TroubleFile", { fg = accent_soft })
  hl("TroubleFoldIcon", { fg = accent })
  hl("TroubleIndent", { fg = border })

  hl("WhichKey", { fg = accent })
  hl("WhichKeyGroup", { fg = accent_soft })
  hl("WhichKeyDesc", { fg = fg })
  hl("WhichKeySeparator", { fg = muted })
  hl("WhichKeyFloat", { bg = surface })
  hl("WhichKeyBorder", { fg = border, bg = surface })

  hl("NoiceCmdline", { fg = fg, bg = surface })
  hl("NoiceCmdlineIcon", { fg = accent })
  hl("NoiceCmdlinePopup", { fg = fg, bg = surface })
  hl("NoiceCmdlinePopupBorder", { fg = border, bg = surface })
  hl("NoiceConfirm", { fg = fg, bg = surface })
  hl("NoiceConfirmBorder", { fg = border, bg = surface })
  hl("NoiceMini", { fg = fg, bg = surface })
  hl("NoicePopup", { fg = fg, bg = surface })
  hl("NoicePopupBorder", { fg = border, bg = surface })

  hl("NotifyERRORBorder", { fg = critical })
  hl("NotifyWARNBorder", { fg = warning })
  hl("NotifyINFOBorder", { fg = accent_soft })
  hl("NotifyDEBUGBorder", { fg = muted })
  hl("NotifyTRACEBorder", { fg = accent })
  hl("NotifyERRORIcon", { fg = critical })
  hl("NotifyWARNIcon", { fg = warning })
  hl("NotifyINFOIcon", { fg = accent_soft })
  hl("NotifyDEBUGIcon", { fg = muted })
  hl("NotifyTRACEIcon", { fg = accent })
  hl("NotifyERRORTitle", { fg = critical, bold = true })
  hl("NotifyWARNTitle", { fg = warning, bold = true })
  hl("NotifyINFOTitle", { fg = accent_soft, bold = true })
  hl("NotifyDEBUGTitle", { fg = muted, bold = true })
  hl("NotifyTRACETitle", { fg = accent, bold = true })

  hl("BlinkCmpMenu", { fg = fg, bg = surface })
  hl("BlinkCmpMenuBorder", { fg = border, bg = surface })
  hl("BlinkCmpMenuSelection", { fg = on_accent, bg = accent, bold = true })
  hl("BlinkCmpScrollBarThumb", { bg = border })
  hl("BlinkCmpScrollBarGutter", { bg = surface_high })
  hl("BlinkCmpLabel", { fg = fg })
  hl("BlinkCmpLabelMatch", { fg = accent, bold = true })
  hl("BlinkCmpLabelDetail", { fg = muted })
  hl("BlinkCmpLabelDescription", { fg = muted })
  hl("BlinkCmpKind", { fg = accent_soft })
  hl("BlinkCmpDoc", { fg = fg, bg = surface })
  hl("BlinkCmpDocBorder", { fg = border, bg = surface })
  hl("BlinkCmpSignatureHelp", { fg = fg, bg = surface })
  hl("BlinkCmpSignatureHelpBorder", { fg = border, bg = surface })

  hl("DashboardHeader", { fg = accent, bold = true })
  hl("DashboardFooter", { fg = muted, italic = true })
  hl("DashboardKey", { fg = accent_soft })
  hl("DashboardDesc", { fg = fg })
  hl("DashboardIcon", { fg = accent })
  hl("DashboardShortCut", { fg = accent_soft })

  hl("IblIndent", { fg = border })
  hl("IblScope", { fg = accent_soft })
  hl("IndentBlanklineChar", { fg = border })
  hl("IndentBlanklineContextChar", { fg = accent_soft })
  hl("UfoFoldedFg", { fg = muted })
  hl("UfoFoldedBg", { bg = surface })
  hl("RenderMarkdownH1Bg", { bg = surface })
  hl("RenderMarkdownH2Bg", { bg = surface })
  hl("RenderMarkdownH3Bg", { bg = surface })
  hl("RenderMarkdownCode", { bg = surface })
  hl("RenderMarkdownBullet", { fg = accent })
  hl("RenderMarkdownDash", { fg = border })

  hl("@variable", { fg = fg })
  hl("@variable.builtin", { fg = accent_soft })
  hl("@parameter", { fg = fg })
  hl("@function", { fg = accent })
  hl("@function.call", { fg = accent })
  hl("@keyword", { fg = ansi_magenta })
  hl("@keyword.function", { fg = ansi_magenta })
  hl("@string", { fg = ansi_green })
  hl("@number", { fg = ansi_yellow })
  hl("@boolean", { fg = ansi_yellow })
  hl("@type", { fg = ansi_yellow })
  hl("@constant", { fg = accent_soft })
  hl("@operator", { fg = muted })
  hl("@punctuation", { fg = fg })
  hl("@comment", { fg = muted, italic = true })
  hl("@tag", { fg = ansi_cyan })
  hl("@attribute", { fg = accent_soft })

  link("markdownH1", "Title")
  link("markdownH2", "Title")
  link("markdownH3", "Title")
  link("markdownH1Delimiter", "Comment")
  link("markdownH2Delimiter", "Comment")
  link("markdownH3Delimiter", "Comment")
  link("markdownLinkText", "Underlined")
  link("markdownUrl", "Underlined")
  link("markdownCode", "String")
  link("markdownCodeBlock", "String")

  vim.cmd("doautocmd ColorScheme")
end

function M.setup()
  M._theme = M.load()
  M.apply(M._theme)

  local function mtime()
    local stat = vim.uv.fs_stat(M.theme_path)
    return stat and stat.mtime.sec or 0
  end

  local last_theme = mtime()
  local last_mode = M.mode()

  local timer = vim.uv.new_timer()
  if not timer then
    return
  end

  timer:start(2000, 2000, vim.schedule_wrap(function()
    local theme_changed = mtime() ~= last_theme
    local mode_changed = M.mode() ~= last_mode
    if not theme_changed and not mode_changed then
      return
    end
    last_theme = mtime()
    last_mode = M.mode()
    M._theme = M.load()
    M.apply(M._theme)
  end))
end

return M
