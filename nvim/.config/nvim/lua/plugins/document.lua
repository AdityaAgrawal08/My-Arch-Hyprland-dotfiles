return {
  -- Markdown Live Preview in Browser
  {
    "iamcco/markdown-preview.nvim",
    cmd = { "MarkdownPreviewToggle", "MarkdownPreview", "MarkdownPreviewStop" },
    ft = { "markdown" },
    build = "cd app && ./install.sh",
  },

  -- Distraction-Free Writing Mode
  {
    "folke/zen-mode.nvim",
    cmd = "ZenMode",
    opts = {
      window = {
        backdrop = 0.95,
        width = 120,
        options = {
          signcolumn = "no",
          number = false,
          relativenumber = false,
          cursorline = false,
          cursorcolumn = false,
          foldcolumn = "0",
        },
      },
    },
  },

  -- Paragraph Dimming
  {
    "folke/twilight.nvim",
    cmd = "Twilight",
    opts = {},
  },

  -- Smooth Physics-based Scrolling
  {
    "karb94/neoscroll.nvim",
    keys = { "<C-u>", "<C-d>", "<C-b>", "<C-f>", "<C-y>", "<C-e>", "zt", "zz", "zb" },
    config = function()
      require("neoscroll").setup()
    end,
  },

  -- Paste Clipboard Images
  {
    "HakonHarnes/img-clip.nvim",
    event = "VeryLazy",
    opts = {
      default = {
        -- The directory where images will be saved, relative to the current file
        dir_path = "assets",

        -- Automatically name the file (e.g., "image_2026-10-12_21-49-00.png")
        file_name = "image_%Y-%m-%d_%H-%M-%S",

        -- File extension format
        extension = "png",

        -- Keep paths relative to the current file
        use_absolute_path = false,
        relative_to_current_file = true,

        -- Prompt for a custom filename before saving (set to false for instant paste)
        prompt_for_file_name = true,

        -- Drag images from a browser or file explorer into the terminal to embed them
        drag_and_drop = {
          enabled = true,
          insert_mode = false,
        },
      },

      -- Adjust markup templates based on filetype
      filetypes = {
        markdown = {
          template = "![[$FILE_NAME]]($FILE_PATH)",
        },
      },
    },
    keys = {
      { "<leader>p", "<cmd>PasteImage<cr>", desc = "Paste image from clipboard" },
    },
  },

  -- Inline Images Preview using Kitty protocol (Lazy loaded)
  {
    "3rd/image.nvim",
    ft = { "markdown", "vimwiki" },
    opts = {
      backend = "kitty", -- or "ueberzug" if not using a Kitty graphics protocol terminal
      integrations = {
        markdown = {
          enabled = true,
          clear_in_insert_mode = false,
          download_remote_images = true,
          only_render_image_at_cursor = false,
          filetypes = { "markdown", "vimwiki" },
        },
      },
      max_width = 100,
      max_height = 12,
      max_width_window_percentage = math.huge,
      max_height_window_percentage = math.huge,
      window_overlap_clear_enabled = false,
    },
  }
}
