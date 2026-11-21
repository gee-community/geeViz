"""Per-pixel fire behavior — Rothermel surface spread and its consequences.

This is the part of fire modeling Earth Engine is genuinely *ideal* for.
Rothermel's rate of spread given a fuel bed, slope, wind and moisture is
a pure pixel-wise function: no neighbors, no iteration, no state. It maps
onto a tile-parallel engine perfectly, at CONUS scale, across as many
weather scenarios as you care to run.

The model (Rothermel 1972, INT-115) computes

    R = (I_R * xi * (1 + phi_w + phi_s)) / (rho_b * eps * Q_ig)

where ``I_R`` is reaction intensity, ``xi`` the propagating flux ratio,
``phi_w`` and ``phi_s`` the wind and slope factors, and the denominator
the heat sink. Everything here is in Rothermel's original English units
(tons/acre, ft, ft/min, BTU/lb) because the published coefficients are,
and converting the coefficients rather than the inputs is how sign and
magnitude errors get in. Conversion to metric happens once, at the edge,
in :func:`ros_metric`.

**On accuracy.** This is the surface-fire model. It does not include
crown fire (see :func:`crown_fire_initiation`), spotting, or any
fire-atmosphere coupling. Rothermel himself scoped it to a quasi-steady
fire spreading through continuous, uniform surface fuel — real fires
routinely violate every one of those. Treat the output as a physically
grounded index that is well correlated with observed spread, not as a
prediction of what a specific fire will do.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .fuels import fuel_param_image

logger = logging.getLogger(__name__)

#: Heat content of wood, BTU/lb. Rothermel's standard value; varies
#: little enough between species that per-fuel-model variation is not
#: worth the complexity here.
HEAT_CONTENT = 8000.0

#: Oven-dry particle density, lb/ft3.
PARTICLE_DENSITY = 32.0

#: Total and effective mineral content, fractions.
MINERAL_TOTAL = 0.0555
MINERAL_EFFECTIVE = 0.0100

#: tons/acre -> lb/ft2. 2000 lb per ton over 43,560 ft2 per acre.
TONS_ACRE_TO_LB_FT2 = 2000.0 / 43560.0

#: ft/min -> m/s.
FT_MIN_TO_M_S = 0.3048 / 60.0


def _img(x):
    import ee
    return x if hasattr(x, "bandNames") else ee.Image(float(x))


def rate_of_spread(fuels, terrain, *,
                   wind_speed_20ft,
                   moisture_1h=0.06,
                   moisture_live=1.50,
                   fbfm_band: str = "FBFM40",
                   wind_adjustment: float = 0.4):
    """Rothermel surface rate of spread, ft/min, as an ``ee.Image``.

    Args:
        fuels: Image carrying the fuel-model band (see
            :func:`~geeViz.fireLib.fuels.landfire_fuels`).
        terrain: Image carrying ``slope_tan`` (see
            :func:`~geeViz.fireLib.fuels.terrain_layers`).
        wind_speed_20ft: 20-ft wind speed in mi/h, as a number or an
            ``ee.Image``. GRIDMET's ``vs`` is 10 m in m/s — convert
            before passing it, or the result is wrong by roughly a
            factor of two and still looks reasonable.
        moisture_1h: Dead 1-hour fuel moisture, fraction (0.06 = 6%).
            GRIDMET ships ``fm100``/``fm1000`` as percentages.
        moisture_live: Live fuel moisture, fraction. 1.50 is a typical
            growing-season value; 0.60 or below is critically dry.
        fbfm_band: Name of the fuel-model band in ``fuels``.
        wind_adjustment: Factor converting 20-ft wind to midflame wind.
            0.4 is a common sheltered-surface default; unsheltered grass
            is nearer 0.6 and dense timber nearer 0.1-0.2. **This single
            number moves rate of spread more than almost any other
            input**, which is why it is an explicit argument rather than
            a constant.

    Returns:
        ``ee.Image`` band ``ros_ft_min``, masked where the fuel model is
        not in the parameter table and forced to zero on non-burnable
        models.

    Display:
        Use a fixed stretch, not ``tl.auto_viz``: rate of spread has a
        known physical range, and a fixed one keeps maps of different
        days or places comparable. Typical magnitudes (1 chain/h is
        about 1.1 ft/min): timber litter 1-10 ft/min, shrub 10-50, grass
        in wind 50-300 and more.

        * mixed fuels: ``{"min": 0, "max": 100}``
        * timber-dominated: ``{"min": 0, "max": 20}``
        * grass or shrub under strong wind: ``{"min": 0, "max": 200}``

        with a low-to-high fire palette, for example
        ``["ffffb2", "fecc5c", "fd8d3c", "f03b20", "bd0026"]``. Values
        above ``max`` show as the top color, which is the right reading.
    """
    import ee

    fbfm = ee.Image(fuels).select(fbfm_band)

    # Bed properties, looked up per pixel from the fuel-model raster.
    w_1h = fuel_param_image(fbfm, "w_1h").multiply(TONS_ACRE_TO_LB_FT2)
    w_10h = fuel_param_image(fbfm, "w_10h").multiply(TONS_ACRE_TO_LB_FT2)
    w_100h = fuel_param_image(fbfm, "w_100h").multiply(TONS_ACRE_TO_LB_FT2)
    w_live = fuel_param_image(fbfm, "w_live").multiply(TONS_ACRE_TO_LB_FT2)
    sav = fuel_param_image(fbfm, "sav")
    depth = fuel_param_image(fbfm, "depth")
    mx_dead = fuel_param_image(fbfm, "mx_dead")

    m_dead = _img(moisture_1h)
    m_live = _img(moisture_live)

    w_dead = w_1h.add(w_10h).add(w_100h)
    w_net = w_dead.add(w_live)

    # Bulk density and packing ratio.
    rho_b = w_net.divide(depth)
    beta = rho_b.divide(PARTICLE_DENSITY)
    beta_op = sav.pow(-0.8189).multiply(3.348)
    beta_ratio = beta.divide(beta_op)

    # Reaction intensity.
    #
    # A = 133 * sigma^-0.7913.  NOT 133/(sigma^1.5 + 495) -- an earlier
    # version had that and it is one of several coefficient slips that
    # together drove rate of spread to exactly zero across an entire
    # test landscape. Every term below is written to match the published
    # form so it can be checked against it line by line.
    a = sav.pow(-0.7913).multiply(133.0)
    # Gamma'_max = sigma^1.5 / (495 + 0.0594 * sigma^1.5)
    gamma_max = sav.pow(1.5).divide(
        sav.pow(1.5).multiply(0.0594).add(495.0))
    gamma = (gamma_max
             .multiply(beta_ratio.pow(a))
             .multiply(beta_ratio.multiply(-1).add(1).multiply(a).exp()))

    # Moisture damping. Clamped at 0 because the polynomial goes
    # negative past the moisture of extinction, and a negative damping
    # coefficient would flip the sign of the whole fire.
    rm = m_dead.divide(mx_dead).min(1.0)
    eta_m = (rm.multiply(-2.59).add(1)
             .add(rm.pow(2).multiply(5.11))
             .subtract(rm.pow(3).multiply(3.52))
             .max(0.0))

    # eta_s = 0.174 * S_e^-0.19, mineral damping.
    eta_s = min(0.174 * (MINERAL_EFFECTIVE ** -0.19), 1.0)

    # Net fuel load removes total mineral content.
    w_n = w_net.multiply(1.0 - MINERAL_TOTAL)

    i_r = gamma.multiply(w_n).multiply(HEAT_CONTENT) \
        .multiply(eta_m).multiply(eta_s)

    # Propagating flux ratio:
    #   xi = exp[(0.792 + 0.681 sigma^0.5)(beta + 0.1)] / (192 + 0.2595 sigma)
    xi = (sav.sqrt().multiply(0.681).add(0.792)
          .multiply(beta.add(0.1)).exp()
          .divide(sav.multiply(0.2595).add(192.0)))

    # Wind factor. Midflame wind in ft/min: mi/h -> ft/min is x88.
    #   C = 7.47 exp(-0.133 sigma^0.55)
    #   B = 0.02526 sigma^0.54
    #   E = 0.715 exp(-3.59e-4 sigma)
    u_mid = _img(wind_speed_20ft).multiply(88.0).multiply(wind_adjustment)
    c = sav.pow(0.55).multiply(-0.133).exp().multiply(7.47)
    b = sav.pow(0.54).multiply(0.02526)
    e = sav.multiply(-3.59e-4).exp().multiply(0.715)
    phi_w = (c.multiply(u_mid.max(0).pow(b))
             .multiply(beta_ratio.pow(e.multiply(-1))))

    # Slope factor. Uses TANGENT of slope, not degrees -- feeding
    # degrees here silently understates spread on steep ground.
    phi_s = terrain_slope_factor(terrain, beta)

    # Heat sink.
    #   epsilon = exp(-138 / sigma)      <- DIVIDED by sigma.
    #   Q_ig    = 250 + 1116 * M_f
    #
    # The epsilon slip is the one that zeroed everything: written as
    # exp(-138 * sigma), with sigma around 2000, it underflows to 0, the
    # heat sink collapses, and every pixel comes back 0 rather than
    # infinite -- a whole landscape that looks fireproof.
    eps = sav.pow(-1).multiply(-138.0).exp()
    q_ig = m_dead.multiply(1116.0).add(250.0)
    heat_sink = rho_b.multiply(eps).multiply(q_ig)

    ros = (i_r.multiply(xi).multiply(phi_w.add(phi_s).add(1))
           .divide(heat_sink))

    # Non-burnable fuels spread at exactly zero. Enforced rather than
    # left to the arithmetic: a zero-load bed divides by zero in the
    # heat sink and yields NaN or a spurious value.
    from .fuels import NON_BURNABLE
    burnable = fbfm.remap(list(NON_BURNABLE),
                          [0] * len(NON_BURNABLE), 1)
    ros = ros.multiply(burnable).max(0.0)

    return ros.rename("ros_ft_min")


def terrain_slope_factor(terrain, beta):
    """Rothermel slope factor ``phi_s``.

    Separated out because it is the single easiest place to introduce a
    silent error: the formula takes the **tangent** of slope, and slope
    rasters are almost always published in degrees. Passing degrees
    directly produces a number that is finite, positive, and far too
    small on steep ground — wrong in the direction that makes a fire
    look safer than it is.
    """
    import ee

    slope_tan = ee.Image(terrain).select("slope_tan")
    return beta.pow(-0.3).multiply(5.275).multiply(slope_tan.pow(2))


def ros_metric(ros_ft_min):
    """Convert rate of spread from ft/min to m/s.

    Kept as an explicit edge conversion. Rothermel's published
    coefficients are unit-bearing, so the calculation stays in English
    units throughout and converts exactly once, here.
    """
    import ee
    return ee.Image(ros_ft_min).multiply(FT_MIN_TO_M_S).rename("ros_m_s")


def flame_length(ros_ft_min, i_r=None, *, residence_time_min: float = 0.5):
    """Byram flame length in feet from rate of spread.

    Byram: ``FL = 0.45 * I^0.46`` with fireline intensity ``I`` in
    BTU/ft/s. Intensity is reaction intensity times residence time times
    spread rate.

    Flame length is what most risk products key on -- the 4 ft and 8 ft
    thresholds in Wildfire Risk to Communities are direct suppression
    interpretations: under 4 ft is generally attackable by hand crews,
    over 8 ft implies crowning or spotting and effectively rules out
    direct attack.
    """
    import ee

    ros = ee.Image(ros_ft_min)
    if i_r is None:
        # Without a reaction-intensity band, fall back to the common
        # empirical relation for typical fuels. Approximate by design;
        # pass i_r when it is available.
        fl = ros.multiply(0.45).pow(0.46).multiply(3.0)
    else:
        intensity = ee.Image(i_r).multiply(residence_time_min) \
            .multiply(ros).divide(60.0)
        fl = intensity.pow(0.46).multiply(0.45)
    return fl.rename("flame_length_ft")


def crown_fire_initiation(fuels, flame_length_ft, *,
                          cbh_band: str = "CBH",
                          cbh_scale: float = 0.1,
                          cc_band: str = "CC"):
    """Van Wagner crown-fire initiation: does the surface fire torch?

    A surface fire transitions to crown fire when its intensity is
    sufficient to ignite the canopy base. The controlling geometry is
    **canopy base height** — the vertical gap between surface flames and
    the lowest live crown fuel.

    Args:
        cbh_scale: LANDFIRE stores canopy base height as **metres x 10**
            so it can be an integer raster, so 0.1 converts to metres.
            Getting this wrong by a factor of ten produces a canopy
            10x too high and a landscape that never torches.
        cc_band: Canopy cover band. Where ``fuels`` has it, a pixel with
            0 cover has no canopy and cannot torch, whatever its CBH.

    Returns:
        ``ee.Image`` band ``crown_initiation`` — 1 where the surface
        fire is expected to reach the canopy base, 0 otherwise
        (including wherever there is no canopy).
    """
    import ee

    fuels = ee.Image(fuels)
    cbh = fuels.select(cbh_band)
    cbh_ft = cbh.multiply(cbh_scale).multiply(3.28084)
    # LANDFIRE codes "no canopy" as CBH 0 and CC 0. Compared bare, a
    # 0 ft canopy base is reached by any flame, so every grass pixel
    # would torch.
    canopy = cbh.gt(0)
    canopy = canopy.And(ee.Image(ee.Algorithms.If(
        fuels.bandNames().contains(cc_band),
        fuels.select([cc_band]).gt(0),
        ee.Image(1))))
    # Torching when flame length reaches the canopy base.
    return (ee.Image(flame_length_ft).gte(cbh_ft).And(canopy)
            .rename("crown_initiation"))
