#!/usr/bin/env python3
import os
from PIL import Image, ImageEnhance

def process_wallpaper():
    input_path = "/home/aditya/.gemini/antigravity/brain/91fa5726-b486-43c6-b6ae-1ac27fdfd7a0/wider_cave_wallpaper_1783067501951.jpg"
    output_path = os.path.expanduser(
        "~/dotfiles/hypr/.config/hypr/themes/wallpapers/assets/wallpaper.png"
    )
    
    if not os.path.exists(input_path):
        print(f"Error: Generated image {input_path} not found.")
        return

    # Load original image
    img = Image.open(input_path)
    
    # Target canvas size: 1920x1080
    canvas_w, canvas_h = 1920, 1080
    waybar_height = 40  # Pad top 40px to fit below Waybar
    available_h = canvas_h - waybar_height  # 1040px
    
    # Scale widescreen image to 1920x1040 (fills the whole width below Waybar)
    new_w, new_h = canvas_w, available_h
    img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    # Apply visual treatments (brightness/saturation/overlay)
    # Reduce brightness to 72%
    img_resized = ImageEnhance.Brightness(img_resized).enhance(0.72)
    # Reduce saturation to 60%
    img_resized = ImageEnhance.Color(img_resized).enhance(0.60)
    
    # Apply a 15% Everforest-dark overlay (#2b3339)
    overlay_color = (43, 51, 57, 38)  # ~15% opacity
    overlay = Image.new("RGBA", (new_w, new_h), overlay_color)
    img_rgba = img_resized.convert("RGBA")
    img_treated = Image.alpha_composite(img_rgba, overlay)
    
    # Create a solid black background canvas
    canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
    
    # Paste the treated image below the waybar
    canvas.paste(img_treated.convert("RGB"), (0, waybar_height))
    
    # Save output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    canvas.save(output_path, "PNG")
    print(f"Processed wider-cave landscape wallpaper successfully saved to: {output_path}")

if __name__ == "__main__":
    process_wallpaper()
