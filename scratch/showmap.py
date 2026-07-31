import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "analysis" / "econ"))
from maplib import read_map
import re
def cores(path):
    b = pathlib.Path(path).read_bytes()
    # crude: field 4 records
    return None
for name in sys.argv[1:]:
    w,h,rows = read_map(f"maps/{name}.map26")
    print(f"== {name} {w}x{h}")
    ch = {0:'.',1:'#',2:'O'}
    for y,r in enumerate(rows):
        print(f"{y:2d} " + "".join(ch[c] for c in r))
    print("   " + "".join(str(x%10) for x in range(w)))
