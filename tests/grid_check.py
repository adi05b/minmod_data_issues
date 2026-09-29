"""Phase 5: which NAD27->WGS84 operations PROJ can use here. Run with PROJ_NETWORK=OFF and =ON."""
import pyproj
from pyproj.transformer import TransformerGroup

print("network", pyproj.network.is_network_enabled())
g = TransformerGroup(4267, 4326, always_xy=True)
print(len(g.transformers), "available |", len(g.unavailable_operations), "unavailable")
for op in g.unavailable_operations[:5]:
    print(" ", op.name, [gr.short_name for gr in op.grids if not gr.available])
