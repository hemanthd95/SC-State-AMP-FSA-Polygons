"""Bounded, repeatable georeferencing diagnostics for the Nov 6 county batch.

These points are only search hints; success is not proof of the farm boundary.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import next_three_registration as reg

OUT = Path(__file__).resolve().parents[1] / 'analysis/allendale_bamberg_calhoun_20261106'
OUT.mkdir(parents=True, exist_ok=True)
reg.OUT = OUT

TARGETS = [
    ('Allendale', '3779', 'Tifanny Loadholt_FSA_Map.pdf', 1, -81.3224192, 33.0084896),
    # Samuel's spreadsheet has no latitude/longitude; shared producer address
    # provides a rough neighborhood only and must not be treated as farm GPS.
    ('Allendale', '3740', 'Samuel Lance JR.pdf', 1, -81.3224192, 33.0084896),
    ('Bamberg', '3523', 'Corey  Jacoby Crosby FSAmap.pdf', 1, -81.0501333, 33.2387299),
    ('Bamberg', '3524', 'John Henry Brabham_FSA_Map.pdf', 2, -81.6563, 33.7577),
    ('Calhoun', '3549', 'Jan Davis-Boneparte_FSA_Map.pdf', 1, -81.6580, 33.7591),
    ('Calhoun', '14280', 'Jaylon carson_FSA Map.pdf', 2, -80.4521, 33.6101),
]


def main():
    result=[]
    targets=[t for t in TARGETS if len(sys.argv)==1 or t[1] in sys.argv[1:]]
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks={pool.submit(reg.process,target):target for target in targets}
        for ft in as_completed(tasks):
            target=tasks[ft]
            try:r=ft.result()
            except Exception as exc:r={'county':target[0], 'farm_id':target[1], 'status':'PROCESSING_ERROR', 'error':str(exc)}
            result.append(r)
            (OUT/'registration_incremental.json').write_text(json.dumps(result,indent=2)+'\n')
            print('COMPLETED',target[0],target[1],r['status'],flush=True)
    (OUT/'registration_results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('BATCH_COMPLETE',len(result),flush=True)


if __name__=='__main__':main()
