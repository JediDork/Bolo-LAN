"""Fixed-size competitive viewport mapped to any fullscreen display.

Every client renders the same logical 1200x760 pixels, regardless of its
monitor size. Extra screen area is black letterboxing, not additional map.
"""


def viewport(display_width, display_height, logical_width=1200, logical_height=760):
    if min(display_width, display_height, logical_width, logical_height) <= 0:
        raise ValueError("Screen and logical dimensions must be positive")
    scale = min(display_width / logical_width, display_height / logical_height)
    draw_width = max(1, round(logical_width * scale))
    draw_height = max(1, round(logical_height * scale))
    left = (display_width - draw_width) // 2
    top = (display_height - draw_height) // 2
    return left, top, draw_width, draw_height


def to_logical(mouse_pos, view, logical_width=1200, logical_height=760):
    """Map fullscreen pointer to fixed game coordinates (including bars)."""
    mx, my = mouse_pos
    left, top, width, height = view
    return ((mx - left) * logical_width / width,
            (my - top) * logical_height / height)
