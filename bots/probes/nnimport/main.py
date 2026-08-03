"""NN-3: what can a bot actually import? Answers the "can numpy be shipped" question.

Tiers tested:
  A stdlib pure-Python NOT pre-imported by the engine
  B stdlib C-EXTENSION not pre-imported by the engine  (lzma/_lzma, sqlite3/_sqlite3,
    ctypes, _ssl, unicodedata) -- if these load, the sandbox can dlopen a .so at all
  C third-party pure-Python present in site-packages (click, rich)
  D sibling module shipped in the bot's own zip/dir (helper.py)
  E filesystem visibility (open, __file__, sys.path, zipimport, importlib machinery)
"""

import sys

from fcode import Controller, EntityType


def _try(expr):
    try:
        v = eval(expr)  # noqa: S307 - probe only
        return "OK(" + str(v)[:24] + ")"
    except Exception as exc:
        return type(exc).__name__


RESULTS = []
for _label, _expr in [
    ("A:fractions", "__import__('fractions').__name__"),
    ("A:secrets", "__import__('secrets').__name__"),
    ("B:lzma", "__import__('lzma').__name__"),
    ("B:_lzma", "__import__('_lzma').__name__"),
    ("B:sqlite3", "__import__('sqlite3').__name__"),
    ("B:ctypes", "__import__('ctypes').__name__"),
    ("B:_ssl", "__import__('_ssl').__name__"),
    ("B:unicodedata", "__import__('unicodedata').__name__"),
    ("B:_decimal", "__import__('_decimal').__name__"),
    ("C:click", "__import__('click').__version__"),
    ("C:rich", "__import__('rich').__name__"),
    ("C:numpy", "__import__('numpy').__version__"),
    ("D:helper", "__import__('helper').VALUE"),
    ("E:open", "open"),
    ("E:memoryview", "memoryview"),
    ("E:__file__", "__file__"),
    ("E:zipimport", "__import__('zipimport').__name__"),
    ("E:importlib.util", "__import__('importlib.util', fromlist=['x']).__name__"),
    ("E:sys.path", "len(sys.path)"),
    ("E:sys.path0", "sys.path[0] if sys.path else 'EMPTY'"),
    ("E:ExtFileLoader", "__import__('importlib.machinery', fromlist=['x']).ExtensionFileLoader"),
    ("E:sys.modules_n", "len(sys.modules)"),
]:
    RESULTS.append(_label + "=" + _try(_expr))


class Player:
    def __init__(self):
        self.sent = 0

    def run(self, ct: Controller) -> None:
        if ct.get_entity_type() != EntityType.CORE:
            return
        r = ct.get_current_round()
        chunks = [RESULTS[i:i + 8] for i in range(0, len(RESULTS), 8)]
        if r <= len(chunks):
            pass
        if r == 3:
            ct.resign(" ".join(chunks[0] + chunks[1])[:499])
