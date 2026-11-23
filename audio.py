"""Small self-contained procedural sounds; no external audio assets required.

The mixer is optional: a headless PC or unavailable sound device is silent.
"""
from array import array
import math
import random

import pygame

SAMPLE_RATE = 22050


def _synth(kind):
    settings = {
        "fire": (0.19, 500, 110, 0.70),
        "impact": (0.14, 180, 50, 0.48),
        "hit": (0.24, 270, 65, 0.68),
        "destroy": (0.75, 150, 24, 0.80),
        "wall_break": (0.52, 125, 30, 0.68),
    }
    duration, start_hz, end_hz, strength = settings[kind]
    count = int(SAMPLE_RATE * duration)
    samples = array("h")
    rng = random.Random({"fire": 3, "impact": 5, "hit": 7,
                         "destroy": 11, "wall_break": 13}[kind])
    phase = 0.0
    for i in range(count):
        t = i / max(1, count - 1)
        frequency = start_hz * (1 - t) + end_hz * t
        phase += math.tau * frequency / SAMPLE_RATE
        # Each event combines a falling pitch with a filtered/noisy transient.
        noise = rng.uniform(-1, 1)
        if kind == "fire":
            sound = math.sin(phase) * 0.65 + noise * (1 - t) * 0.55
        elif kind in ("destroy", "wall_break"):
            sound = math.sin(phase) * 0.4 + noise * 0.6
        else:
            sound = math.sin(phase) * 0.24 + noise * 0.75
        attack = min(1.0, i / max(1, int(0.003 * SAMPLE_RATE)))
        decay = (1.0 - t) ** (2.2 if kind == "fire" else 1.6)
        value = max(-1, min(1, sound * attack * decay * strength))
        samples.append(round(value * 32767))
    return samples.tobytes()


class SoundBank:
    def __init__(self):
        self.enabled = False
        self.muted = False
        self.sounds = {}
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=SAMPLE_RATE, size=-16,
                                  channels=1, buffer=512)
            # Generate mono buffers matching the signed-16-bit mixer.
            for event in ("fire", "impact", "hit", "destroy", "wall_break"):
                self.sounds[event] = pygame.mixer.Sound(buffer=_synth(event))
            pygame.mixer.set_num_channels(24)
            self.enabled = True
        except (pygame.error, OSError, ValueError) as exc:
            print(f"Sound unavailable, continuing silently: {exc}")

    def play(self, kind, distance=0.0):
        if not self.enabled or self.muted:
            return
        sound = self.sounds.get(kind)
        if sound is None:
            return
        channel = pygame.mixer.find_channel()
        if channel is not None:
            channel.set_volume(max(0.12, 1.0 - distance / 1100.0) * 0.7)
            channel.play(sound)

    def toggle_mute(self):
        self.muted = not self.muted
        return self.muted
