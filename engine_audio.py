"""Low-frequency procedural diesel tank engine.

Unlike pure rising sine waves, this uses periodic exhaust thumps and muted
mechanical texture. 1-second buffers loop seamlessly; crossfaded engine-load
layers are kept much closer in pitch to avoid the earlier sci-fi whine.
"""
from array import array
import math

import pygame

from audio import SAMPLE_RATE


ENGINE_RATES = (21, 22, 24)


def engine_loop(rpm_hz):
    """Generate one-second, low-register thumping exhaust cycle."""
    samples = array("h")
    base = max(6, min(48, int(round(rpm_hz))))
    for i in range(SAMPLE_RATE):
        t = i / SAMPLE_RATE
        phase = math.tau * base * t
        if base == 21:
            # Preserve the original idle tone that tested well.
            pulse = (math.sin(phase) * 0.55
                     + math.sin(phase * 2) * 0.18
                     + math.sin(phase * 3) * 0.10
                     + math.sin(phase * 7) * 0.06
                     + math.sin(math.tau * (base // 3) * t) * 0.12)
            value = max(-1.0, min(1.0, pulse * 0.72))
        else:
            # When accelerating, switch to muted combustion knocks instead of
            # high pitched oscillator notes.
            thump = max(0.0, math.cos(phase)) ** 6
            low = math.sin(phase) * 0.15 + math.sin(phase * 2) * 0.055
            pulse = (thump - 0.22) * 0.88
            chatter = (math.sin(math.tau * 71 * t) *
                       math.sin(math.tau * 37 * t)) * 0.048
            rumble = math.sin(math.tau * 7 * t) * 0.05
            value = max(-1.0, min(1.0, (pulse + low + chatter + rumble) * 0.78))
        samples.append(round(value * 32767))
    return samples.tobytes()


def engine_mix(speed, throttle):
    """Three-layer volumes; quieter, lower-pitched diesel under load."""
    fraction = min(1.0, abs(speed) / 150.0)
    fraction = min(1.0, fraction + (0.06 if throttle else 0.0))
    if fraction <= 0.5:
        blend = fraction * 2
        return (0.22 * (1 - blend), 0.29 * blend, 0.0)
    blend = (fraction - 0.5) * 2
    return (0.0, 0.29 * (1 - blend), 0.30 * blend)


class EngineAudio:
    def __init__(self, soundbank):
        self.enabled = bool(soundbank.enabled)
        self.bank = soundbank
        self.levels = [0.0, 0.0, 0.0]
        self.channels = []
        if not self.enabled:
            return
        try:
            pygame.mixer.set_reserved(3)
            for index, hz in enumerate(ENGINE_RATES):
                channel = pygame.mixer.Channel(index)
                loop = pygame.mixer.Sound(buffer=engine_loop(hz))
                channel.set_volume(0.0)
                channel.play(loop, loops=-1)
                self.channels.append((channel, loop))
        except (pygame.error, OSError, ValueError) as exc:
            print(f"Engine audio unavailable: {exc}")
            self.enabled = False
            for channel, _ in self.channels:
                channel.stop()

    def update(self, dt, speed, throttle, alive=True):
        if not self.enabled:
            return
        targets = engine_mix(speed, throttle)
        fade = min(1.0, max(0.0, dt) * 5.5)
        for index, (channel, _) in enumerate(self.channels):
            target = targets[index] if alive and not self.bank.muted else 0.0
            self.levels[index] += (target - self.levels[index]) * fade
            channel.set_volume(max(0.0, min(1.0, self.levels[index])))

    def stop(self):
        for channel, _ in self.channels:
            channel.stop()
