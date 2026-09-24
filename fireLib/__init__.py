"""Wildland fire modeling on Earth Engine.

Earth Engine is a lazy, tile-parallel, **stateless** engine. Fire spread
is inherently **sequential** — a front advances over many timesteps, each
depending on the last. Most Earth Engine fire projects founder on that
seam, so this package draws the line explicitly rather than discovering
it late:

**Tier 1 — everything pixel-wise, in Earth Engine.** Fuels assembly,
terrain derivatives, fire-danger climatology, per-pixel fire behavior,
risk algebra. All embarrassingly parallel; this is where the value is.

**Tier 2 — cost-distance propagation, in Earth Engine.** Arrival-time
surfaces via ``ee.Image.cumulativeCost``, which is the Eikonal/minimum-
travel-time solution and needs no timestep loop at all. Documented
ceiling: it is isotropic.

**Tier 3 — the real simulators, outside.** FSim, FlamMap, FARSITE,
ELMFIRE. This package writes their inputs and reads their outputs. It
does not reimplement them.

The propagation insight worth stating up front, because it is what makes
Tier 2 practical::

    cost    = ee.Image(1).divide(ros)               # seconds per meter
    arrival = cost.cumulativeCost(ignition, 50000)  # seconds to each pixel
    frames  = [arrival.lte(t * dt) for t in range(1, 101)]

Least-accumulated-cost from a source **is** minimum travel time. A
hundred animation frames are a hundred thresholds of *one* image, not a
hundred iterations. Doing it as nested neighborhood operations instead
would require a 100-pixel halo on every tile, because each one expands
the required footprint by a pixel.

What this package will not do, stated so it can be designed around:

* **No true elliptical head-fire spread.** ``cumulativeCost`` assigns
  cost per *pixel*, not per *edge*, so it cannot express "cheap
  downwind, expensive upwind". Chaining short wind-blocks approximates
  directional behavior; it does not reproduce Huygens wavelets.
* **No coupled fire-atmosphere behavior.** Plume dynamics and
  downdraft-driven runs are WRF-Fire and QUIC-Fire territory.
* **No spotting.** Ember transport is stochastic and cost-distance
  cannot express it.
* **No replacement for a project-level FSim run.**
"""

from .wind import (
    UV_BANDS,
    WIND_10M_TO_20FT,
    wind_barbs,
    wind_blocks_from_forecast,
    wind_grid,
    wind_speed_direction,
    wind_uv,
)
from .behavior import (
    crown_fire_initiation,
    flame_length,
    rate_of_spread,
    ros_metric,
)
from .fuels import (
    CONTEXT_ASSETS,
    FUEL_ASSETS,
    RISK_ASSET,
    fuel_coverage,
    fuel_model_params,
    fuel_param_image,
    landfire_fuels,
    terrain_layers,
)
from .spread import (
    calibrate_cost_units,
    isochrones,
    spread_with_wind_blocks,
    transmission_matrix,
    travel_time,
)

__all__ = [
    # Fuels + terrain
    "landfire_fuels",
    "terrain_layers",
    "fuel_model_params",
    "fuel_param_image",
    "fuel_coverage",
    "FUEL_ASSETS",
    "CONTEXT_ASSETS",
    "RISK_ASSET",
    # Behavior
    "rate_of_spread",
    "ros_metric",
    "flame_length",
    "crown_fire_initiation",
    # Spread
    "travel_time",
    "isochrones",
    "spread_with_wind_blocks",
    "transmission_matrix",
    "calibrate_cost_units",
    "wind_uv",
    "wind_speed_direction",
    "wind_grid",
    "wind_barbs",
    "wind_blocks_from_forecast",
    "UV_BANDS",
    "WIND_10M_TO_20FT",
]

__version__ = "2026.9.4"
