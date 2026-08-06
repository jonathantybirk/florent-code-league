"""Channel feasibility check for the passability sweep.

Two questions, both about how much data a probe can get out:
  1. Is resign_message truncated?  We resign with a 1200-char string whose every
     20th char is a landmark digit, so the printed length and the last landmark
     tell us the true cap.
  2. Can a bot write a file?  If yes, the passability table needs no encoding
     tricks at all and can be dumped in full.
"""

import os

from fcode import Controller, EntityType

OUT = os.environ.get("PTIO_OUT", "") or (
    "C:/Users/edlun/AppData/Local/Temp/claude/"
    "c--Users-edlun-Desktop-lucky-shots-Hackathons-florent-code-league/"
    "69495691-95ef-4878-adf9-aeca64f3e3b5/scratchpad/ptio.txt"
)


class Player:
    def __init__(self):
        self.done = False

    def run(self, ct: Controller) -> None:
        if self.done or ct.get_entity_type() != EntityType.CORE:
            return
        self.done = True

        # --- file-write feasibility ---
        io_note = "IO=?"
        try:
            with open(OUT, "w", encoding="utf-8") as fh:
                fh.write("PTIO file channel works. round=%d\n" % ct.get_current_round())
            io_note = "IO=OK"
        except Exception as exc:
            io_note = "IO=%s" % type(exc).__name__

        # --- resign-length feasibility: landmarks every 20 chars ---
        chunks = []
        for i in range(60):
            chunks.append("%03d................." % i)  # 3 + 17 = 20 chars
        payload = "".join(chunks)  # 1200 chars
        ct.resign("LEN1200|" + io_note + "|" + payload + "|END")
