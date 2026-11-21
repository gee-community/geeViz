/**
 * Animated wind particles for geeViz, in the style of windy.com.
 *
 * Two layers make the picture, and the raster is the louder one: a
 * smooth speed field underneath (an ordinary geeViz image layer,
 * bicubic-resampled and queryable) with thin fading trails over the
 * top. This file draws only the trails.
 *
 * ---------------------------------------------------------------------
 * WHERE THE NUMBERS COME FROM
 * ---------------------------------------------------------------------
 * From the TILES, decoded. Earth Engine renders u and v into the red and
 * green channels of ordinary PNG map tiles, linearly stretched from
 * WIND_TILE_MIN/MAX m/s onto 0..255 (see geeViz.weather.windTiles). The
 * client fetches the tiles it is looking at, reads their pixels through
 * an offscreen canvas, and inverts the stretch.
 *
 * The stretch is HARD-CODED here and in Python, deliberately. It is the
 * one number both sides must agree on, and a mismatch does not throw --
 * it yields wrong-but-plausible winds, which look like weather rather
 * than like a bug.
 *
 * The predecessor shipped a JSON lattice sampled once over a fixed
 * region. It worked, but panning past the edge of that region simply
 * stopped the animation, and a continent's worth of lattice was ~200 KB
 * on the wire. Tiles stream with the view instead: pan anywhere, at any
 * zoom, and the data follows.
 *
 * ---------------------------------------------------------------------
 * ATTACHMENT
 * ---------------------------------------------------------------------
 * The encoded image is added as a normal geeImage layer, so the viewer
 * mints its tile URL and builds a real layer-list entry (checkbox,
 * opacity). This file then takes the layer OFF the map -- the raw RGB is
 * nonsense to look at -- and keeps its `getTileUrl` to fetch tiles
 * numerically.
 *
 * `layerObj` is declared as a top-level `let`, so it lives in the global
 * LEXICAL environment and is NOT a property of `window`; a bare
 * reference resolves it while `window.layerObj` is undefined.
 *
 * ---------------------------------------------------------------------
 * COST
 * ---------------------------------------------------------------------
 * A real animation loop, so it must not run unseen: it stops when the
 * layer is unchecked and when the page is hidden. An invisible rAF loop
 * draining a battery is how this kind of layer becomes a regret.
 */
(function (global) {
  "use strict";

  // FALLBACK ONLY. The live values arrive per layer in viz
  // (windTileMin/windTileMax) straight from geeViz.weather, so Python is
  // the single source of truth and the two cannot drift. These stand in
  // if a layer is somehow missing them.
  var TILE_MIN = -40.0;
  var TILE_MAX = 40.0;
  var TILE_PX = 256;

  // Side of the palette-mapped tile the speed raster paints, in pixels.
  //
  // Deliberately COARSER than the tile it reads. The forecast grid is
  // 0.25 degrees (GFS) -- about 28 km -- and at zoom 4 a tile pixel is
  // roughly 2.4 km, so the tile is already a ~10x upsampling of the
  // data before anything is drawn. Painting it back at full 256 is
  // 65,536 palette lookups per tile, ~3 million across a full-screen
  // view, and repeating that on every step of a playing lapse froze the
  // tab outright. At 64 it is 4,096 per tile, sixteen times less, and
  // still finer than the numbers underneath; the browser's own scaling
  // smooths it on the way up, which is what the full-resolution version
  // was paying to do by hand.
  var RASTER_PX = 64;

  // How far off-canvas a particle may drift before it is recycled.
  // Enough that a trail entering the view is already grown, small
  // enough that nothing far outside keeps pulling tiles.
  var CULL_MARGIN = 64;

  // Grid spacing of the prebuilt field, in canvas pixels. Not a viz knob:
  // the forecast grids are 0.25 deg (GFS) and 0.1 deg (WeatherNext), and
  // at every map zoom an 8 px cell is already finer than the data, so
  // there is nothing to gain by tuning it and a great deal of build cost
  // to lose. fieldAt interpolates across it, so the flow stays smooth.
  var FIELD_SPACING = 8;

  // Ceiling on the zoom of the u/v tiles fetched. Also not a viz knob.
  // Tiles track the map so Earth Engine's bicubic lands near display
  // resolution; past zoom 10 a tile pixel is under 150 m against a 28 km
  // grid, which is pure upsampling. The field build is bounded to the
  // viewport, so this governs waste at extreme zoom, nothing more.
  var MAX_TILE_ZOOM = 10;

  // How many times a failed tile is re-requested before it is accepted
  // as genuinely absent. Without this one transient error left a
  // tile-shaped hole in the field for the life of the page.
  var TILE_RETRIES = 3;

  // How many frames ahead of the one on screen to warm. See
  // warmNextFrames: 2 covers the viewer's 666 ms step with room to
  // spare without turning a wide view into a request storm.
  var WARM_FRAMES = 2;

  // Floor on the wait between attempts at a field that came out
  // INCOMPLETE, and the share of the clock rebuilding may take.
  //
  // buildField is ~34,000 cells on a full-screen map, each an inverse
  // projection plus a tile lookup -- measured at ~220 ms with every tile
  // already decoded. Retrying that at the animation rate asks for
  // several seconds of main thread per second of wall clock, which is
  // why a time lapse felt like a GPU problem when it is entirely CPU.
  //
  // A fixed wait cannot work: any constant shorter than the build lets
  // the rebuilds run back to back. So the back-off is measured in
  // BUILDS, not milliseconds -- wait REBUILD_DUTY times however long
  // the last one actually took, which holds the cost near 1/(1+duty) of
  // the thread on any machine and any window size. The floor only
  // matters for small maps where a build is genuinely cheap.
  // How long an opacity change takes to land. A slider drags in 0.05
  // steps and a playing lapse re-raises a frame on every step, so
  // applying either instantly reads as a jump rather than as a control.
  // Short enough not to feel laggy, long enough to stop the flicker.
  var FADE_MS = 220;

  var REBUILD_MS = 150;
  var REBUILD_DUTY = 2;

  // Alpha bands across a trail. Not a viz knob: more bands cost a full
  // pass over every particle each and buy nothing the eye can see, and
  // fewer start to show as stripes along the streak.
  var TRAIL_BANDS = 8;

  // Target frame interval, milliseconds. cambecc's windy.js runs its
  // loop at 30fps for the same reason we do.
  //
  // Streak length is trailLength x speed, and apparent motion is speed
  // x frame rate -- so at a fixed 60fps the trail cannot be shortened
  // without speeding the field up. Halving the frame rate lets the
  // trail halve and the step double, which leaves length AND motion
  // exactly as they were while drawing a quarter as many segments per
  // second. The four defaults below are set as one group; changing any
  // of them alone changes the look.
  //
  // A steady 30 also reads better than an unsteady 50: irregular frame
  // times are what the eye registers as choppy.
  var FRAME_MS = 1000 / 30;

  var adopted = Object.create(null);
  var rafId = null;
  var lastFrameAt = 0;
  var bound = false;

  // Whether the map element is actually on screen.
  //
  // document.hidden already stops the animation when the TAB is in the
  // background, but it says nothing about a visible tab scrolled past
  // the map — a long report page, a notebook cell above the fold, a
  // dashboard where the map is one panel among several. There the
  // particles keep integrating a vector field and repainting a canvas
  // nobody can see, which on a laptop is a fan spinning up for nothing.
  //
  // Defaults to true so that a browser without IntersectionObserver, or
  // a map that is never observed, behaves exactly as before rather than
  // silently never animating.
  var inView = true;

  // One <style> for the two opacity sliders; see injectSliderStyle.
  var styleInjected = false;
  var STYLE_ID = "geeviz-wind-particles-style";

  /**
   * The tile-URL builder on a google.maps.ImageMapType.
   *
   * The viewer constructs the layer as
   * ``new google.maps.ImageMapType({getTileUrl: fn})``, but the Maps API
   * stores that callback under a MINIFIED name -- observed as ``sh`` --
   * so ``layer.getTileUrl`` is undefined. The minified name changes
   * between Maps releases, and ``getTile()`` returns a container DIV
   * whose <img> is populated asynchronously, so neither is dependable.
   *
   * Probe instead: call each own function with a throwaway coordinate
   * and keep the one that answers with a URL string. Version-proof, and
   * it validates itself rather than trusting a name.
   */
  function findTileUrlFn(mapType) {
    if (typeof mapType.getTileUrl === "function") {
      return mapType.getTileUrl.bind(mapType);
    }
    for (var k in mapType) {
      if (typeof mapType[k] !== "function") continue;
      try {
        var r = mapType[k]({ x: 0, y: 0 }, 0);
        if (typeof r === "string" && /^https?:\/\//.test(r)) {
          return mapType[k].bind(mapType);
        }
      } catch (e) { /* not it */ }
    }
    return null;
  }

  /**
   * Take the encoded RGB off the map, and settle the viewer's spinner.
   *
   * Two things the viewer does not expect from us.
   *
   * The u/v tiles are an ENCODING, not a picture -- left visible they
   * paint the world flat red and green. So the ImageMapType comes off
   * the overlay stack. But the viewer re-adds it from scratch every
   * time the layer is unchecked and re-checked
   * (``overlayMapTypes.setAt(...)`` in its visibility handler), and by
   * then this module has already adopted the layer and skips it -- so
   * the raster came back and stayed. Detaching has to be repeatable,
   * and cheap enough to run on every refresh tick.
   *
   * The spinner is handled separately, by :func:`reportProgress`.
   */
  function detach(L) {
    if (!L || typeof L.layerId !== "number") return;
    try {
      // setAt(layerId, null) -- the SAME call the viewer's own turnOff
      // makes, and for the same reason.
      //
      // This used to scan the array and removeAt() the matching entry.
      // That works on its own layer and corrupts every other one:
      // overlayMapTypes is positional, each layer owns the fixed slot
      // recorded in layer.layerId, and removeAt SHIFTS everything above
      // it down one while all those layerId values stay put. After a
      // single detach, layerId N addressed the tiles of layer N+1 --
      // so checking one layer's box hid a different layer's raster, and
      // updateMapLayerOrder re-added rasters at slots that no longer
      // meant what it thought.
      //
      // Nothing in the viewer removeAt()s a layer slot. The only
      // removeAt it does is the labels overlay, which lives at
      // Object.keys(layerObj).length -- past every layer slot, so it
      // shifts nothing.
      global.map.overlayMapTypes.setAt(L.layerId, null);
    } catch (e) {}
  }

  /**
   * Report tile progress to the viewer, honestly.
   *
   * The viewer sets ``layer.loading = true`` inside its own
   * ``getTileUrl`` and clears it when the ImageMapType fires
   * ``tilesloaded``. This module calls ``getTileUrl`` directly -- that
   * is how it fetches tiles -- and has taken the map type off the map,
   * so the event never fires. Both halves are ours, so reporting is too.
   *
   * The first cut simply forced ``loading = false`` once. That stopped
   * the spinner spinning forever, but it also meant the layer NEVER
   * reported loading again: panning to fresh ground fetches a new batch
   * of tiles and the status bar showed nothing happening. So the state
   * is derived from the actual in-flight count instead of pinned.
   *
   * ``burst`` is the number of tiles requested since the queue was last
   * empty, which is what makes the percentage move rather than jump: it
   * resets on each pan, so a pan reads 0..100 over its own batch rather
   * than as a fraction of every tile ever cached.
   */
  function reportProgress(st) {
    var reg = registry();
    var L = reg && reg[st.id];
    if (!L) return;

    var inflight = st.inflight || 0;
    var burst = st.burst || 0;
    // A hidden layer reports 0, which clears the white fill from its row.
    // The viewer's own branches do this (`layer.percent = 0` wherever a
    // layer is hidden); reporting a flat 100 left this row painted while
    // every other unchecked layer went blank.
    var visible = L.visible !== false;
    var loading = visible && inflight > 0;
    var percent = !visible ? 0
      : (loading
         ? Math.max(5, Math.round((100 * (burst - inflight)) / burst))
         : 100);

    if (L.loading === loading && L.percent === percent) return;
    L.loading = loading;
    L.percent = percent;

    // The viewer derives both element ids from the layerObj key.
    var eid = st.id;
    try {
      if (global.$) {
        var sp = global.$("#" + eid + "-spinner2");
        if (loading) sp.show(); else sp.hide();
      }
    } catch (e) {}

    // The white fill across the layer row. The viewer paints this from
    // a CLOSURE -- ``updateProgress`` is defined per layer and captures
    // its own ``layer`` and container id, so it is not reachable from
    // here. (The global of the same name is a different function taking
    // ``(id, val)``; calling it did nothing, which is why the bar sat
    // still after the first load.) Painting the same gradient directly
    // is the only way in, and it must match the viewer's exactly or the
    // row will look different from every other layer.
    try {
      if (global.$) {
        global.$("#" + eid + "-layer-container").css(
          "background",
          "-webkit-linear-gradient(left, #FFF, #FFF " + percent +
          "%, transparent " + percent + "%, transparent 100%)");
      }
    } catch (e) {}

    // The counter in the status bar IS a global. Ask it to recount
    // rather than adjusting it here and risking a drift.
    try {
      if (typeof global.updateGEETileLayersDownloading === "function") {
        global.updateGEETileLayersDownloading();
      }
    } catch (e) {}
  }

  /** One tile entered the queue. */
  function tileStarted(st) {
    st.inflight = (st.inflight || 0) + 1;
    // A burst is a batch of requests bracketed by an empty queue -- a
    // pan, typically. Counting from zero each time is what lets the
    // percentage climb instead of creeping toward an ever-growing total.
    st.burst = (st.inflight === 1) ? 1 : (st.burst || 0) + 1;
    reportProgress(st);
  }

  /** ...and one left it, successfully or not. Both must count, or a
   *  single 404 leaves the layer loading forever. */
  function tileFinished(st) {
    st.inflight = Math.max(0, (st.inflight || 1) - 1);
    reportProgress(st);
  }

  /**
   * The viewer's query table.
   *
   * Same trap as ``registry`` below: ``queryObj`` is declared with
   * ``let`` at the top level, so it lives in the global LEXICAL
   * environment and is NOT a property of ``window``. Reading
   * ``global.queryObj`` returns undefined and the retarget silently
   * never happens -- the layer keeps working and the inspector keeps
   * reporting the u/v encoding as if it were wind.
   */
  function queries() {
    try {
      if (typeof queryObj !== "undefined" && queryObj) return queryObj;
    } catch (e) { /* declared later */ }
    return global.queryObj || null;
  }

  function registry() {
    try {
      if (typeof layerObj !== "undefined" && layerObj) return layerObj;
    } catch (e) { /* declared later */ }
    return global.layerObj || null;
  }

  // ---- Web Mercator -------------------------------------------------

  function lonToTileX(lon, z) {
    return ((lon + 180) / 360) * Math.pow(2, z);
  }

  function latToTileY(lat, z) {
    var r = (lat * Math.PI) / 180;
    return ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) *
           Math.pow(2, z);
  }

  // ---- tile cache ---------------------------------------------------

  /**
   * Decoded pixels for one tile, or null while it loads.
   *
   * Tiles are fetched once and kept. `crossOrigin` is required: without
   * it the canvas is tainted and getImageData throws a SecurityError, so
   * every decode silently yields nothing.
   */
  function getTile(st, z, x, y, frame) {
    // Keyed by FRAME as well as tile. One overlay serves every frame of
    // a time lapse, so without the prefix frame 2 would read frame 1's
    // decoded pixels out of the cache and the wind would stop changing
    // while the slider moved.
    //
    // `frame` names a frame OTHER than the one on screen, which is how
    // the next hours are warmed before the lapse reaches them. A warm
    // fetch is deliberately QUIET: it must not touch st.inflight, because
    // buildField reads that to decide whether the CURRENT frame is fully
    // resolved. Counting prefetches there would leave every build looking
    // incomplete and the field key would never be stamped.
    var quiet = frame !== undefined && frame !== st.frameId;
    var fid = frame === undefined ? st.frameId : frame;

    // One-entry memo, and it earns its keep: buildField walks the grid
    // in scan order, so runs of hundreds of consecutive cells fall in
    // the same tile. Without it every one of ~34,000 cells rebuilds the
    // cache key STRING and hashes it, which was most of the cost of a
    // build. Only decoded tiles are memoized -- caching a null would
    // hide a tile that arrives mid-build.
    if (!quiet && st.memoFrame === fid && st.memoZ === z &&
        st.memoX === x && st.memoY === y && st.memoData) {
      return st.memoData;
    }

    var getUrl = quiet ? st.frames[fid] : st.getTileUrl;
    if (!getUrl) return null;
    var key = (fid || "_") + "/" + z + "/" + x + "/" + y;
    var hit = st.tiles[key];
    // A tile that failed was cached as false and never asked for again,
    // so one 404 or one decode error left a tile-shaped hole in the
    // wind for as long as the page stayed open. Retry it a bounded
    // number of times instead -- transient failures are common and
    // permanent ones stop after TILE_RETRIES.
    if (hit === false) {
      var fails = st.tileFails[key] || 0;
      if (fails >= TILE_RETRIES) return false;
      st.tileFails[key] = fails + 1;
      hit = undefined;                         // fall through and refetch
    }
    if (hit !== undefined) {
      if (!quiet && hit) {
        st.memoFrame = fid; st.memoZ = z; st.memoX = x; st.memoY = y;
        st.memoData = hit;
      }
      return hit;
    }
    st.tiles[key] = null;                      // in flight

    var url;
    try {
      url = getUrl({ x: x, y: y }, z);
    } catch (e) { st.tiles[key] = false; return null; }
    if (!url) { st.tiles[key] = false; return null; }
    if (!quiet) tileStarted(st);

    var img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = function () {
      if (!quiet) tileFinished(st);
      try {
        var c = document.createElement("canvas");
        c.width = TILE_PX; c.height = TILE_PX;
        var cx = c.getContext("2d");
        cx.drawImage(img, 0, 0, TILE_PX, TILE_PX);
        st.tiles[key] = cx.getImageData(0, 0, TILE_PX, TILE_PX).data;
      } catch (e) {
        st.tiles[key] = false;                 // tainted / undecodable
        if (!st.warned) {
          st.warned = true;
          console.warn("wind particles: tile pixels unreadable", e);
        }
      }
    };
    img.onerror = function () {
      st.tiles[key] = false;
      if (!quiet) tileFinished(st);
    };
    img.src = url;
    return null;
  }

  /**
   * Fetch the tiles the NEXT frames will need, before they are asked for.
   *
   * Without this, a lapse arrives at each hour with an empty cache: the
   * frame changes, every tile for it is requested from scratch, and the
   * field cannot be built until they land. At the viewer's 666 ms per
   * frame that is most of the time, which is what "the particles don't
   * update quickly enough" actually is -- not a slow renderer, a cold
   * cache. Tiles are ~10 KB and already cached by the browser after the
   * first pass, so the cost is one pass over the loop.
   *
   * Bounded to WARM_FRAMES ahead: warming all nine at once on a wide
   * view is a few hundred requests in one burst, which competes with the
   * tiles the frame ON SCREEN still needs.
   */
  function warmNextFrames(st) {
    if (!st.isLapse || !st.proj || !st.w || !st.h) return;
    var ids = Object.keys(st.frames);
    var at = ids.indexOf(st.frameId);
    if (at < 0) return;

    var z = st.tileZoom, n = Math.pow(2, z);
    // Same grid the raster paints -- and the same dateline trap, which
    // used to warm a single column on a Pacific view.
    var tile = tileRect(st, z);
    if (!tile) return;

    for (var k = 1; k <= WARM_FRAMES; k++) {
      var fid = ids[(at + k) % ids.length];
      if (fid === st.frameId) break;         // lapse shorter than the window
      for (var i = 0; i < tile.cols; i++) {
        for (var j = 0; j < tile.rows; j++) {
          var y = tile.y0 + j;
          if (y < 0 || y >= n) continue;
          getTile(st, z, (((tile.x0 + i) % n) + n) % n, y, fid);
        }
      }
    }
  }

  /**
   * One decoded (u, v) pixel, addressed in GLOBAL pixel coordinates.
   *
   * Global rather than per-tile so that one function owns the whole
   * decode: which tile a coordinate falls in, the dateline wrap, the
   * transparent-means-no-data check, and the byte-to-m/s stretch. The
   * caller works in pixels and never has to know about tile edges.
   */
  function pixelUV(st, z, gx, gy) {
    // 1 << z, not Math.pow: this runs once per grid cell -- ~34,000
    // times per build -- and z is a small integer zoom.
    var W = (1 << z) * TILE_PX;
    gx = Math.floor(gx); gy = Math.floor(gy);
    if (gy < 0 || gy >= W) return null;
    gx = ((gx % W) + W) % W;                   // wrap the dateline
    var data = getTile(st, z, (gx / TILE_PX) | 0, (gy / TILE_PX) | 0);
    if (!data) return null;
    var i = ((gy % TILE_PX) * TILE_PX + (gx % TILE_PX)) * 4;
    if (data[i + 3] === 0) return null;        // transparent = no data
    // Red carries u, green carries v -- the order the encoder used.
    var lo = st.cfg.tileMin, span = st.cfg.tileMax - lo;
    return [lo + (data[i] / 255) * span, lo + (data[i + 1] / 255) * span];
  }

  /**
   * (u, v, magnitude) at a lat/lon, or null. Nearest pixel.
   *
   * No interpolation here, deliberately. ``windTiles`` applies
   * ``resample('bicubic')`` before ``visualize()``, so Earth Engine has
   * already smoothed the field into the tile -- measured on a GFS tile
   * at zoom 10, the unresampled version runs to 176 identical pixels in
   * a row where the bicubic one runs to 45, with a maximum step of 6
   * against 2.
   *
   * A client-side blend on top of that is work already paid for, done
   * worse (bilinear against bicubic) and repeated for every particle of
   * every frame rather than once per tile. Worse still, what remains
   * after the bicubic is 8-BIT QUANTIZATION -- 0.31 m/s per level --
   * and interpolating between two equal bytes returns the same byte, so
   * there is nothing left for it to recover.
   *
   * The one thing that does matter is that the tiles are fetched near
   * display resolution, which is what ``particleMaxTileZoom`` governs.
   * Capping it low forces the client to sample a coarse grid and then
   * interpolate its way back to smooth -- the long way round.
   */
  function sampleUV(st, lat, lon) {
    if (lat > 85 || lat < -85) return null;
    var z = st.tileZoom;
    var uv = pixelUV(st, z, lonToTileX(lon, z) * TILE_PX,
                     latToTileY(lat, z) * TILE_PX);
    if (!uv) return null;
    // Magnitude here rather than in the caller: every caller wants it,
    // it is one sqrt either way, and returning it keeps frame() from
    // recomputing a number already in hand.
    return [uv[0], uv[1], Math.sqrt(uv[0] * uv[0] + uv[1] * uv[1])];
  }

  function hexToRgb(h) {
    h = String(h || "#fff").replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    return isNaN(n) ? [255, 255, 255] : [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  /**
   * Element-id stems the legend entry might be filed under.
   *
   * An ordinary layer's is its own id. A TIME LAPSE's is the FIRST
   * FRAME's, because the viewer builds the legend per frame and nulls
   * classLegendDict on every frame but the first — so the container
   * that exists belongs to that frame, not to the lapse. Checking only
   * the lapse id found nothing and returned quietly, which left the
   * lapse on the old chip-and-caption legend while the single-frame
   * layer got the colour bar.
   */
  function legendContainerIds(st) {
    var bare = st.id.indexOf("tl:") === 0 ? st.id.slice(3) : st.id;
    return [bare].concat(Object.keys(st.frames || {}));
  }

  /**
   * Rebuild the legend entry as a COLOUR BAR.
   *
   * The viewer has native markup for a continuous ramp -- title, a
   * full-width bar, and the two end values underneath -- but it is only
   * reachable by handing it ``min``/``max``/``palette``, and those go
   * to ``getMapId``. This layer's image is already ``visualize``d, so a
   * palette there is an Earth Engine error, not a legend.
   *
   * So the entry arrives through the class-legend path instead, which
   * renders a small chip with the label beside it. For a class that is
   * right; for a continuous stretch it is not -- a 132 px chip captioned
   * "Wind speed 0-34 mi/hr" does not tell you which end is 34. This
   * reshapes that one entry into the bar-plus-endpoints layout, keeping
   * the swatch the server built (the comet over the ramp, which is what
   * the map actually shows) as the bar's background.
   */
  function restyleLegend(st) {
    var $ = global.$;
    if (!$ || st.legendStyled || !st.cfg.speedRaster) return;
    var id = st.id.indexOf("tl:") === 0 ? st.id.slice(3) : st.id;
    injectSliderStyle();

    // Where the legend entry actually lives.
    //
    // For an ordinary layer the container is "<layerId>-class-container".
    // For a TIME LAPSE it is keyed on the FIRST FRAME's id, not the
    // lapse's -- the viewer builds the legend per frame and nulls
    // classLegendDict on every frame but the first, so the container
    // that exists belongs to that frame. Looking only under the lapse
    // id found nothing and returned quietly, which is why the lapse
    // kept the old chip-and-caption legend while the single-frame
    // layer got the colour bar.
    var li = $();
    var candidates = legendContainerIds(st);
    for (var i = 0; i < candidates.length && !li.length; i++) {
      li = $("#" + candidates[i] + "-class-container").find("li").first();
    }
    if (!li.length) return;                    // panel not built yet

    var lo = st.cfg.rampMin, hi = st.cfg.rampMax, unit = st.cfg.units || "";
    if (lo === undefined || hi === undefined) return;
    var pal = st.cfg.rampPalette || [];
    if (pal.length < 2) return;

    // The ramp is built HERE from the palette rather than lifted out of
    // the server's swatch, because the comet has to be a separate
    // element to move. A background layer cannot be animated across the
    // bar without dragging the ramp with it.
    var stops = [];
    for (var i = 0; i < pal.length; i++) {
      var c = String(pal[i]).replace(/^#?/, "#");
      stops.push(c + " " + Math.round(i * 100 / (pal.length - 1)) + "%");
    }

    st.legendStyled = true;
    li.empty();
    var ramp = $("<div>").addClass("wind-legend-ramp")
        .attr("style", "background:linear-gradient(90deg," +
                       stops.join(",") + ")");
    // A trail crossing the bar, at the layer's own particle colour. The
    // key should show the flow as motion, since motion is the half of
    // this layer a static chip cannot describe.
    var rgb = st.cfg.rgb || [255, 255, 255];
    ramp.append($("<i>").addClass("wind-legend-comet").attr("style",
        "background:linear-gradient(90deg,rgba(" + rgb.join(",") + ",0)," +
        "rgba(" + rgb.join(",") + ",.95))"));
    li.append(ramp);
    // <i>, not <span>. The class-legend CSS styles `li span` as the
    // swatch chip -- bordered, fixed width -- so numbers put in spans
    // came out as two little boxes instead of as labels.
    li.append($("<div>").addClass("wind-legend-ends")
        .append($("<i>").text(String(lo)))
        .append($("<i>").text(String(hi) + (unit ? " " + unit : ""))));
  }

  /**
   * Point the inspector at real weather, not at the encoding.
   *
   * The merged layer draws u/v bytes. Clicking it would report those
   * bytes -- 0..255 per channel -- as if they were a wind reading. The
   * viewer keeps the queried object separate from the drawn one, so the
   * fix is to hand queryObj the speed/direction collection instead.
   *
   * It arrives serialized because viz travels as JSON, and is decoded
   * here with the viewer's own deserializer. Failure is not fatal: the
   * layer keeps working and the query simply stays as it was, which is
   * better than a layer that will not load.
   */
  function retargetQuery(st) {
    if (st.queryRetargeted || !st.cfg.queryItemJson) return;
    var ee = global.ee, qo = queries();
    if (!ee || !ee.Deserializer || !qo) return;
    var id = st.id.indexOf("tl:") === 0 ? st.id.slice(3) : st.id;
    if (!qo[id]) return;                       // panel not built yet
    try {
      var raw = st.cfg.queryItemJson;
      var decoded = ee.Deserializer.fromJSON
          ? ee.Deserializer.fromJSON(raw)
          : ee.Deserializer.decode(JSON.parse(raw));
      qo[id].queryItem = decoded;
      st.queryRetargeted = true;
    } catch (e) {
      st.queryRetargeted = true;               // do not retry every tick
      if (global.console) {
        console.warn("wind particles: could not retarget the query", e);
      }
    }
  }

  /**
   * The ``r, g, b`` of a computed background-color, alpha discarded.
   *
   * Browsers report this as ``rgb(a, b, c)`` or ``rgba(a, b, c, d)``;
   * anything else (a named color, or an empty string on a control the
   * theme has not painted) falls back to the viewer's own track color
   * rather than to nothing, since nothing renders as jQuery UI's
   * default grey and looks broken next to the control above it.
   */
  function rgbOfTrack(css) {
    var m = /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/.exec(String(css || ""));
    return m ? m[1] + "," + m[2] + "," + m[3] : "55,46,44";
  }

  /** Paint a slider track at one alpha, the way the viewer paints its
   *  own. ``!important`` because the class carries a flat background. */
  function setTrackAlpha(id, rgb, alpha) {
    var el = global.document && global.document.getElementById(id);
    if (!el) return;
    el.style.setProperty("background-color",
                         "rgba(" + rgb + "," + alpha + ")", "important");
  }

  /**
   * Where the particle dimmer starts, from the viz.
   *
   * ``windParticleDim`` is geeViz.weather's master ``opacity``, sent
   * under its own name because the viewer has already claimed
   * ``opacity`` for the raster's slider on a grouped layer. Falling
   * back to ``opacity`` keeps a hand-built viz -- one that sets
   * ``windParticles`` directly rather than going through
   * ``addWindLayer`` -- behaving the obvious way.
   */
  function initialDim(v) {
    var d = v && typeof v.windParticleDim === "number"
        ? v.windParticleDim
        : (v && typeof v.opacity === "number" ? v.opacity : 1);
    return Math.min(1, Math.max(0, d));
  }

  /**
   * A second opacity slider, for the particles alone.
   *
   * The viewer gives a time lapse ONE opacity slider, and on a merged
   * wind layer that one drives the speed raster -- it is the
   * layer-shaped thing on screen. The trails need their own, or the two
   * halves of the layer can only be faded together, which defeats
   * drawing them separately.
   *
   * Injected here rather than added to the viewer: this is the only
   * layer type that has two things to fade, and the markup it needs is
   * the markup the existing slider already uses, so it costs one
   * sibling div and no change to a bundle shared with every other
   * viewer. It is skipped silently wherever jQuery UI is absent -- the
   * layer then behaves as it did, with one control.
   */
  /**
   * The little that the two sliders need beyond the panel's own CSS.
   *
   * Injected once, scoped to classes this file owns, rather than edited
   * into a stylesheet shared with every other viewer. Two sliders
   * stacked with no separation read as one broken control, and two
   * identical tracks give no clue which fades what -- so the tracks are
   * tinted to match what they govern: the speed ramp's own colors for
   * the raster, white for the trails.
   */
  function injectSliderStyle() {
    if (!global.document) return;
    // Keyed on the ELEMENT, not on a module-level flag. The flag is
    // reset by a fresh copy of this module while the old <style> is
    // still in the document, and the reverse -- a stale stylesheet
    // with none of the new rules -- is worse than a duplicate.
    if (document.getElementById(STYLE_ID)) return;
    styleInjected = true;
    var css =
      // ---- the second opacity slider -------------------------------
      //
      // NOTHING about how a slider looks is set here. It is a copy of
      // the layer's own opacity control and inherits
      // .simple-layer-opacity-range wholesale, so it matches every
      // other opacity slider in the panel -- same track, same handle,
      // same vertical centring.
      //
      // An earlier version restyled both: a taller track, a lighter
      // handle, a palette-tinted background and an identifying chip.
      // All of it was wrong. Restyling one pair of sliders makes them
      // the odd ones out in a panel full of the stock control, and the
      // handle's centring is tuned to the stock track height -- change
      // the track and the handle sits off-centre. The tooltips say
      // which is which.
      //
      // What IS needed is stacking. The control is float:right and
      // 64px wide; two of them share one line and scrunch together.
      // `clear:right` puts each on its own line.
      ".wind-two-sliders .wind-speed-opacity-slider," +
      ".wind-two-sliders .wind-particle-opacity-slider" +
      "{clear:right !important;margin-left:0 !important;}" +
      // rem, NOT px -- this panel is sized in rem and the viewer's root
      // font-size moves with the viewport (12px narrow, 16px wide). The
      // first cut of these three numbers was measured at a 12px root and
      // written down in px, so on a wide window everything around them
      // grew a third and they did not: the gap stayed 9px between two
      // sliders that were now 3.19px tall instead of 2.39, and the row
      // stayed 38px holding content that wanted 51. That reads as a
      // pinched, crowded pair, and it only shows up at one end of the
      // range -- which is why it survived being looked at.
      //
      // The gap goes on the UPPER one, the particle control, as a bottom
      // margin: `clear:right` makes the lower float clear the upper
      // float's MARGIN edge, so one declaration owns the spacing instead
      // of two fighting over it.
      ".wind-two-sliders .wind-speed-opacity-slider" +
      "{margin-top:0 !important;}" +
      ".wind-two-sliders .wind-particle-opacity-slider" +
      "{margin-bottom:1rem !important;}" +
      // Floats do not grow their parent, so the row is given the height
      // the second slider needs -- without it that slider overflows the
      // entry and lands on the layer below. 3.2rem is 38.4px at a 12px
      // root (what shipped) and 51.2px at 16px (what the row actually
      // needs there).
      "li.wind-two-sliders{min-height:3.2rem;}" +
      // A time lapse's controls already stack; it only needs the gap.
      ".simple-time-lapse-layer-range-first.wind-particle-opacity-slider" +
      "{margin-top:0.5rem !important;}" +
      // ---- the legend entry, rebuilt as a colour bar ----------------
      // A CONCRETE width, not 100%. ul.legend-labels is float:left and
      // therefore shrink-to-fit, so a percentage resolves against
      // whatever the content already happens to be -- which collapsed
      // the bar to 42px and ran the two end labels together.
      ".wind-legend-ramp{display:block !important;width:150px !important;" +
      "height:13px !important;border:1px solid #968b83;" +
      "border-radius:2px;position:relative;overflow:hidden;}" +
      // The trail, crossing the bar on a loop. 3px so it reads as a
      // streak rather than a wipe, and it starts fully off the left
      // edge so the bar is briefly clean -- a comet that never leaves
      // reads as a gradient, not as motion.
      ".wind-legend-comet{position:absolute;top:50%;left:0;" +
      "margin-top:-1.5px;width:34px;height:3px;border-radius:2px;" +
      "animation:wind-legend-flow 2.6s linear infinite;}" +
      "@keyframes wind-legend-flow{" +
      "from{transform:translateX(-34px);}" +
      "to{transform:translateX(150px);}}" +
      // Anything that loops forever has to answer this, or it is an
      // accessibility problem rather than a nicety.
      "@media (prefers-reduced-motion:reduce){" +
      ".wind-legend-comet{animation:none;left:auto;right:6px;}}" +
      ".wind-legend-ends{display:flex;justify-content:space-between;" +
      "width:150px;font-size:11px;opacity:.85;margin-top:1px;}" +
      ".wind-legend-ends i{font-style:normal;}";
    try {
      var el = document.createElement("style");
      el.id = STYLE_ID;
      el.type = "text/css";
      el.appendChild(document.createTextNode(css));
      (document.head || document.documentElement).appendChild(el);
    } catch (e) { /* styling is a nicety; the sliders still work */ }
  }

  function addParticleSlider(st) {
    var $ = global.$;
    if (!$ || st.sliderAdded) return;
    var id = st.id.indexOf("tl:") === 0 ? st.id.slice(3) : st.id;

    // Two shapes to find. A time lapse's opacity control is
    // "<id>-opacity-slider" with the lapse's range class; an ordinary
    // layer's is "<id>-opacity" with .simple-layer-opacity-range. The
    // grouped layer is now BOTH kinds, so look for either and build the
    // sibling out of whatever the host already wears -- that is what
    // keeps it sized and themed like the panel rather than like a patch.
    var host = $("#" + id + "-opacity-slider");
    var handleClass = "time-lapse-slider-handle";
    if (!host.length) {
      host = $("#" + id + "-opacity");
      handleClass = "";
    }
    if (!host.length || typeof host.slider !== "function") return;

    injectSliderStyle();

    var sid = id + "-particle-opacity-slider";
    if ($("#" + sid).length) { st.sliderAdded = true; return; }

    // Strip jQuery UI's own classes off the copy: they are applied by
    // .slider() below, and carrying them into fresh markup leaves an
    // element styled as a slider that is not yet wired to one.
    var base = (host.attr("class") || "").split(/\s+/).filter(function (c) {
      return c && c.indexOf("ui-") !== 0;
    }).join(" ");

    host.addClass("wind-speed-opacity-slider");
    host.attr("title", "Wind speed opacity");
    // The ROW has to know it carries two, because floats do not grow
    // their parent -- without the extra height the second slider
    // overflows the layer entry and lands on the one below it.
    host.closest("li").addClass("wind-two-sliders");
    // BEFORE the host, not after. The pair should read in the order
    // the map draws them: particles are painted over the raster, so the
    // particle control belongs above the raster's. Both are float:right
    // with clear:right, so DOM order is top-to-bottom order.
    host.before(
      "<div title='Particle opacity' id='" + sid + "'" +
      " class='" + base + " wind-particle-opacity-slider'>" +
      "<div id='" + sid + "-handle'" +
      " class='" + handleClass + " ui-slider-handle'></div></div>");

    // The viewer paints its own slider's track with an INLINE
    // background-color, so a copy that inherits only the class comes
    // out in jQuery UI's default grey and does not match the control
    // directly above it. Take the color from the host rather than
    // hard-coding one, so it follows the tenant's theme.
    //
    // And take only the RGB: the host's ALPHA is the speed raster's
    // opacity, which is a different number from the particles' whenever
    // windSpeedOpacity is set. setTrackAlpha supplies ours.
    var trackRgb = rgbOfTrack(host.css("background-color"));
    setTrackAlpha(sid, trackRgb, st.particleDim);

    try {
      $("#" + sid).slider({
        // Starts where the particles actually are, not at 1. A handle
        // parked at full while the flow renders at 0.8 is a control
        // lying about the thing it controls.
        min: 0, max: 1, step: 0.05, value: st.particleDim,
        create: function () {
          $("#" + sid + "-handle").text("");
        },
        slide: function (e, ui) {
          st.particleDim = ui.value;
          // The viewer fades its own track as you drag it
          // (setRangeSliderThumbOpacity), so a copy that does not
          // is visibly the odd one out in a panel of controls that
          // all do -- and on a wind layer the two sit one above the
          // other, which is the worst place to differ.
          setTrackAlpha(sid, trackRgb, ui.value);
          refreshRunState();
        },
      });
      st.sliderAdded = true;
    } catch (e) { /* no jQuery UI: one control, as before */ }
  }

  /**
   * The tile grid covering the canvas, anchored on its NW corner.
   *
   * Counted in TILES from that corner rather than measured between two
   * corners' longitudes, because google.maps normalises longitude into
   * [-180, 180): a view spanning the dateline reports a west edge east
   * of its east edge, and any range built from the pair is either
   * inverted or -- once guarded -- collapsed to nothing. Counting has
   * no such case, and tx running past n is exactly right: that is the
   * next copy of the world, where the wrapped tiles belong.
   *
   * Returns null before the overlay has a projection or a size.
   */
  function tileRect(st, z) {
    if (!st.proj || !st.w || !st.h) return null;
    var pt = new google.maps.Point(st.origin.x, st.origin.y);
    var nw = st.proj.fromDivPixelToLatLng(pt);
    if (!nw) return null;
    var mapZoom = global.map && global.map.getZoom();
    if (typeof mapZoom !== "number") mapZoom = z;
    var side = TILE_PX * Math.pow(2, mapZoom - z);
    if (!(side > 0)) return null;
    var nwTx = lonToTileX(nw.lng(), z);
    var nwTy = latToTileY(Math.min(85, Math.max(-85, nw.lat())), z);
    return {
      nw: nw, side: side, nwTx: nwTx, nwTy: nwTy,
      x0: Math.floor(nwTx), y0: Math.floor(nwTy),
      // +1 for the partial tile the corner starts inside of, +1 for the
      // partial tile at the far edge.
      cols: Math.ceil(st.w / side) + 1,
      rows: Math.ceil(st.h / side) + 1,
    };
  }

  // ---- the speed raster ---------------------------------------------

  /**
   * A 256-entry lookup from the palette, as flat RGB bytes.
   *
   * Built once per layer. The alternative -- interpolating the palette
   * per pixel -- is ~800,000 interpolations per repaint for a picture
   * with 256 distinct colors in it.
   */
  function buildRampLut(palette) {
    var lut = new Uint8Array(256 * 3);
    var cols = [];
    for (var i = 0; i < palette.length; i++) {
      cols.push(hexToRgb(String(palette[i])));
    }
    if (!cols.length) cols = [[255, 255, 255]];
    if (cols.length === 1) cols.push(cols[0]);
    var segs = cols.length - 1;
    for (var k = 0; k < 256; k++) {
      var t = (k / 255) * segs;
      var a = Math.min(segs - 1, Math.floor(t));
      var f = t - a;
      var c0 = cols[a], c1 = cols[a + 1];
      lut[k * 3] = c0[0] + (c1[0] - c0[0]) * f;
      lut[k * 3 + 1] = c0[1] + (c1[1] - c0[1]) * f;
      lut[k * 3 + 2] = c0[2] + (c1[2] - c0[2]) * f;
    }
    return lut;
  }

  /** What the raster was painted for. Same idea as viewKey. */
  function speedKey(st) {
    return viewKey(st) + "|" + (st.tileZoom | 0);
  }

  /**
   * Paint the speed field from the tiles the particles already decoded.
   *
   * There is no second Earth Engine layer under this one: u and v are
   * in the red and green of the tiles this module fetches anyway, and
   * speed is sqrt(u^2 + v^2). So the raster costs no extra requests --
   * it is the same bytes, read a second way.
   *
   * Drawn tile by tile at the tile's own resolution and then scaled by
   * the browser, which is exactly what a raster layer does. Painting
   * per SCREEN pixel instead would mean an inverse projection per pixel
   * and no reuse between frames.
   */
  function renderSpeedRaster(st) {
    if (!st.speedCtx || !st.proj || !st.w || !st.h) return false;
    var paintStart = nowMs();
    var ctx = st.speedCtx;
    var z = st.tileZoom, n = 1 << z;
    var proj = st.proj;

    var lo = st.cfg.rampMinMs, span = st.cfg.rampMaxMs - lo;
    if (!(span > 0)) return false;
    if (!st.rampLut) st.rampLut = buildRampLut(st.cfg.rampPalette);
    var lut = st.rampLut;
    var tmin = st.cfg.tileMin, tspan = st.cfg.tileMax - tmin;

    // The tile grid under the view.
    //
    // Anchored on the canvas's NW corner and counted out in TILES, not
    // derived from the two corners' longitudes. The corner-to-corner
    // version could not cross the dateline: google.maps normalises
    // longitude into [-180, 180), so a Pacific view reported its west
    // edge as +162 and its east edge as -82, which is x1 < x0 -- and
    // the guard for that collapsed the range to a single column. The
    // raster drew as a 256 px strip at the left edge while the
    // particles, which never leave canvas coordinates, covered the map.
    //
    // Counting from the corner has no such case: tx simply runs past n
    // into the next copy of the world, which is where the wrapped tiles
    // belong anyway.
    var tile = tileRect(st, z);
    if (!tile) return false;
    var side = tile.side, nwTx = tile.nwTx, nwTy = tile.nwTy;

    // This paint is laid out from st.origin, so the canvas goes there,
    // and remembers the place it was painted for (see draw()).
    st.speedNw = tile.nw;
    st.speedCanvas.style.left = st.origin.x + "px";
    st.speedCanvas.style.top = st.origin.y + "px";
    ctx.clearRect(0, 0, st.w, st.h);

    // One tile's worth of scratch, reused. A fresh ImageData per tile
    // is an allocation each.
    if (!st.tileImage || st.tileImage.width !== RASTER_PX) {
      st.tileImage = ctx.createImageData(RASTER_PX, RASTER_PX);
      st.tileCanvas = document.createElement("canvas");
      st.tileCanvas.width = RASTER_PX; st.tileCanvas.height = RASTER_PX;
      st.tileCtx = st.tileCanvas.getContext("2d");
    }
    var img = st.tileImage, outPx = img.data;
    var STEP = TILE_PX / RASTER_PX;
    var any = false, missing = false;

    for (var i = 0; i < tile.cols; i++) {
      var tx = tile.x0 + i;
      for (var j = 0; j < tile.rows; j++) {
        var ty = tile.y0 + j;
        if (ty < 0 || ty >= n) continue;
        var wrapped = ((tx % n) + n) % n;
        var data = getTile(st, z, wrapped, ty);
        if (!data) { if (data !== false) missing = true; continue; }

        // px/py/po, NOT i/j/o. `var` is function-scoped, so naming
        // this counter `i` shared it with the COLUMN loop above --
        // decoding the first tile left i at 65536 and the column loop
        // ended after one pass. The raster drew as a single strip at
        // the left edge, which looks exactly like a projection bug and
        // is not one.
        //
        // Reads every STEPth source pixel rather than averaging: the
        // tile is already a smooth upsampling of a much coarser
        // forecast grid, so neighbouring pixels are near-identical and
        // averaging them would cost four reads to reproduce one.
        for (var py = 0, po = 0; py < RASTER_PX; py++) {
          var srow = ((py * STEP) * TILE_PX) * 4;
          for (var px = 0; px < RASTER_PX; px++, po += 4) {
            var so = srow + (px * STEP) * 4;
            if (data[so + 3] === 0) { outPx[po + 3] = 0; continue; }
            var u = tmin + (data[so] / 255) * tspan;
            var v = tmin + (data[so + 1] / 255) * tspan;
            var t = (Math.sqrt(u * u + v * v) - lo) / span;
            t = t < 0 ? 0 : (t > 1 ? 1 : t);
            var c = ((t * 255) | 0) * 3;
            outPx[po] = lut[c];
            outPx[po + 1] = lut[c + 1];
            outPx[po + 2] = lut[c + 2];
            outPx[po + 3] = 255;
          }
        }
        st.tileCtx.putImageData(img, 0, 0);

        // Where this tile lands, by arithmetic from the canvas corner.
        //
        // NOT by projecting each tile's own lat/lng: google.maps.LatLng
        // NORMALISES longitude into [-180, 180), so every tile past the
        // dateline came back mapped to the other side of the world. On
        // a Pacific view that collapsed the whole raster into a thin
        // strip at the left edge, while the particles -- which never
        // leave canvas coordinates -- drew correctly across the map.
        //
        // Mercator is linear in tile space, so the offset from the
        // canvas's own NW corner is exact: (tx - nwTx) tiles across,
        // scaled by a tile's width on screen. tx may run past n here,
        // and should -- that is the wrapped copy of the world, and it
        // belongs to the right of the first.
        ctx.drawImage(st.tileCanvas,
                      (tx - nwTx) * side, (ty - nwTy) * side, side, side);
        any = true;
      }
    }

    ctx.globalAlpha = 1;
    // Cached only once every tile is in. A partial paint left cached
    // would leave the gaps on screen for as long as the view held
    // still, which is the same bug the field key had.
    var done = any && !missing;
    st.speedKey = done ? speedKey(st) : null;
    // ...and backed off when it is NOT, for the same reason buildField
    // is. A repaint is ~48 tiles x 65,536 pixels of palette lookup;
    // retrying that at the animation rate while a lapse streams its
    // next hour asks for tens of millions of operations a second and
    // locks the tab hard enough that the page stops answering at all.
    // Charged against what this paint actually cost, so it scales with
    // the window instead of assuming one.
    st.paintAgainAt = done
        ? 0
        : nowMs() + Math.max(REBUILD_MS, (nowMs() - paintStart) * REBUILD_DUTY);
    return any;
  }

  /**
   * Where, in div pixels, the speed canvas belongs for a paint made with
   * its NW corner at ``nw``, given the view's own corner ``p``.
   *
   * fromLatLngToDivPixel may answer with any copy of the world, because
   * google.maps normalizes longitude; the right one is the copy nearest
   * the view, so x is moved by whole world widths toward ``p``.
   */
  function speedCanvasAt(proj, nw, p) {
    var q = proj.fromLatLngToDivPixel(nw);
    if (!q) return p;
    var world = proj.getWorldWidth ? proj.getWorldWidth() : 0;
    var x = q.x;
    if (world > 0) {
      while (x - p.x > world / 2) x -= world;
      while (p.x - x > world / 2) x += world;
    }
    return { x: x, y: q.y };
  }

  /** Repaint only when the view, the hour or the size moved. */
  function ensureSpeedRaster(st) {
    if (!st.cfg.speedRaster || !st.speedCanvas) return;
    if (st.speedKey && st.speedKey === speedKey(st)) return;
    // Hold off if the last paint came out incomplete. Unlike the field,
    // there is no "first paint" exception: a half-drawn raster is
    // already on screen and the map underneath shows through the gaps,
    // so waiting costs nothing the user can see.
    if (st.paintAgainAt && nowMs() < st.paintAgainAt) return;
    renderSpeedRaster(st);
  }

  // ---- overlay ------------------------------------------------------

  function makeOverlay(st) {
    var ov = new google.maps.OverlayView();

    ov.onAdd = function () {
      // mapPane, NOT overlayLayer.
      //
      // `map.overlayMapTypes` -- every geeViz raster layer -- render as
      // containers inside mapPane, stacked with small z-indexes (1, 2,
      // ... matching their overlayMapTypes index). The OverlayView panes
      // sit ABOVE all of that: mapPane is 100, overlayLayer 101, and
      // everything after it higher still. Measured, in a browser, with
      // a labels layer and a wind layer on one map.
      //
      // So a canvas in overlayLayer is above EVERY tile layer no matter
      // what z-index it carries -- z-index only orders siblings inside
      // one stacking context, and these were not siblings. The symptom
      // was a labels layer, added on top and showing on top of
      // everything else, that could not be got above the wind.
      //
      // In mapPane the canvas is a sibling of the tile containers and
      // applyStacking's layerId z-index means what it says.
      //
      // mapPane "may not receive DOM events" per the Maps docs, which
      // costs nothing here: both canvases are pointer-events:none so a
      // query click reaches the map regardless.
      var pane = this.getPanes().mapPane;

      // The speed raster, when this layer draws its own. A SECOND
      // canvas rather than painting into the particle one: frame()
      // clears and repaints the particles thirty times a second, and
      // the raster only changes when the view or the hour does. Sharing
      // a canvas would mean redrawing ~800,000 palette lookups per
      // animation frame to show a picture that did not change.
      //
      // Appended first, so it sits under the trails: the two share one
      // z-index, and a tie among positioned siblings is broken by DOM
      // order. Both are in the tile layers' own pane, so that single
      // z-index is also what orders the pair against them.
      if (st.cfg.speedRaster) {
        var sc = document.createElement("canvas");
        sc.style.position = "absolute";
        sc.style.pointerEvents = "none";
        sc.style.left = "0px";
        sc.style.top = "0px";
        sc.style.transition = "opacity " + FADE_MS + "ms ease-out";
        applyStacking(st, sc);
        st.speedCanvas = sc;
        st.speedCtx = sc.getContext("2d");
        pane.appendChild(sc);
      }

      var c = document.createElement("canvas");
      c.style.position = "absolute";
      c.style.pointerEvents = "none";      // never eat a query click
      c.style.left = "0px";
      c.style.top = "0px";
      c.style.transition = "opacity " + FADE_MS + "ms ease-out";
      // First paint. Kept in sync afterwards by refreshRunState --
      // see applyStacking.
      applyStacking(st, c);
      st.canvas = c;
      st.ctx = c.getContext("2d");
      pane.appendChild(c);
    };

    ov.draw = function () {
      if (!st.canvas) return;
      var proj = this.getProjection();
      if (!proj) return;
      var div = global.map.getDiv();
      var w = div.offsetWidth, h = div.offsetHeight;

      // Anchor via CONTAINER pixels, not map bounds.
      //
      // getBounds() is undefined until the map's first idle, and the old
      // version early-returned on that -- so the whole layer rendered
      // nothing at all until an idle happened to fire. Container pixels
      // are available as soon as there is a projection.
      var originLatLng = proj.fromContainerPixelToLatLng(
        new google.maps.Point(0, 0));
      if (!originLatLng) return;
      var p = proj.fromLatLngToDivPixel(originLatLng);
      st.canvas.style.left = p.x + "px";
      st.canvas.style.top = p.y + "px";
      if (st.canvas.width !== w || st.canvas.height !== h) {
        st.canvas.width = w; st.canvas.height = h;
        st.particles = null;
      }
      if (st.speedCanvas) {
        if (st.speedCanvas.width !== w || st.speedCanvas.height !== h) {
          st.speedCanvas.width = w; st.speedCanvas.height = h;
          st.speedKey = null;            // a resize invalidates the paint
          st.speedNw = null;
        }
        // The raster stays where its PAINT belongs, not where the view
        // is now: placed at the NW corner it was painted for, so until
        // the next paint lands it moves with the map instead of
        // carrying old pixels to a new place. See speedCanvasAt.
        var q = st.speedNw ? speedCanvasAt(proj, st.speedNw, p) : p;
        st.speedCanvas.style.left = q.x + "px";
        st.speedCanvas.style.top = q.y + "px";
      }
      st.origin = p; st.proj = proj; st.w = w; st.h = h;
      st.viewGeom = [global.map.getZoom(),
                     originLatLng.lat().toFixed(6),
                     originLatLng.lng().toFixed(6), w, h].join("|");
      // Tiles track the map, so Earth Engine's bicubic is evaluated at
      // roughly the resolution it will be shown at and the client can
      // sample the nearest pixel and be done.
      //
      // The cap only stops the pointless extreme: past zoom 10 a tile
      // pixel is under 150 m against a 28 km forecast grid, so finer
      // tiles carry no more information. It is NOT what bounds the
      // request count -- the off-screen cull in frame() does that, and
      // it is what took a zoom-10 view from 1559 tiles to the ~35 the
      // viewport actually needs.
      st.tileZoom = Math.max(0, Math.min(MAX_TILE_ZOOM,
                                         global.map.getZoom() || 4));
    };

    ov.onRemove = function () {
      if (st.canvas && st.canvas.parentNode) {
        st.canvas.parentNode.removeChild(st.canvas);
      }
      st.canvas = null; st.ctx = null;
    };

    return ov;
  }

  /** Random point in the visible container, in lat/lng. No bounds needed. */
  /**
   * Precompute the wind for the whole viewport, once per view.
   *
   * This is the shape cambecc's windy.js uses, and the reason it can
   * animate thousands of particles cheaply: for each cell of a coarse
   * canvas grid, resolve the wind ONCE and store it already converted
   * to PIXELS PER FRAME. Particles then live in canvas coordinates and
   * advancing one is two array reads and two adds -- no projection, no
   * cos(lat), no zoom scaling, no tile lookup, none of it per particle
   * per frame.
   *
   * The arithmetic that used to run 240,000 times a second (4000
   * particles at 60fps) now runs about 130,000 times per VIEW CHANGE,
   * and not at all while the map sits still.
   *
   * It has to be rebuilt on pan and zoom, not merely on resize: canvas
   * pixel (0, 0) means a different place on the globe after a pan, so
   * every cached vector is wrong. Rebuilding is tied to the map's idle
   * event, so it happens once when movement stops rather than during
   * the drag.
   */
  function buildField(st) {
    if (!st.proj || !st.w || !st.h) return false;
    var startedAt = nowMs();
    var cfg = st.cfg;
    var sp = FIELD_SPACING;
    var gw = Math.ceil(st.w / sp) + 1, gh = Math.ceil(st.h / sp) + 1;

    // Built into SCRATCH buffers, never over the field being drawn.
    //
    // This used to fill straight into st.field, blanking it first. On a
    // time lapse that is a freeze on every frame: the instant the hour
    // advances none of the new frame's tiles are decoded yet, so the
    // build resolves nothing, fieldAny goes false, tick() skips the draw
    // entirely and the particles stop dead until the tiles land. Two
    // buffers mean the previous hour's field keeps the flow moving for
    // the few hundred milliseconds the new one needs, and the swap is a
    // pointer swap the eye never catches.
    if (!st.fieldB || st.fieldBW !== gw || st.fieldBH !== gh) {
      st.fieldB = new Float32Array(gw * gh * 2);
      st.fieldOkB = new Uint8Array(gw * gh);
      st.fieldBW = gw; st.fieldBH = gh;
    } else {
      st.fieldOkB.fill(0);
    }
    var f = st.fieldB, ok = st.fieldOkB;
    var ox = st.origin.x, oy = st.origin.y, proj = st.proj;
    var pt = new google.maps.Point(0, 0);
    var any = false;

    // One inverse projection PER ROW and PER COLUMN, not per cell.
    //
    // The map is Web Mercator, which is cylindrical: latitude is a
    // function of the pixel y alone and longitude of the pixel x alone.
    // So the grid needs gh + gw projections, not gh * gw of them. On a
    // full-screen map that is 376 instead of 34,560 -- and it is exact,
    // not an approximation, because that separability IS the projection.
    //
    // fromDivPixelToLatLng was ~90% of a build that measured 290 ms with
    // every tile already decoded. At the animation rate the rebuilds
    // alone asked for roughly nine seconds of main thread per second of
    // wall clock, which is why a time lapse felt like a GPU problem.
    var lats = new Float64Array(gh), lngs = new Float64Array(gw);
    var latOk = new Uint8Array(gh), lngOk = new Uint8Array(gw);
    for (var ry = 0; ry < gh; ry++) {
      pt.x = ox; pt.y = ry * sp + oy;
      var rl = proj.fromDivPixelToLatLng(pt);
      if (rl) { lats[ry] = rl.lat(); latOk[ry] = 1; }
    }
    for (var cx = 0; cx < gw; cx++) {
      pt.x = cx * sp + ox; pt.y = oy;
      var cl = proj.fromDivPixelToLatLng(pt);
      if (cl) { lngs[cx] = cl.lng(); lngOk[cx] = 1; }
    }

    for (var gy = 0; gy < gh; gy++) {
      if (!latOk[gy]) continue;
      for (var gx = 0; gx < gw; gx++) {
        if (!lngOk[gx]) continue;
        var lat = lats[gy];
        var uv = sampleUV(st, lat, lngs[gx]);
        if (!uv) continue;

        var u = uv[0], v = uv[1], mag = uv[2];
        // Apparent-speed floor and ceiling. Applied here, once, rather
        // than per particle per frame -- and only to how far a dot
        // moves. The speed raster and the click query are untouched.
        if (mag > 1e-6) {
          var target = Math.min(Math.max(mag, cfg.minSpeed), cfg.maxSpeed);
          if (target !== mag) {
            var k = target / mag;
            u *= k; v *= k;
          }
        }

        // metres/second -> pixels/frame. Mercator shrinks ground
        // distance toward the poles, so a fixed wind covers more pixels
        // there; cos(lat) is that, and it is why this cannot be one
        // constant for the whole canvas.
        // metres/second -> pixels/frame. One constant: no zoom term
        // (it cancelled -- see cfg.speed) and no latitude term either.
        //
        // This used to divide by cos(lat), on the grounds that Mercator
        // genuinely stretches a fixed ground speed into more pixels
        // toward the poles. True, but it made the Arctic unreadable: in
        // a world view spanning -60..+80 the streaks at the top ran SIX
        // TIMES those at the equator in the same frame, and past 85
        // degrees it diverges.
        //
        // Dropping it costs nothing that matters. Mercator is conformal,
        // so the projection scales u and v by the SAME factor at a given
        // point -- dividing the whole field by a scalar field leaves the
        // direction at every point untouched, and therefore leaves the
        // shape of every streamline untouched. Only the speed along a
        // streamline changes. The streaks trace exactly the same curves;
        // they just do it at a rate that is even across the frame.
        //
        // And the honest reading: length already stopped representing
        // ground speed when it was made zoom-invariant. Keeping one
        // projection term after dropping the other was the inconsistent
        // state, not this.
        var scale = cfg.speed;
        var i = (gy * gw + gx) * 2;
        f[i] = u * scale;
        // Screen y grows downward while v is northward, hence the sign.
        f[i + 1] = -v * scale;
        ok[gy * gw + gx] = 1;
        any = true;
      }
    }

    // A build counts as COMPLETE only with nothing still in flight.
    //
    // The key used to be stamped whenever a single cell had data, which
    // meant a field built while most tiles were in flight was cached as
    // final -- ensureField then returned true forever and those regions
    // stayed permanently empty. The tiles did arrive; the field was
    // frozen before they did, which is why the loading counter honestly
    // read zero over a half-drawn map.
    var complete = any && !st.inflight;

    // Take the new field if it is finished, or if there is nothing on
    // screen yet to keep. A partial field on first load is right --
    // holes that fill in beat an empty map. A partial field DURING a
    // lapse is not: the hour on screen is already drawing correctly.
    if (complete || !st.fieldAny) {
      var pf = st.field, pok = st.fieldOk;
      st.field = f; st.fieldOk = ok;
      st.fieldB = pf; st.fieldOkB = pok;
      st.fieldW = gw; st.fieldH = gh; st.fieldSpacing = sp;
      st.fieldAny = any;
    }

    st.fieldKey = complete ? viewKey(st) : null;
    // Back off before trying again. Nothing about an incomplete build
    // changes until a tile arrives, and retrying at the animation rate
    // costs more than the animation itself.
    // Charge the wait against what this build cost, so a big window
    // backs off proportionally instead of thrashing.
    var took = nowMs() - startedAt;
    st.buildAgainAt = complete
        ? 0
        : nowMs() + Math.max(REBUILD_MS, took * REBUILD_DUTY);
    return st.fieldAny;
  }

  function nowMs() {
    return (global.performance && global.performance.now)
        ? global.performance.now() : Date.now();
  }

  /** What the field was built for. Changes on pan, zoom or resize. */
  function viewKey(st) {
    // The view the canvases are POSITIONED for (st.viewGeom, written by
    // draw() together with st.origin and st.proj), not map.getCenter().
    //
    // The center moves ahead of draw() during a fast pan with momentum:
    // a repaint between the two used the old origin but was keyed with
    // the new center, so when draw() then moved the canvas to the new
    // origin the key still matched and nothing repainted. The speed
    // raster sat offset from the map, showing the wind of the wrong
    // place, until the next zoom or hour. Keying on draw()'s own
    // geometry means a paint can only be reused at the exact position
    // it was made for.
    //
    // st.frameId is part of the key: the field is a resample of the
    // decoded tiles, and advancing a frame changes the data under an
    // unchanged view. Without it the lapse would play with frame 1's
    // vectors forever.
    return [st.viewGeom || "?", st.frameId || "_"].join("|");
  }

  /**
   * The wind at a canvas pixel, in pixels/frame, or null.
   *
   * Bilinear across the GRID -- not across the data. The grid is a
   * subsampling this module chose, so interpolating it back is
   * recovering our own coarseness, which is a different thing from
   * interpolating the forecast (Earth Engine already did that, in the
   * tile). Without it the flow visibly facets at the grid spacing.
   */
  function fieldAt(st, x, y) {
    var f = st.field;
    if (!f || !st.fieldAny) return null;
    var sp = st.fieldSpacing, gw = st.fieldW, gh = st.fieldH;
    var fx = x / sp, fy = y / sp;
    var x0 = Math.floor(fx), y0 = Math.floor(fy);
    if (x0 < 0 || y0 < 0 || x0 + 1 >= gw || y0 + 1 >= gh) return null;
    var ok = st.fieldOk;
    var i00 = y0 * gw + x0, i10 = i00 + 1;
    var i01 = i00 + gw, i11 = i01 + 1;
    if (!ok[i00] || !ok[i10] || !ok[i01] || !ok[i11]) return null;
    var rx = 1 - (fx - x0), ry = 1 - (fy - y0);
    var wa = rx * ry, wb = (1 - rx) * ry, wc = rx * (1 - ry),
        wd = (1 - rx) * (1 - ry);
    return [
      f[i00 * 2] * wa + f[i10 * 2] * wb + f[i01 * 2] * wc + f[i11 * 2] * wd,
      f[i00 * 2 + 1] * wa + f[i10 * 2 + 1] * wb +
        f[i01 * 2 + 1] * wc + f[i11 * 2 + 1] * wd,
    ];
  }

  /**
   * Put a particle somewhere in the view, with its own lifetime.
   *
   * Canvas coordinates now, so this is two random numbers rather than
   * an inverse projection.
   *
   * Trail length is how much history is still drawn, so a particle that
   * respawned two frames ago draws a stub and a mature one draws a full
   * streak. With a single shared lifetime almost every particle sits in
   * the mature part of its life at any instant and the field reads as
   * one uniform comb. Drawing each lifetime from a range keeps short,
   * medium and long streaks on screen at once.
   */
  function respawn(st, p, randomAge) {
    var cfg = st.cfg;
    if (p.hx === undefined || cfg.layout === "random") {
      // Free particles land anywhere; a lattice particle returns to the
      // cell it was seeded in, or the pattern erodes into noise within
      // a lifetime or two.
      p.x = Math.random() * st.w;
      p.y = Math.random() * st.h;
    } else {
      p.x = p.hx;
      p.y = p.hy;
    }
    p.xs = []; p.ys = [];
    p.maxAge = cfg.minAge + Math.random() * (cfg.maxAge - cfg.minAge);
    // Stagger the initial ages too, or the whole field respawns in
    // lockstep and the map pulses once per lifetime.
    p.age = randomAge ? Math.random() * p.maxAge : 0;
    p.dead = false;
    p.retiring = false;
    p.retire = 0;
    return p;
  }

  /**
   * How many particles for this canvas.
   *
   * Proportional to canvas WIDTH, after windy.js -- a wider canvas has
   * more room to fill, and that is the whole of it. It used to compound
   * with zoom, which was really compensating for streak length growing
   * with zoom; now that length is held constant on screen, density
   * should be too, and the zoom term was doing nothing but thinning the
   * field exactly where it was already densest.
   *
   * ``particleCount``, if given, wins outright.
   *
   * No clamps: width x density cannot run away the way the old
   * zoom-compounding formula could, which is what the floor and ceiling
   * were guarding against.
   */
  function countFor(cfg, width) {
    if (cfg.count !== null) return cfg.count;
    return Math.max(0, Math.round(width * cfg.density));
  }

  /**
   * Where the particles start.
   *
   * ``random`` scatters them, which is what a flow field usually wants:
   * the eye reads the streaks and not their starting points. The two
   * lattice modes trade that for even coverage, which is easier to read
   * on a sparse field and is how a barb or quiver plot is laid out.
   *
   * ``grid`` is a strict lattice. ``randomGrid`` is the same lattice
   * with ONE random offset applied to the whole of it -- so the spacing
   * stays even but the rows do not land in the same place every time,
   * which stops the pattern reading as a printed overlay.
   *
   * The lattice is sized so its cells are square and its count lands as
   * close to ``n`` as a rectangle allows; the exact count is whatever
   * the grid comes to, since an even lattice matters more here than
   * hitting the number precisely.
   */
  function layout(st, n) {
    var cfg = st.cfg, w = st.w, h = st.h, out = [];
    if (n <= 0 || !w || !h) return out;

    if (cfg.layout !== "grid" && cfg.layout !== "randomGrid") {
      for (var i = 0; i < n; i++) out.push(null);   // positions come later
      return out;
    }

    // Square cells: cols/rows in the ratio of the canvas, product ~n.
    var cell = Math.sqrt((w * h) / n);
    var cols = Math.max(1, Math.round(w / cell));
    var rows = Math.max(1, Math.round(h / cell));
    var dx = w / cols, dy = h / rows;
    // One offset for the whole lattice, not per cell -- jittering each
    // point separately would just be `random` with extra steps.
    var offx = cfg.layout === "randomGrid" ? Math.random() * dx : dx / 2;
    var offy = cfg.layout === "randomGrid" ? Math.random() * dy : dy / 2;
    for (var r = 0; r < rows; r++) {
      for (var c = 0; c < cols; c++) {
        out.push([c * dx + offx, r * dy + offy]);
      }
    }
    return out;
  }

  function seed(st) {
    var n = countFor(st.cfg, st.w);
    var homes = layout(st, n);
    st.count = homes.length;
    var ps = new Array(homes.length);
    for (var i = 0; i < homes.length; i++) {
      var p = {};
      if (homes[i]) { p.hx = homes[i][0]; p.hy = homes[i][1]; }
      ps[i] = respawn(st, p, true);
    }
    st.particles = ps;
  }

  function frame(st) {
    if (!st.ctx || !st.particles || !st.field) return;
    var ctx = st.ctx, cfg = st.cfg, ps = st.particles;
    var n = cfg.trailLength;

    ctx.clearRect(0, 0, st.w, st.h);
    ctx.lineCap = cfg.lineCap;

    // --- advance, recording each new position ------------------------
    //
    // Everything expensive moved into buildField: the projection,
    // cos(lat), the zoom normalisation, the speed clamp and the tile
    // lookup all happen once per grid cell when the view settles. What
    // is left per particle per frame is one grid read and two adds.
    for (var i = 0; i < ps.length; i++) {
      var p = ps[i];
      if (p.dead) { respawn(st, p, false); continue; }

      // A retiring particle KEEPS FLYING; only its allowance of trail
      // shrinks, so the tail catches up to a head that is still moving.
      //
      // The first version froze the particle and retracted the trail
      // into it. That consumed the tail first, which is the direction
      // asked for -- but a stationary streak among moving ones reads as
      // drifting backwards, because everything else is still going
      // forward. Letting it fly keeps the motion of the fade in the
      // same direction as the motion of the particle; the streak simply
      // gets shorter until it is gone.
      if (p.retiring) {
        p.retire -= 1;
        if (p.retire <= 0) { p.dead = true; continue; }
      }

      // Off the canvas draws nothing, so recycle it into the view. The
      // margin lets a trail that is entering already be grown.
      if (p.x < -CULL_MARGIN || p.x > st.w + CULL_MARGIN ||
          p.y < -CULL_MARGIN || p.y > st.h + CULL_MARGIN) {
        p.dead = true;
        continue;
      }

      var d = fieldAt(st, p.x, p.y);
      // A gap in the grid, or its edge. Age the particle out rather
      // than freezing it in place.
      if (!d) {
        p.age += 1;
        if (p.age > p.maxAge && !p.retiring) {
          p.retiring = true;
          p.retire = p.xs.length;
        }
        continue;
      }

      p.x += d[0];
      p.y += d[1];
      p.xs.push(p.x); p.ys.push(p.y);
      // Trim from the OLDEST end. While retiring the allowance shrinks
      // by one each frame, so the trail is eaten tail-first while the
      // head carries on.
      var cap = p.retiring ? p.retire : n;
      while (p.xs.length > cap) { p.xs.shift(); p.ys.shift(); }

      p.age += 1;
      if (p.age > p.maxAge && !p.retiring) {
        p.retiring = true;
        p.retire = p.xs.length;      // fade over the trail it actually has
      }
    }

    // --- stroke in BANDS, oldest first --------------------------------
    //
    // One pass per band rather than per trail segment. Stroking by
    // segment meant iterating every particle 25 times a frame and
    // emitting an isolated moveTo+lineTo for each: 148,750 canvas path
    // operations per frame at the defaults, 8.9 million a second, which
    // is what made the animation choppy. The old fade-based renderer did
    // one pass; this was 25x that.
    //
    // A band covers a contiguous run of a trail and draws it as a
    // POLYLINE -- one moveTo and then lineTo per point -- at a single
    // alpha. Eight bands are visually indistinguishable from
    // twenty-five, because the alpha ramp is smooth and each step falls
    // a few pixels along a thin translucent streak, but it cuts the
    // particle visits by two thirds and the path operations by a third.
    var r = cfg.rgb[0], g = cfg.rgb[1], bl = cfg.rgb[2];
    var segs = n - 1;
    var bands = Math.min(segs, TRAIL_BANDS);
    for (var b = 0; b < bands; b++) {
      // ``taper`` above 1 pushes the fade toward the tail, which is what
      // makes the shape read as a comet rather than a wedge.
      var t = (b + 1) / bands;
      var alpha = cfg.opacity * Math.pow(t, cfg.taper);
      // Width ramps minWidth -> maxWidth across the trail, so the head
      // needs no special case: at t = 1 it already IS maxWidth. Only the
      // alpha gets a discontinuity, which is what makes the tip read as
      // a highlight rather than merely the widest part.
      var width = cfg.minWidth + (cfg.maxWidth - cfg.minWidth) * t;
      if (b === bands - 1) alpha = Math.min(1, cfg.opacity * cfg.headBoost);
      ctx.strokeStyle = "rgba(" + r + "," + g + "," + bl + "," + alpha + ")";
      ctx.lineWidth = width;
      // Almost every trail is full length, so cut that case ONCE per
      // band rather than re-dividing per particle. Doing it inside the
      // particle loop cost two divisions and two floors on every visit
      // -- 47,600 a frame -- and made banding slower than the
      // per-segment version it was meant to replace.
      var fi0 = Math.floor((b * segs) / bands);
      var fi1 = Math.floor(((b + 1) * segs) / bands);
      ctx.beginPath();
      for (var j = 0; j < ps.length; j++) {
        var pp = ps[j];
        var len = pp.xs ? pp.xs.length : 0;
        if (len < 2) continue;
        // Bands are cut over the trail the particle ACTUALLY has, so a
        // half-grown or retiring trail still tapers across its whole
        // length instead of losing its head.
        var own = len - 1, i0, i1;
        if (own === segs) {
          i0 = fi0; i1 = fi1;
        } else {
          i0 = Math.floor((b * own) / bands);
          i1 = Math.floor(((b + 1) * own) / bands);
        }
        if (i1 <= i0) continue;
        // Adjacent bands share an endpoint, so the polylines join with
        // no gap at the seam.
        ctx.moveTo(pp.xs[i0], pp.ys[i0]);
        for (var k = i0 + 1; k <= i1; k++) ctx.lineTo(pp.xs[k], pp.ys[k]);
      }
      ctx.stroke();
    }
  }

  function anyRunning() {
    for (var id in adopted) if (adopted[id].running) return true;
    return false;
  }

  /** Rebuild the field if the view moved, or if tiles only arrived
   *  after the last attempt. One string compare when nothing changed. */
  function ensureField(st) {
    if (st.fieldAny && st.fieldKey === viewKey(st)) return true;
    // Throttled while incomplete -- but only when there is already a
    // field to draw. With nothing on screen, rebuild as fast as tiles
    // allow: waiting 150 ms between attempts on first load would show
    // an empty map for no reason.
    if (st.fieldAny && st.buildAgainAt && nowMs() < st.buildAgainAt) {
      return true;                     // keep drawing what is already up
    }
    return buildField(st);
  }

  function tick(ts) {
    rafId = null;
    // rAF fires at the display rate; render only every FRAME_MS. The
    // timestamp rAF hands in is monotonic, so this does not drift the
    // way Date.now() would across a clock change.
    var now = ts || (global.performance && global.performance.now
                     ? global.performance.now() : Date.now());
    if (now - lastFrameAt >= FRAME_MS) {
      lastFrameAt = now;
      for (var id in adopted) {
        var st = adopted[id];
        if (!st.running) continue;
        // The raster first: it is what the trails are drawn over, and
        // it repaints only when the view or the hour actually moved.
        ensureSpeedRaster(st);
        if (!ensureField(st)) continue;   // tiles not in yet; retry next frame
        if (!st.particles) seed(st);
        frame(st);
      }
    }
    if (anyRunning()) rafId = global.requestAnimationFrame(tick);
  }

  /**
   * Put the canvas at its layer's place in the stack.
   *
   * ``map.overlayMapTypes`` render as containers inside the ``mapPane``
   * pane, stacked with small z-indexes matching their array index. The
   * canvas is appended to that same pane (see ``onAdd``) precisely so
   * this z-index orders it against them.
   *
   * It did not used to be. The canvas lived in ``overlayLayer``, a pane
   * ABOVE mapPane, so this number ordered the two wind canvases against
   * each other and nothing else -- no tile layer could be brought above
   * the wind, whatever the layer list said.
   *
   * ``layerId`` is the index the viewer passes to
   * ``overlayMapTypes.setAt``, so matching it puts the particles in the
   * same stack the rasters use.
   *
   * It has to be RE-APPLIED, not set once: dragging a layer runs
   * updateMapLayerOrder, which reassigns every layer.layerId and
   * re-adds the rasters at their new index. A z-index written at
   * adoption keeps the order the list had when the layer was created,
   * which is why dragging a raster above the particles did nothing.
   */
  function applyStacking(st, canvas) {
    // BOTH canvases when no particular one is named.
    //
    // The speed raster used to be stacked exactly once, in onAdd, while
    // the refresh tick restacked only the particles. A drag then split
    // the layer in half: the trails moved to the layer's new depth and
    // the colored field stayed at the depth it was created at, so a
    // wind layer dragged above another had its raster still underneath.
    if (!canvas) {
      if (st.speedCanvas) applyStacking(st, st.speedCanvas);
      if (st.canvas) applyStacking(st, st.canvas);
      return;
    }
    var c = canvas;
    if (!c) return;
    var reg = registry();
    // st.frameId, not st.id. For a time lapse st.id is the GROUP key
    // ("tl:<timeLapseID>"), which is not a registry entry at all -- this
    // found nothing and returned, so the lapse's canvas never got a
    // z-index and dragging the lapse in the layer list left the
    // particles where they were. The showing frame is a real layer and
    // carries the layerId the viewer is using. For a plain layer
    // frameId and id are the same thing.
    var L = reg && reg[st.frameId];
    if (!L || typeof L.layerId !== "number") return;
    var z = String(L.layerId);
    if (c.style.zIndex !== z) c.style.zIndex = z;
  }

  /** Element alpha, written only when it actually changed. */
  function setCanvasAlpha(el, a) {
    if (!el) return;
    var v = String(a === undefined || a === null ? 1 : a);
    if (el.style.opacity !== v) el.style.opacity = v;
  }

  /** Take an overlay off the map and out of the DOM, for good. */
  function dropOverlay(st) {
    st.running = false;
    try {
      if (st.overlay && st.overlay.setMap) st.overlay.setMap(null);
    } catch (e) { /* already detached */ }
    [st.canvas, st.speedCanvas].forEach(function (c) {
      if (c && c.parentNode) c.parentNode.removeChild(c);
    });
    st.canvas = st.ctx = st.speedCanvas = st.speedCtx = null;
    // Drop the decoded tiles too. They are the big allocation here --
    // a frame's worth is megabytes, and a lapse holds one per frame.
    st.tiles = Object.create(null);
    st.field = st.fieldOk = st.fieldB = st.fieldOkB = null;
    st.particles = null;
  }

  function refreshRunState() {
    var reg = registry();
    var pageVisible = !global.document || !global.document.hidden;
    for (var id in adopted) {
      var st = adopted[id];

      // Gone entirely? Map.clearMap() and a re-add empty the registry,
      // and an overlay whose every frame has disappeared has nothing
      // left to draw. Without this its canvases stay in the pane for
      // the life of the page -- cleared, so nothing shows, but
      // accumulating one pair per wind layer ever added, each still
      // answering the idle and resize handlers.
      var stillThere = false;
      for (var lid in st.frames) {
        if (reg && reg[lid]) { stillThere = true; break; }
      }
      if (!stillThere) { dropOverlay(st); delete adopted[id]; continue; }

      // Which frame is on? NOT the one whose checkbox is ticked.
      //
      // A geeImage time lapse turns EVERY frame's visibility on at once
      // -- turnOnTimeLapseLayers() clicks all of them -- and then picks
      // the current frame with the OPACITY slider: selectFrame() zeroes
      // every frame and raises just the one. Only a tileMapService
      // lapse advances by clicking a checkbox. Reading `visible` here
      // pinned the particles to frame 0 forever; they animated
      // perfectly well, through a field that never changed, which is
      // the kind of wrong that looks right.
      //
      // Cumulative mode raises frames 0..current to the SAME opacity,
      // so the current one is the LAST non-zero in frame order -- hence
      // >= on the tie rather than >. "Frame order" is st.frames'
      // insertion order, i.e. the order the viewer registered the
      // layers, which is the order its own `sliders` array is built in
      // and therefore the order selectFrame indexes. It is NOT sorted
      // by date -- an observed registry ran ...0919-06 before
      // ...0919-00 -- but slider order is the one that matters here.
      var shown = null, anyFrame = false, best = 0, anyVisible = false;
      for (var fid in st.frames) {
        anyFrame = true;
        var FL = reg && reg[fid];
        if (!FL || FL.visible === false) continue;
        anyVisible = true;
        if (!st.isLapse) { if (shown === null) shown = fid; continue; }
        // Undefined opacity means the viewer has not built the slider
        // yet; treat it as shown so a lapse of one frame still runs.
        var op = typeof FL.opacity === "number" ? FL.opacity : 1;
        if (op > 0 && op >= best) { best = op; shown = fid; }
      }
      // Dragging a lapse's opacity to zero is not the same as switching
      // it off. Every frame goes to 0 and no frame looks "raised", but
      // the lapse is still playing and its checkbox is still ticked --
      // so keep the frame already showing rather than stopping. Off is
      // `visible === false`, which is handled above.
      if (st.isLapse && !shown && anyVisible) shown = st.frameId;
      if (shown && shown !== st.frameId) {
        // Swap which decoded field the particles sample. Deliberately
        // NOT resetting st.particles: the trails carry on advecting
        // through the new field, which is the whole point of one
        // overlay per lapse. Resetting here would scatter fresh
        // particles on every frame and play as stutter.
        st.frameId = shown;
        st.getTileUrl = st.frames[shown];
        st.fieldKey = null;            // resample from the cache
        st.buildAgainAt = 0;           // and do it now, not after a back-off
        st.speedKey = null;            // the raster is a frame behind too
        st.paintAgainAt = 0;
        // Warm the hours after this one while this one plays. By the
        // time the lapse steps again their tiles are decoded and the
        // rebuild is pure arithmetic with nothing to wait for.
        warmNextFrames(st);
      }

      var L = reg && reg[st.frameId];
      var want = pageVisible && inView &&
                 (anyFrame ? anyVisible : (L ? L.visible !== false : true));
      if (want !== st.running) {
        st.running = want;
        if (!want) {
          // BOTH canvases. Clearing only the particle one left the
          // speed raster painted over the map after the layer was
          // switched off -- the trails vanished, the colours did not,
          // and nothing in the panel could get rid of them. The raster
          // is not redrawn by tick() while stopped, so a stale paint
          // simply stays until something else happens to repaint it.
          if (st.ctx) st.ctx.clearRect(0, 0, st.w, st.h);
          if (st.speedCtx) {
            st.speedCtx.clearRect(0, 0, st.w, st.h);
            // ...and forget the paint, or coming back on would find a
            // matching key and skip the repaint it now needs.
            st.speedKey = null;
            st.paintAgainAt = 0;
          }
        }
        // Only a genuine off->on gets a fresh scatter. A frame change
        // does not pass through here, so trails survive it.
        if (want) st.particles = null;
      }
      // Follow the opacity sliders.
      //
      // The dimmers ride on the CANVAS ELEMENTS, not on the stroke
      // alpha. cfg.opacity is the SHAPE of a trail's fade -- taper,
      // head boost -- so rewriting it per drag both discarded the
      // configured look and changed instantly. Element opacity scales
      // the finished picture, and CSS eases it over FADE_MS for free.
      //
      // A LAPSE's per-frame opacities are the frame-SELECTION
      // mechanism, eight of nine sitting at 0 at any instant, so only
      // RAISED frames are read. selectFrame() zeroes every frame and
      // then raises one; a refresh landing between those two steps
      // would see 0 and blank the raster -- on every step of a playing
      // lapse, which is a strobe. The last positive value stands until
      // a new one arrives.
      if (L && typeof L.opacity === "number") {
        if (st.isLapse) {
          if (best > 0) st.cfg.speedOpacity = best;
        } else {
          st.cfg.speedOpacity = L.opacity;
        }
      }
      if (st.cfg.speedRaster && !st.sliderAdded) addParticleSlider(st);
      if (st.cfg.speedRaster && !st.queryRetargeted) retargetQuery(st);
      if (st.cfg.speedRaster && !st.legendStyled) restyleLegend(st);
      setCanvasAlpha(st.speedCanvas, st.cfg.speedOpacity);
      setCanvasAlpha(st.canvas, st.cfg.speedRaster
          ? st.particleDim
          : st.cfg.speedOpacity);
      // Re-checking the layer makes the viewer rebuild and re-add the
      // encoded RGB. Undo it here rather than in scan(), which skips
      // anything already adopted. Re-adding also re-flips loading via
      // the viewer's getTileUrl, so the progress report belongs on the
      // same tick.
      // Detach EVERY frame, not just the showing one: an unhidden
      // frame would paint the encoded u/v RGB over the map as a
      // magenta-green wash.
      if (anyFrame) {
        for (var dfid in st.frames) {
          var DL = reg && reg[dfid];
          if (DL) detach(DL);
        }
        reportProgress(st); applyStacking(st);
      } else if (L) { detach(L); reportProgress(st); applyStacking(st); }
    }
    if (anyRunning() && rafId === null) rafId = global.requestAnimationFrame(tick);
  }

  /**
   * Stop animating when the map scrolls off screen; resume when it is
   * back.
   *
   * Observes the map's own container rather than a canvas: the canvases
   * come and go as layers are added and removed, and the container is
   * the thing whose position on the page actually decides whether any
   * of this is visible.
   *
   * The threshold is 0, so "in view" means any part of the map is —
   * a map half past the fold is still worth animating, and a stricter
   * threshold would stop it while the user is looking at it.
   *
   * No-ops where IntersectionObserver is absent, leaving ``inView``
   * true; the animation then behaves exactly as it did before.
   */
  function observeInView() {
    if (!global.IntersectionObserver || !global.map ||
        typeof global.map.getDiv !== "function") {
      return;
    }
    var el;
    try {
      el = global.map.getDiv();
    } catch (e) {
      return;
    }
    if (!el) return;
    try {
      var io = new global.IntersectionObserver(function (entries) {
        for (var i = 0; i < entries.length; i++) {
          var next = !!entries[i].isIntersecting;
          if (next === inView) continue;
          inView = next;
          // Reseeding on the way back in is what refreshRunState
          // already does for any layer it switches on, so the particles
          // come back in the current view rather than resuming from
          // wherever they were when the map left the screen.
          refreshRunState();
        }
      }, { threshold: 0 });
      io.observe(el);
    } catch (e) {
      inView = true;
    }
  }

  function bindOnce() {
    if (bound || !global.map) return;
    // Rebuild on idle -- once when movement STOPS, not during a drag.
    // A pan invalidates the whole field: canvas pixel (0, 0) means a
    // different place on the globe afterwards, so every cached vector is
    // wrong. Zoom and resize likewise.
    global.map.addListener("idle", function () {
      for (var id in adopted) {
        // Drop the KEY, not the arrays: buildField refills them in
        // place unless the canvas itself changed size.
        adopted[id].fieldKey = null;
        adopted[id].speedKey = null;      // and the raster, likewise
        adopted[id].paintAgainAt = 0;
        adopted[id].buildAgainAt = 0;
        adopted[id].particles = null;     // reseed into the new view
        // A pan or zoom invalidates every frame's warmed tiles, not
        // just the one showing -- the view covers different tiles now.
        warmNextFrames(adopted[id]);
      }
      refreshRunState();
    });
    if (global.document) {
      global.document.addEventListener("visibilitychange", refreshRunState);
    }
    observeInView();
    global.setInterval(refreshRunState, 500);
    bound = true;
  }

  /**
   * Every knob that governs how the particles look and move.
   *
   * Grouped as COUNT, SIZE, SHAPE, SPEED, LIFETIME, COLOR. Defaults are
   * the windy.com-alike look; each is overridable per layer through the
   * viz dict, and geeViz stamps all of them from Python so a hand-built
   * layer and a `Map.addWindLayer` layer behave identically.
   */
  function cfgFrom(viz) {
    var v = viz || {};

    // Widths derive from one base weight, so raising the weight scales
    // the whole taper rather than only its midpoint. Explicit min/max
    // win when given -- same pattern as minAge tracking maxAge.
    var weight = v.particleStrokeWeight !== undefined
      ? v.particleStrokeWeight
      : (v.particleLineWidth !== undefined ? v.particleLineWidth : 1.1);

    var maxAge = v.particleMaxAge || 45;

    return {
      // ---- count ---------------------------------------------------
      // Proportional to canvas WIDTH, after windy.js: a wider canvas has
      // more room to fill, and that is the whole of it. ~3000 particles
      // on a 1700 px canvas. particleCount, if given, wins outright.
      //
      // No floor or ceiling: width x density cannot run away the way the
      // old zoom-compounding formula could. A phone gives ~560, a 5K
      // display ~9000, and both are the right answer for their screen.
      count: v.particleCount !== undefined && v.particleCount !== null
        ? v.particleCount : null,
      density: v.particleDensity !== undefined ? v.particleDensity : 1.2,
      // "random" (default) | "randomGrid" | "grid" -- see layout().
      layout: v.particleLayout === "grid" || v.particleLayout === "randomGrid"
        ? v.particleLayout : "random",

      // ---- size ----------------------------------------------------
      // strokeWeight is the base; minWidth and maxWidth are the
      // ABSOLUTE pixel widths at the tail and at the head, and the taper
      // ramps between them. A comet is thin at the tail and fat at the
      // tip, so maxWidth > minWidth; equal values give a constant-width
      // ribbon.
      //
      // WIDTH is across the streak; LENGTH along it is
      // particleTrailLength. The two dimensions are named for what they
      // measure.
      strokeWeight: weight,
      minWidth: v.particleMinWidth !== undefined
        ? v.particleMinWidth : weight * 0.45,
      maxWidth: v.particleMaxWidth !== undefined
        ? v.particleMaxWidth : weight * 1.5,

      // ---- shape ---------------------------------------------------
      // How many frames of history each trail draws. This, times the
      // per-frame step, IS the streak length -- an explicit number now,
      // where it used to be an emergent property of a fade constant.
      trailLength: Math.max(2, v.particleTrailLength || 13),
      // Exponent on the tail fade. 1 is a linear wedge; above 1 the
      // faint part stretches out and the shape reads as a comet.
      taper: v.particleTaper !== undefined ? v.particleTaper : 2.1,
      // The leading segment's alpha multiplier -- the bright tip.
      headBoost: v.particleHeadBoost !== undefined ? v.particleHeadBoost : 1.6,
      // "round" gives tapered tips; "butt" gives blunt ones.
      lineCap: v.particleLineCap || "round",

      // ---- speed ---------------------------------------------------
      // Pixels per frame for each m/s of wind, at the equator.
      //
      // This one number replaced a speed factor AND a reference zoom.
      // Screen speed was `speedFactor * 2^(zoomRef - zoom) / metresPerPixel`,
      // and metresPerPixel is `156543 * cos(lat) / 2^zoom` -- so the two
      // powers of two cancelled exactly and the whole expression reduced
      // to a constant over cos(lat). Zoom does not appear at all, which
      // is the same thing as saying a streak is the same size on screen
      // at every zoom.
      speed: v.particleSpeed !== undefined ? v.particleSpeed : 0.5,
      // Apparent-speed FLOOR and CEILING, m/s, applied to the advection
      // only. Length is proportional to speed, so without a floor a
      // light breeze draws a dot and a calm map reads as a broken one;
      // without a ceiling a cyclone core smears clear across the
      // screen. Direction is preserved either way, and the speed raster
      // and the click query still report the true value.
      // The speed raster's stretch, in m/s. Sent by
      // geeViz.weather.addWindLayer, derived there from viz min/max and
      // units -- not knobs of this renderer. The fallbacks cover a
      // hand-built layer that supplies neither.
      minSpeed: v.windMinSpeedMs !== undefined ? v.windMinSpeedMs : 1.0,
      maxSpeed: v.windMaxSpeedMs !== undefined ? v.windMaxSpeedMs : 15.0,

      // ---- lifetime ------------------------------------------------
      maxAge: maxAge,
      // A quarter of the maximum by default, so the shortest streaks
      // are visibly stubs against the longest. Set them equal to get a
      // uniform comb.
      minAge: v.particleMinAge !== undefined ? v.particleMinAge : maxAge * 0.25,

      // ---- color ---------------------------------------------------
      opacity: v.particleOpacity !== undefined ? v.particleOpacity : 0.9,
      // The configured value, kept unscaled. cfg.opacity is what the
      // renderer reads and the layer's opacity slider multiplies into,
      // so without a pristine copy each slider move would compound on
      // the last and the particles would fade to nothing in a few drags.
      baseOpacity: v.particleOpacity !== undefined ? v.particleOpacity : 0.9,

      // ---- the speed raster, when this layer draws its own ----------
      // windSpeedRaster says the layer is the merged kind: one set of
      // u/v tiles behind BOTH the colored speed field and the trails.
      speedRaster: !!v.windSpeedRaster,
      rampPalette: v.windSpeedPalette || [],
      // Unclamped bounds -- see weather.py. windMinSpeedMs carries a
      // 1 m/s advection floor that must not reach the colors.
      rampMinMs: v.windRampMinMs !== undefined ? v.windRampMinMs : 0,
      rampMaxMs: v.windRampMaxMs !== undefined ? v.windRampMaxMs : 40,
      // ...and the same stretch in display units, for the legend ends.
      rampMin: v.windRampMin,
      rampMax: v.windRampMax,
      units: v.windUnits || "",
      // Its own alpha, independent of the particles'. Driven by the
      // lapse's existing opacity slider; the particles get their own.
      speedOpacity: 1,
      // The speed/direction collection, serialized. See retargetQuery.
      queryItemJson: v.windQueryItem || null,
      rgb: hexToRgb(v.particleColor || "#fff"),

      // Sent by geeViz.weather.addWindLayer. Reading them rather than
      // trusting a second copy is what keeps encoder and decoder in
      // lockstep: a mismatch would not throw, it would yield winds wrong
      // by a scale and offset, which still look like weather.
      tileMin: v.windTileMin !== undefined ? v.windTileMin : TILE_MIN,
      tileMax: v.windTileMax !== undefined ? v.windTileMax : TILE_MAX,
    };
  }

  function scan() {
    // Cheap and idempotent; the viewer defines
    // updateMapLayerOrder well before any layer exists, but
    // this file makes no assumption about load order.
    patchReorder();
    var reg = registry();
    if (!reg || !global.map) return;
    for (var id in reg) {
      if (adopted[id]) continue;
      var L = reg[id];
      if (!L || !L.viz || !L.viz.windParticles) continue;

      // Every frame of a time lapse is its own geeImage layer, and they
      // all carry windParticles. Adopting each one would stack N
      // particle fields on the map at once. Group them instead: the
      // viewer stamps viz.timeLapseID on every frame, so that is the
      // overlay's identity and the layer id becomes a frame within it.
      var gid = (L.viz.timeLapseID ? "tl:" + L.viz.timeLapseID : id);
      if (adopted[gid]) {
        var g = adopted[gid];
        // Same guard the single-layer path below uses: the viewer
        // creates the registry entry before it mints the ImageMapType,
        // so L.layer is undefined for a beat and findTileUrlFn throws
        // on it. A time lapse adds N frames, so this window is hit N
        // times per scan instead of once.
        if (!g.frames[id] && L.layer) {
          var fn = findTileUrlFn(L.layer);
          if (fn) { g.frames[id] = fn; detach(L); reportProgress(g); }
        }
        continue;
      }
      // Needs the ImageMapType the viewer built; that is where the tile
      // URL lives.
      if (!L.layer) continue;
      var getUrl = findTileUrlFn(L.layer);
      if (!getUrl) continue;                 // tiles not minted yet
      detach(L);

      var st = {
        id: gid, getTileUrl: getUrl, cfg: cfgFrom(L.viz),
        // frames: layerId -> getTileUrl. One entry for a plain layer,
        // one per frame for a lapse. frameId says which is showing.
        frames: (function (o) { o[id] = getUrl; return o; })(
            Object.create(null)),
        frameId: id,
        isLapse: !!L.viz.timeLapseID,
        tiles: Object.create(null), tileFails: Object.create(null),
        tileZoom: 4,
        field: null, fieldOk: null, fieldW: 0, fieldH: 0,
        // The scratch half of the double buffer, and the back-off clock
        // for builds that came out incomplete. See buildField.
        fieldB: null, fieldOkB: null, fieldBW: 0, fieldBH: 0,
        buildAgainAt: 0,
        // 0..1 from the injected particle-opacity slider, starting
        // where the viz says. The viewer has no idea this second
        // control exists, so unlike the raster's -- which is the
        // layer's own slider and gets `opacity` for free -- this one
        // has to be told. It sat hard-coded at 1, which is why setting
        // `opacity` dimmed the speed field and left the flow alone.
        particleDim: initialDim(L.viz), sliderAdded: false,
        queryRetargeted: false,
        legendStyled: false,
        speedCanvas: null, speedCtx: null, speedKey: null, rampLut: null,
        paintAgainAt: 0,
        fieldSpacing: FIELD_SPACING, fieldKey: null, fieldAny: false,
        canvas: null, ctx: null, particles: null, running: false,
        inflight: 0, burst: 0,
        origin: { x: 0, y: 0 }, proj: null, w: 0, h: 0, warned: false,
      };
      st.overlay = makeOverlay(st);
      st.overlay.setMap(global.map);
      adopted[gid] = st;
      // findTileUrlFn probes the viewer's own getTileUrl, which flips
      // layer.loading = true as a side effect. Settle it now: if this
      // layer never requests a tile (it is switched off, say) nothing
      // else would, and the spinner would spin on an idle layer.
      reportProgress(st);
      bindOnce();
      if (st.cfg.speedRaster) {
        addParticleSlider(st); retargetQuery(st); restyleLegend(st);
      }
      refreshRunState();
    }
  }


  /**
   * Make a drag-reorder land on the wind layers at the same instant it
   * lands on everything else.
   *
   * ``updateMapLayerOrder`` is what the sortable list calls on drop. It
   * reassigns every ``layerObj[id].layerId``, then re-adds each VISIBLE
   * layer with ``overlayMapTypes.setAt(layerId, layer.layer)`` -- and
   * for a wind layer that re-adds the encoded u/v RGB this module took
   * off the map, because as far as the viewer is concerned it is an
   * ordinary geeImage layer that someone removed behind its back.
   *
   * The refresh tick already repairs both halves of that: it re-detaches
   * the RGB and re-applies the z-index. But it runs on a 500 ms
   * interval, so a drop left up to half a second of the raw encoding
   * flashing magenta-green over the map, with the trails at their old
   * depth. Long enough to see every time.
   *
   * So: run the viewer's own function, then repair immediately, in the
   * same turn. Nothing is duplicated -- the tick does exactly this, just
   * later, and both operations are idempotent.
   *
   * Wrapped rather than replaced, and the original is kept: it is a
   * top-level function declaration, so the global binding and the window
   * property are one slot, and both the sortable's `update` and `stop`
   * handlers resolve through it.
   *
   * It is patched HERE, in this file, for the reason everything else
   * about wind lives here: lcms-viewer.min.js is built from another repo
   * and a change made inside it is a change the next rebuild can revert
   * without anyone noticing.
   */
  var reorderPatched = false;

  function patchReorder() {
    if (reorderPatched) return true;
    var orig = global.updateMapLayerOrder;
    if (typeof orig !== "function") return false;
    global.updateMapLayerOrder = function () {
      var r = orig.apply(this, arguments);
      try {
        var reg = registry();
        for (var id in adopted) {
          var st = adopted[id];
          // Every frame, not just the showing one: a lapse re-adds all
          // of them and an unhidden frame is a magenta-green wash.
          for (var fid in st.frames) {
            var L = reg && reg[fid];
            if (L) detach(L);
          }
          applyStacking(st);
        }
      } catch (e) {
        // A repair that throws must not take the viewer's own reorder
        // down with it -- the drop has already been applied, and the
        // refresh tick will catch up regardless.
        if (global.console && console.warn) {
          console.warn("wind-particles: reorder repair failed", e);
        }
      }
      return r;
    };
    global.updateMapLayerOrder._geeVizOriginal = orig;
    reorderPatched = true;
    return true;
  }

  if (typeof setInterval === "function") setInterval(scan, 600);

  /** Advance N frames synchronously. Testing seam: rAF is throttled to a
   *  standstill in a tab that is not foreground, so an automated check of
   *  the rendering cannot rely on the animation loop running at all. */
  function step(id, n) {
    var st = adopted[id];
    if (!st) return null;
    ensureField(st);
    if (!st.particles) seed(st);
    for (var i = 0; i < (n || 1); i++) frame(st);
    var alive = 0;
    for (var j = 0; j < st.particles.length; j++) if (!st.particles[j].dead) alive++;
    return { particles: st.particles.length, alive: alive,
             tilesCached: Object.keys(st.tiles).length };
  }

  global.geeVizWindParticles = {
    scan: scan,
    step: step,
    status: function (id) {
      var st = adopted[id];
      if (!st) return null;
      var ok = 0, pending = 0, bad = 0;
      for (var k in st.tiles) {
        if (st.tiles[k] === null) pending++;
        else if (st.tiles[k] === false) bad++;
        else ok++;
      }
      return { id: id, running: st.running, tileZoom: st.tileZoom,
               baseCount: st.cfg.count,
               countFor: countFor(st.cfg, st.w),
               fieldCells: st.field ? st.fieldW * st.fieldH : 0,
               particles: st.particles ? st.particles.length : 0,
               tiles: { ok: ok, pending: pending, failed: bad } };
    },
    // Testing seams. _frame is here so the per-frame cost can be
    // BENCHMARKED off-browser, with the canvas stubbed -- guessing at
    // render cost from the source is how a 3x regression hides.
    _frame: frame,
    // Benchmarking _frame without _seed measures nothing: the particle
    // objects frame() draws are built here, and a hand-rolled stand-in
    // has no trail history, so every particle is skipped and the op
    // count comes out flat regardless of how many there are.
    _seed: seed,
    _countFor: countFor,
    _layout: layout,
    _fieldAt: fieldAt,
    _buildField: buildField,
    _viewKey: viewKey,
    _sampleUV: sampleUV,
    _lonToTileX: lonToTileX,
    _latToTileY: latToTileY,
    _hexToRgb: hexToRgb,
    // The overlay table, and the tick that maintains it. A time lapse
    // is N registry layers behind ONE overlay, and which frame that
    // overlay is sampling is decided here rather than by the viewer --
    // so a test that cannot see `adopted` can only check that the
    // particles move, which they do whether or not the frame ever
    // advances. That is precisely the bug this pair exists to catch.
    _adopted: adopted,
    // The second opacity slider, and the two helpers that keep its
    // track looking like every other track in the panel. Exercised
    // rather than described: the viewer fades its own track as you drag
    // (setRangeSliderThumbOpacity) and a copy that silently does not is
    // invisible in the source and obvious on screen.
    _patchReorder: patchReorder,
    _applyStacking: applyStacking,
    _addParticleSlider: addParticleSlider,
    _rgbOfTrack: rgbOfTrack,
    _setTrackAlpha: setTrackAlpha,
    _initialDim: initialDim,
    _legendContainerIds: legendContainerIds,
    _refreshRunState: function () { return refreshRunState(); },
    // The tile fetch and the frame warmer. Their in-flight bookkeeping
    // is what buildField reads to decide a field is finished, and it is
    // asymmetric on purpose (a prefetch must not count) -- so it is
    // worth exercising rather than describing.
    _getTile: getTile,
    _warmNextFrames: warmNextFrames,
    _ensureField: ensureField,
    _renderSpeedRaster: renderSpeedRaster,
    _ensureSpeedRaster: ensureSpeedRaster,
    // The overlay's draw(), which places both canvases. Where the raster
    // sits against where it was painted for is the whole of the
    // fast-pan offset bug, and only running draw() can show it.
    _makeOverlay: makeOverlay,
    _speedCanvasAt: speedCanvasAt,
    _range: [TILE_MIN, TILE_MAX],
  };
})(typeof window !== "undefined" ? window : this);
