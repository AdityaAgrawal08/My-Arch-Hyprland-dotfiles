local M = {}

local function get_char_len(str, byte_pos)
  if byte_pos > #str then return 0 end
  local next_pos = byte_pos + 1
  while next_pos <= #str do
    local byte = string.byte(str, next_pos)
    if byte < 128 or byte >= 192 then
      break
    end
    next_pos = next_pos + 1
  end
  return next_pos - byte_pos
end

local function get_cursor_word_bounds(line, col, word)
  if word == "" then return nil, nil end
  local start_pos = 1
  while true do
    local s, e = line:find(word, start_pos, true)
    if not s then break end
    local cursor_pos = col + 1
    if cursor_pos >= s and cursor_pos <= e then
      return s, e
    end
    start_pos = s + 1
  end
  return line:find(word, 1, true)
end

-- Custom formatting helper functions
local function toggle_wrap(prefix, suffix)
  suffix = suffix or prefix
  local mode = vim.fn.mode()
  if mode == "v" or mode == "V" or mode == "\22" then
    vim.cmd("normal! \27") -- exit visual mode to set '< and '> marks
    local start_line = vim.fn.line("'<")
    local start_col = vim.fn.col("'<")
    local end_line = vim.fn.line("'>")
    local end_col = vim.fn.col("'>")
    
    local lines = vim.api.nvim_buf_get_lines(0, start_line - 1, end_line, false)
    if #lines == 0 then return end
    
    if #lines == 1 then
      local line = lines[1]
      local char_len = get_char_len(line, end_col)
      local actual_end = end_col + char_len - 1
      
      local before = string.sub(line, 1, start_col - 1)
      local selected = string.sub(line, start_col, actual_end)
      local after = string.sub(line, actual_end + 1)
      
      if string.sub(selected, 1, #prefix) == prefix and string.sub(selected, -#suffix) == suffix then
        selected = string.sub(selected, #prefix + 1, -#suffix - 1)
      else
        selected = prefix .. selected .. suffix
      end
      vim.api.nvim_buf_set_lines(0, start_line - 1, start_line, false, { before .. selected .. after })
    else
      local end_line_text = lines[#lines]
      local char_len = get_char_len(end_line_text, end_col)
      local actual_end = end_col + char_len - 1
      
      lines[1] = string.sub(lines[1], 1, start_col - 1) .. prefix .. string.sub(lines[1], start_col)
      lines[#lines] = string.sub(lines[#lines], 1, actual_end) .. suffix .. string.sub(lines[#lines], actual_end + 1)
      vim.api.nvim_buf_set_lines(0, start_line - 1, end_line, false, lines)
    end
  else
    local word = vim.fn.expand("<cword>")
    if word == "" then return end
    local line = vim.api.nvim_get_current_line()
    local col = vim.api.nvim_win_get_cursor(0)[2]
    
    local start_pos, end_pos = get_cursor_word_bounds(line, col, word)
    if not start_pos then return end
    
    local before = string.sub(line, 1, start_pos - 1)
    local after = string.sub(line, end_pos + 1)
    
    local wrapped_before = string.sub(before, -#prefix) == prefix
    local wrapped_after = string.sub(after, 1, #suffix) == suffix
    if wrapped_before and wrapped_after then
      before = string.sub(before, 1, -#prefix - 1)
      after = string.sub(after, #suffix + 1)
    else
      word = prefix .. word .. suffix
    end
    vim.api.nvim_set_current_line(before .. word .. after)
  end
end

local function prepend_lines(prefix)
  local mode = vim.fn.mode()
  local start_line, end_line
  if mode ~= "v" and mode ~= "V" and mode ~= "\22" then
    start_line = vim.fn.line(".")
    end_line = start_line
  else
    vim.cmd("normal! \27")
    start_line = vim.fn.line("'<")
    end_line = vim.fn.line("'>")
  end
  
  local lines = vim.api.nvim_buf_get_lines(0, start_line - 1, end_line, false)
  for i, line in ipairs(lines) do
    if string.sub(line, 1, #prefix) == prefix then
      lines[i] = string.sub(line, #prefix + 1)
    else
      lines[i] = prefix .. line
    end
  end
  vim.api.nvim_buf_set_lines(0, start_line - 1, end_line, false, lines)
end

local function insert_at_cursor(text)
  vim.api.nvim_put({ text }, "c", true, true)
end

local function insert_link()
  vim.ui.input({ prompt = "Link Text: " }, function(text)
    if not text then return end
    vim.ui.input({ prompt = "URL: ", default = "https://" }, function(url)
      if not url then return end
      insert_at_cursor(string.format("[%s](%s)", text, url))
    end)
  end)
end

local function insert_table()
  vim.ui.input({ prompt = "Columns: ", default = "3" }, function(cols_str)
    local cols = tonumber(cols_str) or 3
    vim.ui.input({ prompt = "Rows: ", default = "2" }, function(rows_str)
      local rows = tonumber(rows_str) or 2
      
      local header = "|"
      local separator = "|"
      for i = 1, cols do
        header = header .. " Header " .. i .. " |"
        separator = separator .. " -------- |"
      end
      
      local lines = { header, separator }
      for r = 1, rows do
        local row_str = "|"
        for c = 1, cols do
          row_str = row_str .. " Cell |"
        end
        table.insert(lines, row_str)
      end
      
      local row = vim.api.nvim_win_get_cursor(0)[1]
      vim.api.nvim_buf_set_lines(0, row, row, false, lines)
    end)
  end)
end

local function toggle_checkbox()
  local line = vim.api.nvim_get_current_line()
  if line:match("^%s*[%-%*]%s+%[%s+%]") then
    line = line:gsub("^(%s*)([%-%*])%s+%[%s+%]", "%1%2 [x]", 1)
  elseif line:match("^%s*[%-%*]%s+%[x%]") then
    line = line:gsub("^(%s*)([%-%*])%s+%[x%]", "%1%2 [ ]", 1)
  else
    if line:match("^%s*[%-%*]%s+") then
      line = line:gsub("^(%s*)([%-%*])%s+", "%1%2 [ ] ", 1)
    else
      line = line:gsub("^(%s*)", "%1- [ ] ", 1)
    end
  end
  vim.api.nvim_set_current_line(line)
end

local function toggle_code_block()
  local mode = vim.fn.mode()
  local start_line, end_line
  if mode == "v" or mode == "V" or mode == "\22" then
    vim.cmd("normal! \27")
    local vstart = vim.fn.line("'<")
    local vend = vim.fn.line("'>")
    start_line = math.min(vstart, vend)
    end_line = math.max(vstart, vend)
  else
    start_line = vim.fn.line(".")
    end_line = start_line
  end

  local lines = vim.api.nvim_buf_get_lines(0, start_line - 1, end_line, false)
  if #lines == 0 then return end

  -- Check if already wrapped with ``` above and below
  local prev_line = start_line > 1 and vim.api.nvim_buf_get_lines(0, start_line - 2, start_line - 1, false)[1] or ""
  local next_line = vim.api.nvim_buf_get_lines(0, end_line, end_line + 1, false)[1] or ""

  if prev_line:match("^%s*```") and next_line:match("^%s*```") then
    -- Remove the ``` lines
    vim.api.nvim_buf_set_lines(0, end_line, end_line + 1, false, {})
    vim.api.nvim_buf_set_lines(0, start_line - 2, start_line - 1, false, {})
  else
    -- Insert ``` above and below
    vim.api.nvim_buf_set_lines(0, end_line, end_line, false, { "```" })
    vim.api.nvim_buf_set_lines(0, start_line - 1, start_line - 1, false, { "```" })
  end
end

-- Custom Markdown Toolbar Picker
local function apply_format(choice)
  if choice == "Bold" then
    toggle_wrap("**")
  elseif choice == "Italic" then
    toggle_wrap("*")
  elseif choice == "Underline" then
    toggle_wrap("<u>", "</u>")
  elseif choice == "Strikethrough" then
    toggle_wrap("~~")
  elseif choice == "Bullet List" then
    prepend_lines("- ")
  elseif choice == "Numbered List" then
    prepend_lines("1. ")
  elseif choice == "Quote" then
    prepend_lines("> ")
  elseif choice == "Heading 1" then
    prepend_lines("# ")
  elseif choice == "Heading 2" then
    prepend_lines("## ")
  elseif choice == "Heading 3" then
    prepend_lines("### ")
  elseif choice == "Code Block" then
    toggle_code_block()
  elseif choice == "Horizontal Rule" then
    insert_at_cursor("\n---\n")
  elseif choice == "Link" then
    insert_link()
  elseif choice == "Table" then
    insert_table()
  elseif choice == "Checkbox" then
    toggle_checkbox()
  end
end

local function show_toolbar()
  local items = {
    "Bold", "Italic", "Underline", "Strikethrough",
    "Bullet List", "Numbered List", "Quote",
    "Heading 1", "Heading 2", "Heading 3",
    "Code Block", "Horizontal Rule", "Link", "Table", "Checkbox"
  }
  vim.ui.select(items, {
    prompt = "Markdown Formatting Toolbar",
  }, function(choice)
    if not choice then return end
    apply_format(choice)
  end)
end

-- Focus / Zen Mode
local focus_active = false
local original_scrolloff = nil

local function is_twilight_open()
  local ok, twilight_view = pcall(require, "twilight.view")
  if ok and type(twilight_view.is_open) == "function" then
    local is_open_ok, result = pcall(twilight_view.is_open)
    if is_open_ok then return result end
  end
  local ok_t, twilight = pcall(require, "twilight")
  if ok_t and twilight.enabled ~= nil then
    return twilight.enabled
  end
  return false
end

local function toggle_focus_mode()
  focus_active = not focus_active
  local has_zen, zen = pcall(require, "zen-mode")
  local has_twilight, _ = pcall(require, "twilight")
  
  if focus_active then
    original_scrolloff = vim.wo.scrolloff
    vim.wo.scrolloff = 999
    vim.wo.wrap = true
    vim.wo.linebreak = true
    vim.wo.spell = true
    
    pcall(function()
      if has_zen and not zen.active then
        vim.cmd("ZenMode")
      end
      if has_twilight and not is_twilight_open() then
        vim.cmd("Twilight")
      end
    end)
    vim.notify("Focus Mode Enabled (Typewriter scroll active)", vim.log.levels.INFO)
  else
    if original_scrolloff then
      vim.wo.scrolloff = original_scrolloff
    end
    vim.wo.spell = false
    
    pcall(function()
      if has_zen and zen.active then
        vim.cmd("ZenMode")
      end
      if has_twilight and is_twilight_open() then
        vim.cmd("Twilight")
      end
    end)
    vim.notify("Focus Mode Disabled", vim.log.levels.INFO)
  end
end

-- Image resizing function
local function resize_image(args)
  local arg = args.args
  if not arg or arg == "" then
    vim.notify("Usage: :ImageResize 50 (or :ImageResize 300x200)", vim.log.levels.ERROR)
    return
  end
  
  local line = vim.api.nvim_get_current_line()
  local path = line:match("!%[.-%]%((.-)%)")
  if not path then
    vim.notify("No markdown image reference found on current line.", vim.log.levels.ERROR)
    return
  end
  
  local buf_dir = vim.fn.expand("%:p:h")
  local abs_path = vim.fn.simplify(buf_dir .. "/" .. path)
  
  if vim.fn.filereadable(abs_path) == 0 then
    vim.notify("Image file not found: " .. abs_path, vim.log.levels.ERROR)
    return
  end
  
  local resize_arg
  if arg:match("^%d+$") then
    resize_arg = arg .. "%"
  elseif arg:match("^%d+x%d+$") then
    resize_arg = arg .. "!"
  else
    resize_arg = arg
  end
  
  local backup_path = abs_path .. ".bak"
  vim.fn.system(string.format("cp %q %q", abs_path, backup_path))
  local cmd = string.format("mogrify -resize %s %q", resize_arg, abs_path)
  vim.fn.jobstart(cmd, {
    on_exit = function(_, exit_code)
      if exit_code == 0 then
        vim.fn.delete(backup_path)
        vim.notify("Resized image to " .. arg, vim.log.levels.INFO)
        pcall(function()
          require("image").clear()
        end)
      else
        vim.fn.system(string.format("mv %q %q", backup_path, abs_path))
        vim.notify("Failed to resize image using mogrify. Restored original.", vim.log.levels.ERROR)
      end
    end
  })
end

-- Document export: prefer the doc-tools suite, fall back to pandoc.
local function export_document(format)
  local infile = vim.fn.expand("%:p")
  local outfile = vim.fn.expand("%:p:r") .. "." .. format
  
  if infile == "" then
    vim.notify("Buffer must be saved to a file first.", vim.log.levels.ERROR)
    return
  end
  
  vim.notify("Exporting to " .. format:upper() .. "...", vim.log.levels.INFO)

  local toolkit = {
    pdf = "md2pdf",
    html = "md2html",
    docx = "md2docx",
  }
  local cmd
  if vim.fn.executable("docs") == 1 and toolkit[format] then
    cmd = string.format("%s %q -o %q", toolkit[format], infile, outfile)
  else
    cmd = string.format("pandoc %q -o %q", infile, outfile)
  end

  vim.fn.jobstart(cmd, {
    on_exit = function(_, exit_code)
      if exit_code == 0 then
        vim.notify("Successfully exported to " .. outfile, vim.log.levels.INFO)
      else
        vim.notify(
          "Export failed. Install the doc-tools suite (docs doctor) or pandoc.",
          vim.log.levels.ERROR
        )
      end
    end
  })
end

local function show_export_menu()
  local items = { "PDF", "HTML", "DOCX" }
  vim.ui.select(items, {
    prompt = "Export Document Format",
  }, function(choice)
    if not choice then return end
    export_document(choice:lower())
  end)
end

function M.setup(bufnr)
  local opts = { buffer = bufnr, silent = true }
  
  -- Buffer-local keymaps
  vim.keymap.set({ "n", "v" }, "<C-b>", function() toggle_wrap("**") end, opts)
  vim.keymap.set({ "n", "v" }, "<C-i>", function() toggle_wrap("*") end, opts)
  vim.keymap.set("n", "<C-Space>", toggle_checkbox, opts)
  
  vim.keymap.set("n", "<leader>mt", show_toolbar, opts)
  vim.keymap.set("n", "<leader>mi", ":PasteImage<CR>", opts)
  vim.keymap.set("n", "<leader>ml", insert_link, opts)
  vim.keymap.set("n", "<leader>mp", ":MarkdownPreviewToggle<CR>", opts)
  vim.keymap.set("n", "<leader>me", show_export_menu, opts)
  vim.keymap.set("n", "<leader>mf", toggle_focus_mode, opts)

  -- Document writing preferences
  vim.wo.wrap = true
  vim.wo.linebreak = true
  vim.wo.spell = true

  -- Register buffer-local user commands
  vim.api.nvim_buf_create_user_command(bufnr, "MarkdownToolbar", show_toolbar, {})
  vim.api.nvim_buf_create_user_command(bufnr, "ImageResize", resize_image, { nargs = 1 })
  vim.api.nvim_buf_create_user_command(bufnr, "ExportPDF", function() export_document("pdf") end, {})
  vim.api.nvim_buf_create_user_command(bufnr, "ExportHTML", function() export_document("html") end, {})
  vim.api.nvim_buf_create_user_command(bufnr, "ExportDOCX", function() export_document("docx") end, {})
  vim.api.nvim_buf_create_user_command(bufnr, "ExportMenu", show_export_menu, {})
  vim.api.nvim_buf_create_user_command(bufnr, "FocusModeToggle", toggle_focus_mode, {})
end

M.toggle_checkbox = toggle_checkbox
M.toggle_code_block = toggle_code_block

return M
