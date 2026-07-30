import pathlib
import json, os, re, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import fixtures
from harness import ROOT, SCRATCH  # noqa: E402
cfg={"ores":[[x,1] for x in range(6,19,2)],"trunk_y":2,"trunk_w":4,"trunk_e":18,
     "first_harv_round":60,"add_every":120}
json.dump(cfg,open(f"{SCRATCH}/tcfg.json","w"))
env=dict(os.environ,FCODE_ECON_CFG=f"{SCRATCH}/tcfg.json")
out=subprocess.run(["uv","run","fcode","run","jon/probes/probe_trunk","common/donothingbot",fixtures.trunk(),
                    "--replay",f"{SCRATCH}/t.replay26"],cwd=ROOT,env=env,
                   capture_output=True,text=True).stderr
res={}; ev=[]
for l in out.splitlines():
    m=re.match(r"T (\d+) res=(\d+) scale=([\d.]+)",l)
    if m: res[int(m.group(1))]=(int(m.group(2)),float(m.group(3)))
    elif l.startswith(("HARV","TRUNK")): ev.append(l)
print("\n".join(ev))
harv_rounds=[int(re.search(r"r=(\d+)",e).group(1)) for e in ev if e.startswith("HARV")]
print("\nSteady-state rate measured in the last 60 rounds before each new harvester:")
print(f"{'n_harv':>6} {'window':>14} {'Ti/round':>9} {'expected(2.5n+2.5)':>19}")
for i,hr in enumerate(harv_rounds):
    n=i  # harvesters live during the window ending at hr
    a,b=hr-60,hr-5
    if a<10: continue
    rate=(res[b][0]-res[a][0])/(b-a)
    print(f"{n:>6} {f'{a}-{b}':>14} {rate:>9.3f} {2.5*n+2.5:>19.2f}")
# final window
last=max(res)
a,b=last-200,last-5
n=len(harv_rounds)
print(f"{n:>6} {f'{a}-{b}':>14} {(res[b][0]-res[a][0])/(b-a):>9.3f} {2.5*n+2.5:>19.2f}")
