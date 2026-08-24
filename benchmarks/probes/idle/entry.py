"""Benchmark probe: does absolutely nothing. Named entry.py so tournament
discovery (which globs for main.py) never registers probes as rated bots."""


class Player:
    def run(self, ct):
        pass
