"""
Animation utilities — easing functions and interpolation for smooth animations.

Used by motion graphics, infographics, Ken Burns effect, and transitions.
"""

import math


def ease_out_cubic(t):
    """Fast start, slow end. Great for elements entering the screen."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_cubic(t):
    """Smooth acceleration and deceleration. Great for fade transitions."""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4.0 * t * t * t
    else:
        return 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


def ease_out_quad(t):
    """Gentle deceleration. Subtler than cubic."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 2


def ease_out_bounce(t):
    """Bounce effect at the end. Great for pop-in elements."""
    t = max(0.0, min(1.0, t))
    if t < 1.0 / 2.75:
        return 7.5625 * t * t
    elif t < 2.0 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    elif t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    else:
        t -= 2.625 / 2.75
        return 7.5625 * t * t + 0.984375


def smooth_step(t):
    """Hermite interpolation — smooth start and end."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def interpolate(start, end, t, easing=None):
    """
    Interpolate between two values with optional easing.

    Args:
        start: Start value (number)
        end: End value (number)
        t: Progress 0.0 to 1.0
        easing: Easing function (e.g. ease_out_cubic). None = linear.

    Returns:
        Interpolated value
    """
    if easing:
        t = easing(t)
    else:
        t = max(0.0, min(1.0, t))
    return start + (end - start) * t
