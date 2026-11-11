#!/usr/bin/env python3
"""Wave 4: address-first photo registration attempts for 10 further YEAR2 farmers.
Uses original FSA PDFs and the same USGS NAIP/SIFT QA gates as wave2.
No producer is marked complete without exact enrolled Farm/Tract/Field trace.
"""
from pathlib import Path
import recovery49_wave2_registrations as engine
ROOT=Path(__file__).resolve().parents[1]
engine.OUT=ROOT/"analysis/recovery49_20261111/wave4"
engine.OUT.mkdir(parents=True,exist_ok=True)
engine.TARGETS=[
 ("Brandon Dingle","Brandon dingle FSAmap.pdf","6749/6174/UNSPECIFIED",
    "2580 Joseph Lemon and Dingle Rd Manning, SC 29102"),
 ("Calvin Blair","Calvin_Blair_FSA_Map.pdf","3603/848/3",
    "1033 Armour Hill Dr, Pinewood, SC 29125"),
 ("Everett Rendell","Everett Rendell FSAmap.pdf","1568/1083/UNSPECIFIED",
    "34 Mayland Dr, Summerton, SC 29148"),
 ("Charles Bright Jr.","Bright, Charles, JR_ FSAmap.pdf","2715/3022/UNSPECIFIED",
    "16047 ACE Basin Parkway, Jacksonboro, SC 29452"),
 ("Angela Solomon","Angela_Solomon_FSA_Map.pdf","5661/5039/18",
    "2251 Magnolia Street, Orangeburg, SC 29115"),
 ("Jasper Summers","Jasper Summers FSA Map.pdf","13709/45508/UNSPECIFIED",
    "299 Greywood Dr, Branchville, SC 29432"),
 ("Jaylon Carson","Jaylon carson_FSA Map.pdf","14291/46266/18;14280/46258/3",
    "2169 Bull Swamp Rd, North, SC 29112"),
 ("Joseph Gadson","Joseph Gadson_FSAmap.pdf","UNSPECIFIED/UNSPECIFIED/UNSPECIFIED",
    "1942 Bonner Ave, Santee, SC 29142"),
 ("Louie Johnson","Louie Johnson FSA_Map.pdf","8242/5134/2",
    "596 Chestnut St, Orangeburg, SC 29115"),
 ("Tywone Hilliard","Tywone Hillard_FSA_Map.pdf","1064/3623/UNSPECIFIED;3826/3624/UNSPECIFIED",
    "157 Hollis Rd, Santee, SC 29142")
]
# For multiple pages, try the first two source pages and retain which
# actually matched; a matching page still needs farm ID reconciliation.
original=engine.core.source_views
def all_candidate_pages(source,page):
 import fitz
 with fitz.open(source) as doc:count=len(doc)
 return [v for p in range(1,min(2,count)+1) for v in original(source,p)]
engine.core.source_views=all_candidate_pages
if __name__=="__main__":engine.main()
