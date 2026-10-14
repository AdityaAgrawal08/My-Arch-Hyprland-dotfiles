return {
  -- Icons
  { "nvim-tree/nvim-web-devicons", lazy = true },

  -- Theme
  {
    "ellisonleao/gruvbox.nvim",
    priority = 1000,
    config = function()
      local uv = vim.uv or vim.loop

      -- Follow the terminal's transparency state, published by the `terminal`
      -- fish command. Opaque terminal -> solid gruvbox (original nvim look).
      -- Transparent terminal -> transparent nvim.
      local pid = vim.env.KITTY_PID
      local dir = vim.env.XDG_RUNTIME_DIR or "/tmp"
      local path = pid and pid ~= "" and (dir .. "/kitty-mode-" .. pid) or nil

      local last = nil
      local function apply(mode)
        if mode == last then return end
        last = mode
        require("gruvbox").setup({ transparent_mode = mode ~= "opaque" })
        vim.cmd.colorscheme("gruvbox")
      end

      if path then
        if vim.fn.filereadable(path) == 0 then
          local f = io.open(path, "w")
          if f then
            f:write("transparent\n"); f:close()
          end
        end
        local f = io.open(path, "r")
        if f then
          apply(f:read("*l") or "transparent")
          f:close()
        else
          apply("transparent")
        end

        local h = uv.new_fs_event()
        if h then
          pcall(function()
            h:start(path, {}, vim.schedule_wrap(function()
              local fh = io.open(path, "r")
              if not fh then return end
              local mode = fh:read("*l")
              fh:close()
              if mode and mode ~= "" then apply(mode) end
            end))
          end)
        end
      else
        apply("transparent")
      end
    end,
  },

  -- Statusline
  {
    "nvim-lualine/lualine.nvim",
    event = "VeryLazy",
    dependencies = { "nvim-tree/nvim-web-devicons" },
    config = function()
      require("lualine").setup({
        options = {
          theme = "gruvbox",
          globalstatus = true,
          section_separators = { left = "", right = "" },
          component_separators = { left = "│", right = "│" },
        },
        sections = {
          lualine_a = { "mode" },
          lualine_b = { "branch", "diff", "diagnostics" },
          lualine_c = { { "filename", path = 1 } },
          lualine_x = { "encoding", "fileformat", "filetype" },
          lualine_y = { "progress" },
          lualine_z = { "location" },
        },
      })
    end,
  },

  {
    "rcarriga/nvim-notify",
    config = function()
      local notify = require("notify")
      notify.setup({
        background_colour = "#000000",
      })
      vim.notify = notify
    end,
  },

  -- noice.nvim (modern UI)
  {
    "folke/noice.nvim",
    event = "VeryLazy",
    dependencies = {
      "MunifTanjim/nui.nvim",
      "rcarriga/nvim-notify",
    },
    config = function()
      require("noice").setup({
        lsp = {
          override = {
            ["vim.lsp.util.convert_input_to_markdown_lines"] = true,
            ["vim.lsp.util.stylize_markdown"] = true,
          },
        },
        presets = {
          bottom_search = true,
          command_palette = true,
          long_message_to_split = true,
          inc_rename = true,
        },
      })
    end,
  },

  -- inc-rename
  {
    "smjonas/inc-rename.nvim",
    config = function()
      require("inc_rename").setup()
    end,
  },

  -- Indent guides
  {
    "lukas-reineke/indent-blankline.nvim",
    main = "ibl",
    event = { "BufReadPost", "BufNewFile" },
    opts = {},
  },

  -- Dashboard
  {
    "nvimdev/dashboard-nvim",
    event = "VimEnter",
    config = function()
      local db = require("dashboard")
      db.setup({
        theme = "hyper",
        config = {
          week_header = {
            enable = true,
          },
          shortcut = {
            { desc = "Files",     group = "@property", action = "Telescope find_files", key = "f" },
            { desc = "Live grep", group = "@string",   action = "Telescope live_grep",  key = "g" },
            { desc = "Neo-tree",  group = "@constant", action = "Neotree toggle",       key = "n" },
          },
        },
      })
    end,
  },
}
