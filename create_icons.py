#!/usr/bin/env python3

from PIL import Image, ImageDraw
import os

def create_circle_icon(size, color, recording=False):
    """Create a circular microphone icon"""
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Calculate dimensions
    padding = size // 8
    mic_width = size // 3
    mic_height = size // 2
    base_height = size // 6
    
    # Draw microphone body
    mic_left = (size - mic_width) // 2
    mic_top = padding
    mic_right = mic_left + mic_width
    mic_bottom = mic_top + mic_height
    
    # Microphone body (rounded rectangle)
    draw.rounded_rectangle(
        [mic_left, mic_top, mic_right, mic_bottom],
        radius=mic_width // 2,
        fill=color
    )
    
    # Microphone base
    base_left = size // 4
    base_right = size - size // 4
    base_top = mic_bottom - base_height // 2
    base_bottom = base_top + base_height
    
    draw.rounded_rectangle(
        [base_left, base_top, base_right, base_bottom],
        radius=base_height // 2,
        fill=color
    )
    
    # Stand
    stand_width = size // 8
    stand_left = (size - stand_width) // 2
    stand_top = base_top
    stand_bottom = size - padding
    
    draw.rectangle(
        [stand_left, stand_top, stand_left + stand_width, stand_bottom],
        fill=color
    )
    
    # Add recording indicator if needed
    if recording:
        indicator_size = size // 4
        indicator_pos = (size - indicator_size - padding, padding)
        draw.ellipse(
            [indicator_pos[0], indicator_pos[1],
             indicator_pos[0] + indicator_size, indicator_pos[1] + indicator_size],
            fill='red'
        )
    
    return image

def create_icons():
    """Create icons for all platforms"""
    # Create icons directory if it doesn't exist
    os.makedirs('icons', exist_ok=True)
    
    # Windows icons (ICO format)
    normal_win = create_circle_icon(256, 'white')
    recording_win = create_circle_icon(256, 'white', recording=True)
    normal_win.save('icons/mic-windows.ico', format='ICO')
    recording_win.save('icons/mic-recording-windows.ico', format='ICO')
    
    # macOS icons (PNG format with black color)
    normal_mac = create_circle_icon(256, 'black')
    recording_mac = create_circle_icon(256, 'black', recording=True)
    normal_mac.save('icons/mic-macos.png', format='PNG')
    recording_mac.save('icons/mic-recording-macos.png', format='PNG')
    
    # Linux icons (PNG format with white color)
    normal_linux = create_circle_icon(256, 'white')
    recording_linux = create_circle_icon(256, 'white', recording=True)
    normal_linux.save('icons/mic-linux.png', format='PNG')
    recording_linux.save('icons/mic-recording-linux.png', format='PNG')

if __name__ == '__main__':
    create_icons() 