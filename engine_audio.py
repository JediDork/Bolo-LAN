"""Procedural looped tank engine sound with speed-responsive crossfading.

No sample assets or streaming; three tonal loops blend on independent reserved
mixer channels. Sound is only the local tank and does not change gameplay.
"""
from array import array
import math
import random

import pygame

from audio import SAMPLE_RATE


def engine_loop(rpm_hz):
    """Generate one-second seamless looping engine waveform at integer Hz."""
    count = SAMPLE_RATE
    values = array("h")
    # Integer cycles make both ends match for seamless looping.
    base = round(rpm_hz)
    for i in range(count):
        time = i / SAMPLE_RATE
        crank = math.tau * base * time
        # Exhaust pulses, mechanical rattle and a quiet low-frequency drone.
        pulse = math.sin(crank) * 0.55
        pulse += math.sin(crank * 2) * 0.18
        pulse += math.sin(crank * 3) * 0.10
        pulse += math.sin(crank * 7) * 0.06
        pulse += math.sin(math.tau * (base // 3) * time) * 0.12
        values.append(round(max(-1, min(1, pulse * 0.72)) * 32767))
    return values.tobytes()


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
            for index, hz in enumerate((21, 34, 49)):
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
        fraction = min(1.0, abs(speed) / 150.0)
        load = 0.10 if throttle else 0.0
        fraction = min(1.0, fraction + load)
        # Continuous equal-power-ish crossfade between idle, cruise and revs.
        idle = max(0.0, 1.0 - fraction * 2)
        mid = max(0.0, 1.0 - abs(fraction - 0.48) * 2.15)
        high = max(0.0, (fraction - 0.35) / 0.65)
        targets = [idle * 0.22, mid * 0.32, high * 0.34]
        fade = min(1.0, max(0, dt) * 5.5)
        for index, (channel, _) in enumerate(self.channels):
            target = targets[index] if alive and not self.bank.muted else 0.0
            self.levels[index] += (target - self.levels[index]) * fade
            channel.set_volume(max(0.0, min(1.0, self.levels[index])))

    def stop(self):
        for channel, _ in self.channels:
            channel.stop()
