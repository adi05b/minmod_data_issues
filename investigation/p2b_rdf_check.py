"""Problem 2, Part B: the KG export must not change.

Compares every mineral-site TTL file of two local ETL outputs as a sorted multiset
of lines, with the random node ids (mr:LocationInfo_<uuid>, mr:CandidateEntity_<uuid>,
...) normalised. Two runs of the same code already differ byte-for-byte because of
those ids, so a byte comparison proves nothing either way.

    python3 investigation/p2b_rdf_check.py kgdata-p2 kgdata-p2-after
"""

import glob
import re
import sys
from pathlib import Path

UUID = re.compile(r"_[0-9a-f]{8}_[0-9a-f]{4}_[0-9a-f]{4}_[0-9a-f]{4}_[0-9a-f]{12}")
a, b = (Path(x) / "data/mineral-sites/kg" for x in sys.argv[1:3])
files = sorted(Path(f).relative_to(a) for f in glob.glob(str(a / "*/*.ttl")))
assert files == sorted(Path(f).relative_to(b) for f in glob.glob(str(b / "*/*.ttl")))
diff, lines = [], 0
for f in files:
    la = sorted(UUID.sub("_UUID", l) for l in open(a / f, encoding="utf-8"))
    lb = sorted(UUID.sub("_UUID", l) for l in open(b / f, encoding="utf-8"))
    lines += len(la)
    if la != lb:
        diff.append(str(f))
print(f"{len(files)} TTL files, {lines:,} lines compared; files that differ: {len(diff)} {diff[:5]}")
