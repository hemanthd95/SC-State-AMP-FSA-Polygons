#!/usr/bin/env python3
"""Wave 3: ten more open farmers. Reuses wave2 robust NAIP QA;
same-FSA-farm controls are prioritized over an unreliable mailing address.
No source photo alone is accepted as a field polygon.
"""
import json
from pathlib import Path
import recovery49_wave2_registrations as wave
ROOT=Path(__file__).resolve().parents[1]
wave.OUT=ROOT/"analysis/recovery49_20261111/wave3"
wave.OUT.mkdir(parents=True,exist_ok=True)
wave.TARGETS=[
 ("Christine Berry Zeigler","Christine Berry Zeigler_FSA Map.pdf","1271/469/1","568 Nassau Drive, Bowman, SC 29018"),
 ("Lewis Gin","Lewis Gin_FSA Map.pdf","4706/11322/36","900 Magnolia Street, East Hampton, SC 29924"),
 ("Joe Hilliard","Joe Hillard_FSA_Map.pdf","13859/45814/20","157 Hollis Rd, Santee, SC 29142"),
 ("Arthur Cobbs","Arthur Cobbs_FSA Map.pdf","548/295/UNKNOWN","115 Prosperity Ln, Reevesville, SC 29471"),
 ("Brenda M. Harris","Brenda Harris_FSAmap.pdf","4943/4414/3","192 Old Spell Road, St George, SC 29477"),
 ("Jeremiah Conyers","Jeremiah Conyers Farm Map.pdf","948/2427/3","9407 Paxville Hwy, Manning, SC 29102"),
 ("Charles Manigault","Manigault Charles_FSAmap.pdf","1283/2004/UNKNOWN","165 Corn Flower Lane, Round O, SC 29452"),
 ("Edward Carson","Edward Carson_FSA Map.pdf","14291/46266/19,13","358 Amber Rd, North, SC 29112"),
 ("Morgan Summers","Morgan summers_FSA_Map.pdf","13225/6178/24","5953 Freedom Rd, Branchville, SC 29432"),
 ("Pashona Rendell","PashonnaRendell_FSA_Map.pdf","9231/7908/UNKNOWN","34 Mayland Drive, Summerton, SC 29148")
]
real_geocode=wave.geocode
def anchored_geocode(address):
  ans=real_geocode(address)
  if "Nassau Drive" in address:
    # Another verified physical field near same Excel address, only as a search anchor.
    ans.insert(0,dict(provider="NEAR_SAME_ADDRESS_PREVIOUS_BERRY_FIELD",
          lon=-80.6487298,lat=33.4276425,matched_address="568 Nassau Drive Bowman farm search"))
  if "Magnolia Street" in address and "East Hampton" in address:
    # Exact same FSA Farm 4706/Tract 11322 as Annette Weekley Field10.
    ans.insert(0,dict(provider="SAME_FSA_FARM_TRACT_PREVIOUSLY_REGISTERED",
       lon=-81.13247,lat=32.84736,matched_address="Farm 4706 Tract 11322 map anchor"))
  return ans
wave.geocode=anchored_geocode
if __name__=="__main__":wave.main()
