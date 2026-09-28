"""
View GEE objects using Python

geeViz.geeView is the core module for managing GEE objects on the geeViz mapper object. geeViz instantiates an instance of the `mapper` class as `Map` by default. Layers can be added to the map using `Map.addLayer` or `Map.addTimeLapse` and then viewed using the `Map.view` method.

"""

"""
    Copyright 2026 Ian Housman

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

# Script to allow GEE objects to be viewed in a web viewer
# Intended to work within the geeViz package
######################################################################
# Import modules
import ee, sys, os, webbrowser, json, socket, subprocess, site, datetime, requests, google, tempfile, signal, time
from google.auth.transport import requests as gReq
from google.oauth2 import service_account

from threading import Thread
from urllib.parse import urlparse
from IPython.display import IFrame, display, HTML

if sys.version_info[0] < 3:
    import SimpleHTTPServer, SocketServer
else:
    import http.server, socketserver


IS_COLAB = ee.oauth.in_colab_shell()  # "google.colab" in sys.modules
IS_WORKBENCH = os.getenv("DL_ANACONDA_HOME") != None
if IS_COLAB:
    from google.colab.output import eval_js

######################################################################
# Functions to handle various initialization/authentication workflows to try to get a user an initialized instance of ee


# Function to have user input a project id if one is still needed
def setProject(id):
    """
    Sets the project id of an instance of ee

    Args:
        id (str): Google Cloud Platform project id to use

    """
    
   
    ee.data.setCloudApiUserProject(id)

def simpleSetProject(overwrite=False,verbose=False):
    """
    Tries to find the current Google Cloud Platform project id and set it

    Args:
    overwrite (bool, optional): Whether or not to overwrite a cached project ID file

    """

    creds_path = ee.oauth.get_credentials_path()
    creds_dir = os.path.dirname(creds_path)
    if not os.path.exists(creds_dir):os.makedirs(creds_dir)

    provided_project = "{}.proj_id".format(creds_path)
    provided_project = os.path.normpath(provided_project)

    if not os.path.exists(provided_project) or overwrite:
        project_id = input("Please enter GEE project ID: ")

        print("You entered: {}".format(project_id))
        o = open(provided_project, "w")
        o.write(project_id)
        o.close()
    else:
        o = open(provided_project, "r")
        project_id = o.read()
        if verbose:
            print("Cached project id file path: {}".format(provided_project))
            print("Cached project id: {}".format(project_id))
        o.close()
    setProject(project_id)
    

def robustInitializer(verbose: bool = False):
    """Thin pointer to ``geeViz.eeAuth.robust_init`` — kept here for
    backwards compatibility with scripts that imported it from
    ``geeViz.geeView`` directly.

    The full decision tree (eeAuth proxy → EE refresh token → ADC fallback
    with explicit warning → interactive ``ee.Authenticate(force=True)``)
    lives in ``geeViz.eeAuth.eeCreds.EECreds.robust_init`` so it's
    usable from any geeViz entry point, not just module import.
    """
    from geeViz.eeAuth import robust_init as _robust_init
    return _robust_init(verbose=verbose)


robustInitializer()
######################################################################
# Set up GEE and paths
geeVizFolder = "geeViz"
geeViewFolder = "geeView"

# Set up template web viewer
# Do not change
cwd = os.getcwd()

paths = sys.path

py_viz_dir = os.path.dirname(__file__)

# print("geeViz package folder:", py_viz_dir)

# Specify location of files to run
template = os.path.join(py_viz_dir, geeViewFolder, "index.html")
ee_run_dir = os.path.join(py_viz_dir, geeViewFolder, "src/gee/gee-run/")
if os.path.exists(ee_run_dir) == False:
    os.makedirs(ee_run_dir)


######################################################################
######################################################################
# Functions
######################################################################
# Linear color gradient functions
##############################################################
##############################################################
def color_dict_maker(gradient: list[list[int]]) -> dict:
    """Takes in a list of RGB sub-lists and returns dictionary of
    colors in RGB and hex form for use in a graphing function
    defined later on"""
    return {
        "hex": [RGB_to_hex(RGB) for RGB in gradient],
        "r": [RGB[0] for RGB in gradient],
        "g": [RGB[1] for RGB in gradient],
        "b": [RGB[2] for RGB in gradient],
    }


# color functions adapted from bsou.io/posts/color-gradients-with-python
def hex_to_rgb(value: str) -> tuple:
    """Return (red, green, blue) for the color given as #rrggbb."""
    value = value.lstrip("#")
    lv = len(value)
    if lv == 3:
        lv = 6
        value = f"{value[0]}{value[0]}{value[1]}{value[1]}{value[2]}{value[2]}"

    return tuple(int(value[i : i + lv // 3], 16) for i in range(0, lv, lv // 3))


def RGB_to_hex(RGB: list[int]) -> str:
    """[255,255,255] -> "#FFFFFF" """
    # Components need to be integers for hex to make sense
    RGB = [int(x) for x in RGB]
    return "#" + "".join(["0{0:x}".format(v) if v < 16 else "{0:x}".format(v) for v in RGB])


def linear_gradient(start_hex: str, finish_hex: str = "#FFFFFF", n: int = 10) -> dict:
    """returns a gradient list of (n) colors between
    two hex colors. start_hex and finish_hex
    should be the full six-digit color string,
    inlcuding the number sign ("#FFFFFF")"""
    # Starting and ending colors in RGB form
    s = hex_to_rgb(start_hex)
    f = hex_to_rgb(finish_hex)
    # Initilize a list of the output colors with the starting color
    RGB_list = [s]
    # Calcuate a color at each evenly spaced value of t from 1 to n
    for t in range(1, n):
        # Interpolate RGB vector for color at the current value of t
        curr_vector = [int(s[j] + (float(t) / (n - 1)) * (f[j] - s[j])) for j in range(3)]
        # Add it to our list of output colors
        RGB_list.append(curr_vector)

    # print(RGB_list)
    return color_dict_maker(RGB_list)


def polylinear_gradient(colors: list[str], n: int):
    """returns a list of colors forming linear gradients between
    all sequential pairs of colors. "n" specifies the total
    number of desired output colors"""
    # The number of colors per individual linear gradient
    n_out = int(float(n) / (len(colors) - 1)) + 1

    # If we don't have an even number of color values, we will remove equally spaced values at the end.
    apply_offset = False
    if n % n_out != 0:
        apply_offset = True
        n_out = n_out + 1

    # returns dictionary defined by color_dict()
    gradient_dict = linear_gradient(colors[0], colors[1], n_out)

    if len(colors) > 1:
        for col in range(1, len(colors) - 1):
            next = linear_gradient(colors[col], colors[col + 1], n_out)
            for k in ("hex", "r", "g", "b"):
                # Exclude first point to avoid duplicates
                gradient_dict[k] += next[k][1:]

    # Remove equally spaced values here.
    if apply_offset:
        offset = len(gradient_dict["hex"]) - n
        sliceval = []

        for i in range(1, offset + 1):
            sliceval.append(int(len(gradient_dict["hex"]) * i / float(offset + 2)))

        for k in ("hex", "r", "g", "b"):
            gradient_dict[k] = [i for j, i in enumerate(gradient_dict[k]) if j not in sliceval]

    return gradient_dict


def get_poly_gradient_ct(palette: list[str], min: int, max: int) -> list[str]:
    """
    Take a palette and a set of min and max stretch values to get a 1:1 value to color hex list

    Args:
        palette (list): A list of hex code colors that will be interpolated

        min (int): The min value for the stretch

        max (int): The max value for the stretch

    Returns:
        list: A list of linearly interpolated hex codes where there is 1:1 color to value from min-max (inclusive)

    >>> import geeViz.geeView as gv
    >>> viz = {"palette": ["#FFFF00", "00F", "0FF", "FF0000"], "min": 1, "max": 20}
    >>> color_ramp = gv.get_poly_gradient_ct(viz["palette"], viz["min"], viz["max"])
    >>> print("Color ramp:", color_ramp)

    """
    ramp = polylinear_gradient(palette, max - min + 1)
    return ramp["hex"]


##############################################################
######################################################################
# Function to check if being run inside a notebook
# Taken from: https://stackoverflow.com/questions/15411967/how-can-i-check-if-code-is-executed-in-the-ipython-notebook
def is_notebook():
    """
    Check if inside Jupyter shell


    Returns:
        bool: Whether inside Jupyter shell or not
    """
    return ee.oauth._in_jupyter_shell()


######################################################################
# Function for cleaning trailing .... in accessToken
def cleanAccessToken(accessToken):
    """
    Remove trailing '....' in generated access token

    Args:
        accessToken (str): Raw access token

    Returns:
        str: Given access token without trailing '....'
    """
    while accessToken[-1] == ".":
        accessToken = accessToken[:-1]
    return accessToken


######################################################################
# Function to get domain base without any folders
def baseDomain(url):
    """
    Get root domain for a given url

    Args:
        url (str): URL to find the base domain of

    Returns:
        str: domain of given URL
    """
    url_parts = urlparse(url)
    return f"{url_parts.scheme}://{url_parts.netloc}"


######################################################################
# Function for using default GEE refresh token to get an access token for geeView
# Updated 12/23 to reflect updated auth methods for GEE
def refreshToken():
    """
    Get a refresh token from currently authenticated ee instance

    Returns:
        str: temporary access token
    """
    credentials = ee.data.get_persistent_credentials()
    credentials.refresh(gReq.Request())
    accessToken = credentials.token
    # print(credentials.to_json())
    accessToken = cleanAccessToken(accessToken)
    return accessToken


######################################################################
# Function for using a GEE white-listed service account key to get an access token for geeView
def serviceAccountToken(service_key_file_path):
    """
    Get a refresh token from service account key file credentials

    Returns:
        str: temporary access token
    """
    try:
        credentials = service_account.Credentials.from_service_account_file(service_key_file_path, scopes=ee.oauth.SCOPES)
        credentials.refresh(gReq.Request())
        accessToken = credentials.token
        accessToken = cleanAccessToken(accessToken)
        return accessToken
    except Exception as e:
        print(e)
        print("Failed to utilize service account key file.")
        return None


######################################################################
# In-process threaded HTTP server backing `Map.view()`.
#
# Historically `run_local_server` spawned a subprocess (`python -m http.server`)
# which required PID-file bookkeeping and regularly left orphans. As of
# geeViz 2026.3.3 the server runs as a daemon thread inside the Python process,
# rooted at the geeViz package dir via `directory=` (no chdir side effects).
#
# The server exists only to provide a real HTTP origin for the rendered
# viewer — this matters because the Google Maps JS API key baked into
# `index.html` has HTTP referrer restrictions that reject `file://` and
# `about:srcdoc` origins. Serving via `http://localhost:<port>/...` gives
# Maps a referrer it accepts.
#
# `Map.view()` writes the per-session runGeeViz.js and opens index.html
# into `geeView/<ee_run_name>.html` and then navigates the browser / IFrame
# to `http://localhost:<port>/geeView/<ee_run_name>.html`. Relative asset
# paths (`./src/...`) resolve through the same server.

_RUNNING_SERVERS = {}  # port -> (server, thread)
import threading as _threading


def _js_str(value) -> str:
    """A JavaScript string literal for arbitrary text, safe anywhere in the
    generated viewer script.

    Layer names, the map title and query settings come from users and from
    agents, and they were interpolated into JS string literals unescaped.
    One apostrophe -- ``Peak Nor'easter Wind`` -- ended the string early,
    the whole runGeeViz.js failed to PARSE, ``runGeeViz`` was never
    defined, and not a single layer loaded, ordinary names included. The
    server-side validator never runs this script, so it reported PASS.

    ``json.dumps`` emits a valid JS string literal for any input: it
    escapes both quote styles, backslashes, control characters and --
    because ``ensure_ascii`` is on -- U+2028/U+2029, which JSON allows raw
    but older JS engines treat as line terminators. ``</`` becomes
    ``<\\/`` (the same string to JS) so the text stays inert even when the
    script is inlined into an HTML ``<script>`` element, where the HTML
    parser closes the element at the first ``</script`` regardless of any
    JS quoting.
    """
    return json.dumps("" if value is None else str(value)).replace("</", "<\\/")
# Reentrant lock so `run_local_server` can call `_kill_server` (which also
# acquires this lock) while holding it — a non-reentrant `Lock()` would
# deadlock and hang `Map.view()` any time a stale state file is found.
_SERVERS_LOCK = _threading.RLock()

# Upstream URL of the live eeAuth proxy. ``Map.view`` sets this when it
# finds an active ``eeCreds`` proxy; the request handler reads it to
# reverse-proxy ``/ee-api/*`` requests so the viewer JS can use the
# same-origin default of ``window.location.origin + "/ee-api"`` without
# the browser ever talking to the proxy's port directly.
_EE_API_UPSTREAM: "str | None" = None
_EE_API_UPSTREAM_LOCK = _threading.Lock()

# Lazily-built connection pool for the reverse-proxy leg
# (viewer-server → uvicorn proxy). Created on first ``_proxy_ee_api``
# call. Without pooling, every value:compute/getMapId fired by the
# viewer opens a fresh TCP connection to the uvicorn proxy, which adds
# kernel-level overhead on every layer query — small per request but
# very visible when the viewer fires N parallel queries per click.
_EE_API_POOL = None
_EE_API_POOL_LOCK = _threading.Lock()


def _get_ee_api_pool():
    """Return a process-wide ``urllib3.PoolManager`` for the
    viewer→uvicorn forwarding leg. Built on first use because
    ``urllib3`` is a transitive dep and we don't want to import it at
    geeView load time for users who never call ``Map.view``."""
    global _EE_API_POOL
    if _EE_API_POOL is None:
        with _EE_API_POOL_LOCK:
            if _EE_API_POOL is None:
                import urllib3
                _EE_API_POOL = urllib3.PoolManager(
                    num_pools=8,
                    maxsize=32,
                    block=False,
                    timeout=urllib3.Timeout(connect=10, read=300),
                )
    return _EE_API_POOL


def _set_ee_api_upstream(url: "str | None") -> None:
    """Register the upstream eeAuth proxy URL with the local HTTP server.

    Idempotent. Pass ``None`` to disable reverse-proxying (the /ee-api
    handler will then 503).
    """
    global _EE_API_UPSTREAM
    with _EE_API_UPSTREAM_LOCK:
        _EE_API_UPSTREAM = (url or "").rstrip("/") or None


def _resolve_ee_tenant(request_path: str, referer: str) -> str:
    """Pick the tenant to stamp on a forwarded /ee-api request.

    Precedence: ``?tenant=…`` on the incoming request → ``?tenant=…`` on
    the Referer URL (so EE calls triggered by a page that pinned itself
    to a tenant route through correctly) → ``eeCreds.current()`` as the
    process-wide default.
    """
    from urllib.parse import urlparse, parse_qs
    for src in (request_path, referer):
        if not src:
            continue
        q = parse_qs(urlparse(src).query)
        tenants = q.get("tenant") or []
        if tenants and tenants[0]:
            return tenants[0]
    try:
        from geeViz.eeAuth.eeCreds import eeCreds as _eeCreds
        return _eeCreds.current() or ""
    except Exception:
        return ""


# Headers that must NOT be copied between client / upstream connections.
# Some are hop-by-hop per RFC 7230 §6.1; ``host`` and ``content-length``
# are rebuilt by the outbound urllib request itself.
_PROXY_HOP_BY_HOP_HEADERS = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
    "host", "content-length",
})


class _GeeVizRequestHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler rooted at the geeViz package dir, with a
    /ee-api/* reverse-proxy hook.

    File serving uses ``directory=py_viz_dir`` so it works regardless of
    the process cwd. Access logs are silenced to avoid notebook stderr spam.

    Any request whose path starts with ``/ee-api/`` is forwarded to the
    upstream eeAuth proxy registered via ``_set_ee_api_upstream``. The
    handler stamps an ``X-geeViz-Creds`` tenant header based on
    ``_resolve_ee_tenant``, strips hop-by-hop headers, and streams the
    response back. Lets the viewer JS use the same-origin
    ``/ee-api`` default without the URL having to carry the actual
    proxy address.
    """

    def __init__(self, *args, **kwargs):
        kwargs["directory"] = py_viz_dir
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        """Silence per-request access logs.

        stdlib's default handler writes one line per request to stderr,
        which pollutes the notebook / terminal when the map fetches
        dozens of tiles. Overriding to a no-op keeps ``Map.view()``
        output focused on user prints.
        """
        return

    def end_headers(self):  # noqa: D401 - stdlib API
        """Force no-cache on every static response.

        Without this, browsers cache the geeView JS bundle indefinitely
        (the stdlib server emits no ``Cache-Control``, only ``Last-Modified``,
        which browsers freely cache). When we ship a JS update — e.g.
        the same-origin ``/ee-api`` default replacing the heroku URL —
        users keep hitting the old bundle until they hard-refresh, and
        the symptoms (cross-origin requests to a long-dead proxy) are
        impossible to diagnose without DevTools. Forcing no-store
        eliminates the failure mode entirely; cost is one network
        round-trip per asset per page load, which is irrelevant for a
        local dev server.
        """
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    # ---- /ee-api reverse-proxy ----
    def _is_ee_api(self) -> bool:
        # ``self.path`` may include the query string; check just the path.
        from urllib.parse import urlparse
        return urlparse(self.path).path.startswith("/ee-api/") or \
            urlparse(self.path).path == "/ee-api"

    def _proxy_ee_api(self) -> None:
        upstream = _EE_API_UPSTREAM
        if not upstream:
            self.send_error(503, "eeAuth proxy not registered")
            return
        # Both ``self.path`` and ``upstream`` carry the ``/ee-api`` prefix.
        # Strip it from the incoming path so we don't double it.
        suffix = self.path
        if suffix.startswith("/ee-api"):
            suffix = suffix[len("/ee-api"):]

        # Map.view() bakes the tenant into the JS-side proxy URL as a
        # ``/t/<tenant>/`` path prefix (rather than a ``?tenant=`` query
        # on the page URL). Strip it here and surface the tenant for
        # routing. This keeps the page URL bar clean AND pins every tab
        # to its tenant for the lifetime of the page — process-wide
        # eeCreds.use() switches can't drift open tabs to other creds.
        path_tenant = ""
        if suffix.startswith("/t/"):
            rest = suffix[len("/t/"):]
            slash = rest.find("/")
            if slash > 0:
                path_tenant = rest[:slash]
                suffix = rest[slash:]
            else:
                # ``/ee-api/t/<tenant>`` with no trailing segment — keep
                # the suffix as-is and treat as the tenant ack endpoint.
                path_tenant = rest
                suffix = "/"

        target_url = upstream + suffix  # upstream already ends without trailing slash

        # Read body (if any). EE often POSTs JSON; for streaming uploads we'd
        # need chunked forwarding, but EE doesn't use that path.
        try:
            content_length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            content_length = 0
        body = self.rfile.read(content_length) if content_length > 0 else None

        # Forward most headers; strip hop-by-hop and overwrite tenant.
        out_headers = {}
        for h, v in self.headers.items():
            if h.lower() in _PROXY_HOP_BY_HOP_HEADERS:
                continue
            out_headers[h] = v
        # Tenant precedence: ``/t/<tenant>/`` path segment (per-tab pin)
        # → ``?tenant=`` on request or Referer (legacy) → eeCreds.current()
        # process-wide default (only safe in single-tenant setups).
        tenant = path_tenant or _resolve_ee_tenant(
            self.path, self.headers.get("Referer", ""),
        )
        if tenant:
            out_headers["X-geeViz-Creds"] = tenant

        # Use the shared pool so connections to the uvicorn proxy
        # stay alive across requests. urllib3 ``preload_content=False``
        # streams the body chunk-by-chunk on the way back, matching the
        # original ``urlopen``+read-loop behavior without buffering the
        # whole response (important for getMapId tile responses).
        try:
            pool = _get_ee_api_pool()
            resp = pool.request(
                self.command, target_url,
                body=body, headers=out_headers,
                preload_content=False,
                retries=False,
                redirect=False,
            )
        except Exception as e:
            self.send_error(502, f"eeAuth proxy unreachable: {e}")
            return
        try:
            self._relay_response(resp.status, resp.headers, resp)
        finally:
            resp.release_conn()

    def _relay_response(self, status: int, headers, body_stream) -> None:
        self.send_response(status)
        for h, v in headers.items():
            if h.lower() in _PROXY_HOP_BY_HOP_HEADERS:
                continue
            self.send_header(h, v)
        self.end_headers()
        # Stream in chunks to avoid loading huge tile/compute responses into
        # memory in one go.
        while True:
            chunk = body_stream.read(64 * 1024)
            if not chunk:
                break
            try:
                self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                # Browser hung up — common when panning the map fast.
                return

    # Override each HTTP verb so reverse-proxy fires for /ee-api/*; everything
    # else falls through to ``SimpleHTTPRequestHandler``'s static-file behavior.
    # All six ``do_*`` methods share the same shape: if the request path is
    # ``/ee-api/*`` proxy it upstream, otherwise (GET) serve static or (others)
    # 405. Documenting once instead of six identical docstrings.
    def do_GET(self):  # noqa: N802 - stdlib API
        """Static file for non-``/ee-api/*`` paths, proxy otherwise."""
        if self._is_ee_api():
            return self._proxy_ee_api()
        return super().do_GET()

    def do_POST(self):  # noqa: N802 - stdlib API
        """Proxy ``/ee-api/*`` POSTs; anything else → 405."""
        if self._is_ee_api():
            return self._proxy_ee_api()
        self.send_error(405, "Method Not Allowed")

    def do_PUT(self):  # noqa: N802 - stdlib API
        """Proxy ``/ee-api/*`` PUTs; anything else → 405."""
        if self._is_ee_api():
            return self._proxy_ee_api()
        self.send_error(405, "Method Not Allowed")

    def do_DELETE(self):  # noqa: N802 - stdlib API
        """Proxy ``/ee-api/*`` DELETEs; anything else → 405."""
        if self._is_ee_api():
            return self._proxy_ee_api()
        self.send_error(405, "Method Not Allowed")

    def do_PATCH(self):  # noqa: N802 - stdlib API
        """Proxy ``/ee-api/*`` PATCHes; anything else → 405."""
        if self._is_ee_api():
            return self._proxy_ee_api()
        self.send_error(405, "Method Not Allowed")

    def do_OPTIONS(self):  # noqa: N802 - stdlib API
        """Proxy ``/ee-api/*`` OPTIONS preflight; anything else → 405."""
        if self._is_ee_api():
            return self._proxy_ee_api()
        # No CORS preflight needed for static files served same-origin.
        self.send_error(405, "Method Not Allowed")


def run_local_server(port: int = 8001):
    """
    Start the in-process threaded geeViz web server, rooted at the geeViz
    package directory.

    The function is idempotent: if a server is already running on `port`, it
    returns the existing port number without restarting. If `port` is held by
    an unrelated process (or a stale subprocess from an older geeViz version
    that we can't kill), we transparently auto-pick a free port and return
    the actual port that ended up bound.

    Args:
        port (int): Preferred port number. If unavailable, a free port is
            auto-selected.

    Returns:
        int: The port number the server is actually bound to. Callers should
            use this (not the originally-requested port) when building URLs.
    """
    with _SERVERS_LOCK:
        if port in _RUNNING_SERVERS:
            return port
        # If the preferred port is already active, it may be a leftover
        # subprocess from an older geeViz version — try to kill it via the
        # PID file so we can take over cleanly. Stale state files (PID
        # already dead) are also handled here: `_kill_server` just removes
        # the file. After this, re-check the port status.
        if isPortActive(port):
            state = _read_server_state(port)
            if state and "pid" in state and state["pid"] != os.getpid():
                _kill_server(port)
                time.sleep(0.5)
            else:
                # No state file we can act on — just clean up any stale
                # file so it doesn't confuse future runs.
                _kill_server(port)

        # On Windows, binding to an already-listening port can spuriously
        # succeed (SO_REUSEADDR semantics differ from POSIX), leaving us
        # with a "server" that can't actually accept connections. So we
        # always check `isPortActive` first and fall straight to port 0
        # (OS-assigned) if the preferred port is still held — `bind()` is
        # not a reliable collision detector on Windows.
        if isPortActive(port):
            print("Port {} still held after cleanup — auto-picking a free port".format(port))
            port = 0

        try:
            server = socketserver.ThreadingTCPServer(("127.0.0.1", port), _GeeVizRequestHandler)
        except OSError as e:
            # Preferred port somehow failed even though isPortActive said it
            # was free. Fall back once to OS-assigned.
            if port != 0:
                print("Bind on port {} failed ({}) — auto-picking a free port".format(port, e))
                try:
                    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _GeeVizRequestHandler)
                except OSError as e2:
                    print("Failed to bind any local port for geeViz server: {}".format(e2))
                    return None
            else:
                print("Failed to bind any local port for geeViz server: {}".format(e))
                return None
        port = server.server_address[1]
        server.daemon_threads = True
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        _RUNNING_SERVERS[port] = (server, thread)
        _write_server_state(port, os.getpid(), py_viz_dir)
        return port


######################################################################
# Function to see if port is active
def isPortActive(port: int = 8001):
    """
    See if a given port number is currently active

    Args:
        port (int): Port number to check status of

    Returns:
        bool: Whether or not the port is already active
    """
    # The original code creates a socket and may leave it open (orphaned) if not explicitly closed, 
    # since it does not use a context manager or explicit close. The revised code uses 
    # a `with` statement to ensure that the socket is properly closed after use, 
    # preventing orphan sockets and resource leaks.

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)  # 2 Second Timeout
        result = sock.connect_ex(("localhost", port))
        if result == 0:
            return True
        else:
            return False


######################################################################
# Server state management helpers
def _server_state_path(port):
    """Return path to the server state file for a given port."""
    return os.path.join(tempfile.gettempdir(), ".geeViz_server_{}.json".format(port))


def _read_server_state(port):
    """Read server state {pid, root_dir} from the temp file. Returns None if missing."""
    path = _server_state_path(port)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _write_server_state(port, pid, root_dir):
    """Write server state to a temp file keyed by port."""
    path = _server_state_path(port)
    with open(path, "w") as f:
        json.dump({"pid": pid, "root_dir": root_dir, "port": port}, f)


def _kill_server(port):
    """Shut down an http server tracked for `port`, whether it's in-process
    (preferred path) or a legacy subprocess left behind by an older geeViz
    version."""
    with _SERVERS_LOCK:
        entry = _RUNNING_SERVERS.pop(port, None)
    if entry is not None:
        server, _thread = entry
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
    else:
        # Legacy subprocess case — fall back to the old PID-based kill path.
        state = _read_server_state(port)
        if state and "pid" in state and state["pid"] != os.getpid():
            try:
                os.kill(state["pid"], signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
    path = _server_state_path(port)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _detect_proxy_url():
    """Auto-detect the proxy URL for the current environment.

    Tries, in order:

    1. ``GEEVIZ_PROXY_URL`` environment variable — set this for Cloud Run
       or any custom deployment (e.g. ``GEEVIZ_PROXY_URL=https://my-service.run.app``).
    2. GCE metadata server — works on Vertex AI Workbench, where the
       instance name + region are available at a well-known endpoint and
       the proxy URL follows a predictable pattern.
    3. Fall back to ``input()`` prompt — same behavior as original geeViz
       for environments where auto-detection fails.

    Returns:
        str: the proxy base URL (e.g. ``https://instance-dot-region.notebooks.googleusercontent.com``).
    """
    # 1. Explicit env var — highest priority, works everywhere
    env_url = os.getenv("GEEVIZ_PROXY_URL")
    if env_url:
        print("Using proxy URL from GEEVIZ_PROXY_URL env var:", env_url)
        return env_url

    # 2. GCE metadata — auto-detect on Vertex AI Workbench
    try:
        meta_headers = {"Metadata-Flavor": "Google"}
        instance = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/name",
            headers=meta_headers, timeout=2
        ).text
        zone = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/zone",
            headers=meta_headers, timeout=2
        ).text.split("/")[-1]
        region = "-".join(zone.split("-")[:-1])
        proxy_url = "https://{}-dot-{}.notebooks.googleusercontent.com".format(instance, region)
        print("Auto-detected Workbench proxy URL:", proxy_url)
        return proxy_url
    except Exception:
        pass

    # 3. Fall back to prompt
    return input(
        "Please enter the URL your notebook/service is running from "
        "(e.g. https://code-dot-region.notebooks.googleusercontent.com/): "
    )


def _ensure_server(port):
    """Ensure an in-process HTTP server is serving from py_viz_dir. Returns
    the port the server is actually bound to — may differ from the requested
    port if it was unavailable and we auto-picked a free one. Safe to call
    from every `Map.view()`.
    """
    with _SERVERS_LOCK:
        if port in _RUNNING_SERVERS:
            return port
    actual = run_local_server(port)
    if actual is None:
        return None
    # Only surface a message when the port had to be reassigned — the
    # normal case is silent so the only URL a user sees is the actual
    # geeView URL printed later by view(). Two URLs in the output was
    # confusing users who thought they should click the server root.
    if actual != port:
        print("geeViz server bound to http://localhost:{}/{}/ (requested {})".format(actual, geeViewFolder, port))
    return actual


######################################################################
######################################################################
######################################################################
# Set up mapper object
class mapper:
    """Primary geeViz map setup and manipulation object.

    The `mapper` builds up a list of GEE layers and map commands (`addLayer`,
    `addTimeLapse`, `turnOnInspector`, `setCenter`, etc.) and then launches
    the interactive geeView web viewer via `view()`.

    **Rendering flow (as of geeViz 2026.3.3)**

    `Map.view()` writes the per-session `runGeeViz.js` to its canonical
    disk location (`geeView/src/gee/gee-run/`) and opens
    `geeView/index.html` directly:

    - **Plain Python / scripts** — opened via a `file://` URL with the
      access token passed as a query string. No HTTP server needed.
    - **Notebooks (VS Code, Jupyter)** — displayed inline via an
      `IFrame(src="http://localhost:<port>/geeView/...")` backed by an
      in-process threaded `http.server` (daemon thread, no subprocess).
      VS Code's webview blocks `file://` in iframes, so a real HTTP
      origin is required for inline display. The server auto-picks a
      free port if the preferred one (default 8001) is held.
    - **Colab / Vertex AI Workbench** — uses platform-specific proxy
      URLs via `google.colab.kernel.proxyPort()` or `self.proxy_url`.

    The `buildgeeViz.py` build script patches `lcms-viewer.min.js` so
    the viewer's runtime `loadGEELibraries()` call uses
    `document.createElement('script')` instead of `$.getScript()` (which
    is jQuery XHR — blocked by Chrome under `file://`). It also strips
    the dead `require(...)` fallback from `changeDetectionLib.js`.

    **Key methods**

    - `view(open_browser=None, open_iframe=None, iframe_height=525)` —
      launch the viewer
    - `addLayer` / `addTimeLapse` / `addSelectLayer` / `turnOnInspector` /
      `turnOnAutoAreaCharting` / `setCenter` / `centerObject` / `clearMap`
    - `refresh()` — re-run the last `view()` with a fresh token

    Args:
        port (int, default 8001): Port `view()` should use, and a
            request to pin the eeAuth proxy there. Setting it
            explicitly — either `mapper(port=…)` with a non-default
            value or `Map.port = …` — marks the port as
            human-chosen, which makes `view()` pin the eeAuth proxy to
            it and respawn any healthy proxy listening elsewhere. Leave
            it alone and the proxy stays on its own default (8889),
            which is usually what you want. Note that in the default
            detached mode the in-process `http.server` is never
            started at all — the detached proxy serves both
            `/geeView/*` and `/ee-api/*` — so the port only backs a
            local server in the attached/legacy paths, where an
            unavailable port is replaced by a free one.

    Attributes:
        port (int, default 8001): Port `view()` should use, and a
            request to pin the eeAuth proxy there. Assigning to it
            marks the port as human-chosen, so `view()` pins the eeAuth
            proxy to it and respawns any healthy proxy listening
            elsewhere; left alone, the proxy stays on its own default
            (8889). In the default detached mode no in-process
            `http.server` is started — the detached proxy serves both
            `/geeView/*` and `/ee-api/*` — so the port only backs a
            local server in the attached/legacy paths, where an
            unavailable port is replaced by a free one.

        proxy_url (str, default None): Vertex AI Workbench proxy URL used
            when `view()` runs inside a Workbench notebook. Auto-prompted
            on first call if unset; set manually in advance (e.g.
            `Map.proxy_url = "https://code-dot-region.notebooks.googleusercontent.com/"`)
            to skip the prompt. Ignored outside Workbench.

        refreshTokenPath (str, default ee.oauth.get_credentials_path()):
            Path to the Earth Engine refresh token credentials file used to
            mint fresh access tokens on each `view()` call.

        serviceKeyPath (str, default None): Path to a service account key
            JSON. If provided, it will be used for authentication inside
            geeView instead of the refresh token — useful for headless
            deployments (Cloud Run, scheduled jobs) where no user refresh
            token is available.

        project (str, default ee.data._get_state().cloud_api_user_project):
            Google Cloud project id used for Earth Engine. `geeViz` tries to
            resolve this automatically from `ee.Initialize(project=...)`; set
            it manually if `Map.view()` logs `project=None`.

        turnOffLayersWhenTimeLapseIsOn (bool, default True): Whether all
            other layers should be turned off when a time lapse is turned
            on. Default is True to avoid confusing layer-order rendering
            when time lapses and non-time lapses are visible at the same
            time. Set to False if you want them visible simultaneously.
            
        showToolTipModal (bool, default False): Whether to show the tooltip modal when the map is loaded.
    """

    def __call__(self):
        """Allow ``gv.Map()`` to return the singleton instead of raising TypeError."""
        return self

    @property
    def port(self) -> int:
        """Port `view()` will use.

        Reads back whatever is currently in effect, which is not
        necessarily what was set: in attached/legacy mode `view()`
        overwrites it with the port the picker actually bound when the
        requested one was busy.
        """
        return self._port

    @port.setter
    def port(self, value: int) -> None:
        """Set the port and record that a human asked for it.

        The side effect is the point: assigning here flips
        `_port_explicit` to True, which is what makes `view()` pin the
        eeAuth proxy to this port and respawn a healthy proxy that is
        listening somewhere else. Without that flag `view()` passes
        `proxy_port=None` and reuses any healthy proxy wherever it
        already is. So `Map.port = 8001` is NOT a no-op even though
        8001 is the default value — it converts the default into a
        demand.
        """
        # No warning here — Map.port IS honored in attached mode.
        # If the user is on detached and the port ends up ignored,
        # Map.view() prints a runtime hint after it knows the
        # resolved mode.
        self._port = int(value)
        # Record that a HUMAN chose this port. view() only pins the
        # eeAuth proxy to it when that's true — otherwise the default
        # 8001 would be treated as a demand and kill a healthy proxy
        # listening on the eeAuth default (8889) just to move it.
        self._port_explicit = True

    _DEFAULT_PORT = 8001

    def __init__(self, port: int = _DEFAULT_PORT):
        """Construct the mapper.

        Args:
            port (int, default 8001): Port for `view()`. Unlike the
                `Map.port` setter, passing a port here only counts as
                an explicit human choice when it DIFFERS from the
                default — `mapper(port=8001)` leaves the port
                unpinned (any healthy eeAuth proxy is reused wherever
                it sits), while `Map.port = 8001` pins it and forces a
                respawn. The asymmetry is intentional: `Map = mapper()`
                is constructed at import time with the default, and
                treating that as a demand would kill a healthy proxy on
                every import.
        """
        # Stored on ``_port`` so the public ``port`` setter (see property
        # above) can run its side effects without recursing into itself,
        # and so internal writes — the ``_ensure_server`` fallback port
        # pick, which the port picker chose rather than the user — can
        # bypass those side effects and NOT flip ``_port_explicit``.
        self._port = int(port)
        # True once the caller sets Map.port (property setter) or passes
        # a non-default to __init__. See the setter for why it matters.
        #
        # Read through ``self``, NOT the module-level ``Map`` singleton:
        # ``Map = mapper()`` is constructed at import time, so this
        # __init__ runs BEFORE that name is bound and referencing it
        # here raises NameError — which breaks `import geeViz.geeView`
        # outright.
        self._port_explicit = int(port) != int(self._DEFAULT_PORT)
        self.layerNumber = 1
        self.idDictList = []
        self.mapCommandList = []
        self.ee_run_name = "runGeeViz"

        self.typeLookup = {
            "Image": "geeImage",
            "ImageCollection": "geeImageCollection",
            "Feature": "geeVectorImage",
            "FeatureCollection": "geeVectorImage",
            "Geometry": "geeVectorImage",
            "dict": "geoJSONVector",
        }
        try:
            self.isNotebook = ee.oauth._in_jupyter_shell()
        except:
            self.isNotebook = ee.oauth.in_jupyter_shell()
        try:
            self.isColab = ee.oauth._in_colab_shell()
        except:
            self.isColab = ee.oauth.in_colab_shell()

        self.proxy_url = None

        self.refreshTokenPath = ee.oauth.get_credentials_path()
        self.serviceKeyPath = None
        self.queryWindowMode = "sidePane"
        self.project = ee.data._get_state().cloud_api_user_project
        self.turnOffLayersWhenTimeLapseIsOn = True
        self.showToolTipModal = False

        # eeAuth mode override for Map.view() — takes precedence over
        # the ``GEEVIZ_EEAUTH_MODE`` env var. When None (default), the
        # env var wins; when the env var is also unset, geeView picks
        # ``auto`` on Colab and ``detached`` elsewhere. Set via
        # ``Map.setAuthMode("attached"|"detached"|"legacy"|"attached_strict")`` when
        # you want to be explicit without touching env.
        self.eeAuthMode = None

    ######################################################################
    # Per-layer workload-tag capture.
    #
    # Every add* call snapshots ``ee.data.getWorkloadTag()`` at the moment
    # of the call and stashes it in the layer's idDict. ``.view()``
    # replays those tags in the emitted JS bootstrap — one
    # ``ee.data.setWorkloadTag(<tag>)`` before each layer's addSerialized*
    # call (and a reset at the top / between untagged layers) — so
    # per-layer attribution survives to Cloud Monitoring even though the
    # JS viewer's own ``setDefaultWorkloadTag("<mode>---viewer-exports")``
    # would otherwise blanket every tile fetch. No JS changes required;
    # the JS SDK's ``setWorkloadTag`` is a synchronous module-global read
    # by each request as it builds, so the setter-then-add sequence
    # captures the intended tag before the async fetch fires.
    def _capture_workload_tag(self) -> str:
        try:
            import ee.data as _ee_data
            return (_ee_data.getWorkloadTag() or "").strip()
        except Exception:
            return ""

    ######################################################################
    # Function for adding a layer to the map
    def addLayer(self, image: ee.Image | ee.ImageCollection | ee.Geometry | ee.Feature | ee.FeatureCollection, viz: dict = {}, name: str | None = None, visible: bool = True):
        """
        Adds GEE object to the mapper object that will then be added to the map user interface with a `view` call.

        Args:
            image (ImageCollection, Image, Feature, FeatureCollection, Geometry): ee object to add to the map UI.
            viz (dict): Primary set of parameters for map visualization, querying, charting, etc. In addition to the parameters supported by the addLayer function in the GEE Code Editor, there are several additional parameters available to help facilitate legend generation, querying, and area summaries. The accepted keys are:

                {
                    "min" (int, list, or comma-separated numbers): One numeric value or one per band to map onto 00.,

                    "max" (int, list, or comma-separated numbers): One numeric value or one per band to map onto FF,

                    "gain" (int, list, or comma-separated numbers): One numeric value or one per band to map onto 00-FF.,

                    "bias" (int, list, or comma-separated numbers): One numeric value or one per band to map onto 00-FF.,

                    "gamma" (int, list, or comma-separated numbers): Gamma correction factor. One numeric value or one per band.,

                    "palette" (str, list, or comma-separated strings): List of CSS-style color strings (single-band previews only).,

                    "opacity" (float): a number between 0 and 1 for initially set opacity.,

                    "layerType" (str, one of geeImage, geeImageCollection, geeVector, geeVectorImage, geoJSONVector): Optional parameter. For vector data ("featureCollection", "feature", or "geometry"), you can spcify "geeVector" if you would like to force the vector to be an actual vector object on the client. This can be slow if the ee object is large and/or complex. Otherwise, any "featureCollection", "feature", or "geometry" will default to "geeVectorImage" where the vector is rasterized on-the-fly for map rendering. Any querying of the vector will query the underlying vector data though. To add a geojson vector as json, just add the json as the image parameter.,

                    "reducer" (Reducer, default 'ee.Reducer.lastNonNull()'): If an ImageCollection is provided, how to reduce it to create the layer that is shown on the map. Defaults to ee.Reducer.lastNonNull(),

                    "autoViz" (bool): Whether to take image bandName_class_values, bandName_class_names, bandName_class_palette properties to visualize, create a legend (populates `classLegendDict`), and apply class names to any query functions (populates `queryDict`),

                    "includeClassValues" (bool, default True): Whether to include the numeric value of each class in the legend when `"autoViz":True`.

                    "canQuery" (bool, default True): Whether a layer can be queried when visible.,

                    "addToLegend" (bool, default True): Whether geeViz should try to create a legend for this layer. Sometimes setting it to `False` is useful for continuous multi-band inputs.,

                    "classLegendDict" (dict): A dictionary with a key:value of the name:color(hex) to include in legend. This is auto-populated when `autoViz` : True,

                    "queryDict" (dict): A dictionary with a key:value of the queried number:label to include if queried numeric values have corresponding label names. This is auto-populated when `autoViz` : True,

                    "queryParams" (dict, optional): Dictionary of additional parameters for querying visible map layers:

                        {
                            "palette" (list, or comma-separated strings): List of hex codes for colors for charts. This is especially useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired set of colors for each band to have on the chart.,

                            "yLabel" (str, optional): Y axis label for query charts. This is useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired label for the Y axis.
                        }

                    "legendLabelLeftBefore" (str) : Label for continuous legend on the left before the numeric component,

                    "legendLabelLeftAfter" (str) : Label for continuous legend on the left after the numeric component,

                    "legendLabelRightBefore" (str) : Label for continuous legend on the right before the numeric component,

                    "legendLabelRightAfter" (str) : Label for continuous legend on the right after the numeric component,

                    "canAreaChart" (bool): whether to include this layer for area charting. If the layer is complex, area charting can be quite slow,

                    "areaChartParams" (dict, optional): Parameters for the interactive area charting
                        in the geeView map viewer. Passed to the viewer's JS ``areaChart.addLayer()``.
                        All keys are optional.

                        **Reducer & spatial resolution:**

                        * ``"reducer"`` (ee.Reducer): Reducer for zonal stats. Default
                          ``ee.Reducer.frequencyHistogram()`` for thematic data (when
                          ``bandName_class_values/names/palette`` properties exist),
                          ``ee.Reducer.mean()`` otherwise.
                        * ``"crs"`` (str, default ``"EPSG:5070"``): CRS for zonal stats.
                        * ``"transform"`` (list, default ``[30, 0, -2361915, 0, -30, 3177735]``):
                          Snap transform for zonal stats.
                        * ``"scale"`` (int, default None): Spatial resolution. Only specify
                          if ``transform`` is None.
                        * ``"minZoomSpecifiedScale"`` (int, default 11): Zoom level below
                          which spatial resolution doubles per zoom step.

                        **Chart type & display:**

                        * ``"line"`` (bool, default True): Create a line chart.
                        * ``"sankey"`` (bool, default False): Create Sankey transition charts.
                          Only for thematic ``ee.ImageCollection`` with ``system:time_start``.
                        * ``"chartType"`` (str, default ``"line"`` for ImageCollection,
                          ``"bar"`` for Image): Options: ``"line"``, ``"bar"``,
                          ``"stacked-line"``, ``"stacked-bar"``.
                        * ``"steppedLine"`` (bool, default False): Step interpolation.
                        * ``"showGrid"`` (bool, default True): Show grid lines.
                        * ``"rangeSlider"`` (bool, default False): Show x-axis range slider.
                        * ``"autoScale"`` (bool): Auto-scale chart axes.

                        **Sankey-specific:**

                        * ``"sankeyTransitionPeriods"`` (list of lists): Years for sankey
                          transitions (e.g. ``[[1985,1987],[2000,2002],[2020,2022]]``).
                        * ``"sankeyMinPercentage"`` (float, default 0.5): Min class % to
                          include in sankey.

                        **Masking / threshold support:**

                        * ``"shouldUnmask"`` (bool, default False): Include masked pixels
                          in area chart by unmasking before reducing. Use with
                          ``.selfMask()`` threshold layers so percentages are relative
                          to total area.
                        * ``"unmaskValue"`` (int/float, default 0): Value to unmask to.

                        **Labels & formatting:**

                        * ``"bandNames"`` (list or str): Bands to chart. Defaults to
                          all bands or ``viz["bands"]``.
                        * ``"dateFormat"`` (str, default ``"YYYY"``): Date format for
                          x-axis labels.
                        * ``"xAxisLabel"`` (str): Custom x-axis label.
                        * ``"yAxisLabel"`` (str): Custom y-axis label. Defaults to
                          ``"% Area"`` for thematic, ``"Mean"`` for continuous.
                        * ``"xAxisProperty"`` (str): Property for x-axis values
                          instead of date.
                        * ``"xTickDateFormat"`` (str): Date format for x-axis ticks.
                        * ``"hovermode"`` (str, default ``"closest"``): Options:
                          ``"closest"``, ``"x"``, ``"y"``, ``"x unified"``,
                          ``"y unified"``.
                        * ``"palette"`` (list or comma-separated str): Hex colors for
                          chart series.
                        * ``"chartLabelMaxWidth"`` (int, default 40): Max chars per
                          line in class labels.
                        * ``"chartLabelMaxLength"`` (int, default 100): Max total
                          chars in class labels.
                        * ``"barChartMaxClasses"`` (int, default 20): Max classes in
                          bar charts.
                        * ``"chartPrecision"`` (int, default 3): Decimal places.
                        * ``"chartDecimalProportion"`` (float, default 0.25):
                          Proportion of total decimal places to show.

                        **Sizing:**

                        * ``"chartWidth"`` (int): Chart width in pixels.
                        * ``"chartHeight"`` (int): Chart height in pixels.
                        * ``"chartTitleFontSize"`` (int): Title font size.
                        * ``"chartLabelFontSize"`` (int): Label font size.
                        * ``"chartAxisTitleFontSize"`` (int): Axis title font size.

                        **Class overrides (auto-detected from image properties):**

                        * ``"class_names"`` (dict): Override class names by band.
                        * ``"class_values"`` (dict): Override class values by band.
                        * ``"class_palette"`` (dict): Override class colors by band.
                        * ``"class_visibility"`` (dict): Override class visibility.

                }
            name (str): Descriptive name for map layer that will be shown on the map UI
            visible (bool, default True): Whether layer should be visible when map UI loads

        >>> import geeViz.geeView as gv
        >>> Map = gv.Map
        >>> ee = gv.ee
        >>> nlcd = ee.ImageCollection("USGS/NLCD_RELEASES/2021_REL/NLCD").select(['landcover'])
        >>> Map.addLayer(nlcd, {"autoViz": True}, "NLCD Land Cover / Land Use 2021")
        >>> Map.turnOnInspector()
        >>> Map.view()


        """
        if name == None:
            name = f"Layer {self.layerNumber}"
            self.layerNumber += 1
        print("Adding layer: " + name)

        # Make sure not to update viz dictionary elsewhere
        viz = dict(viz)

        # Handle reducer if ee object is given
        if "reducer" in viz.keys():

            try:
                viz["reducer"] = viz["reducer"].serialize()
            except Exception as e:
                try:
                    viz["reducer"] = eval(viz["reducer"]).serialize()
                except Exception as e:  # Most likely it's already serialized
                    e = e
        if "areaChartParams" in viz.keys():

            if "reducer" in viz["areaChartParams"].keys():
                try:
                    viz["areaChartParams"]["reducer"] = viz["areaChartParams"]["reducer"].serialize()
                except Exception as e:
                    try:
                        viz["areaChartParams"]["reducer"] = eval(viz["areaChartParams"]["reducer"]).serialize()
                    except Exception as e:  # Most likely it's already serialized
                        e = e

        # Coerce sankeyTransitionPeriods from flat list to nested pairs
        if "areaChartParams" in viz:
            stp = viz["areaChartParams"].get("sankeyTransitionPeriods")
            if stp and len(stp) > 0:
                first = stp[0]
                if isinstance(first, (list, tuple)):
                    pass  # already nested pairs
                elif isinstance(first, (int, float)):
                    viz["areaChartParams"]["sankeyTransitionPeriods"] = [[y, y] for y in stp]
                else:
                    raise TypeError(
                        f"sankeyTransitionPeriods entries must be lists (e.g. [[1985,1985],[2024,2024]]) "
                        f"or ints (e.g. [1985, 2024]), got {type(first).__name__}"
                    )

        # Get the id and populate dictionarye
        idDict = {}

        # Always wrap Geometry/Feature as FeatureCollection for rendering
        imageType = type(image).__name__
        if imageType == "Geometry":
            image = ee.FeatureCollection([ee.Feature(image)])
            imageType = "FeatureCollection"
        elif imageType == "Feature":
            image = ee.FeatureCollection([image])
            imageType = "FeatureCollection"
        elif imageType not in self.typeLookup:
            # Common cause: ee.Element returned from .copyProperties() /
            # .get(...) / .first(). Try to coerce to ee.Image — that's the
            # right interpretation for most analysis pipelines that end with
            # a property-attached image. If that fails, raise a clear error.
            try:
                image = ee.Image(image)
                imageType = "Image"
            except Exception as e:
                raise TypeError(
                    f"addLayer received an object of type {type(image).__name__!r}, "
                    f"which is not a recognized Earth Engine layer type. If this came "
                    f"from .copyProperties() / .get(...) / .first(), wrap the result in "
                    f"ee.Image(...) explicitly, e.g. "
                    f"ee.Image(img.copyProperties(other_img)). "
                    f"Underlying cast error: {e}"
                ) from e

        if "layerType" not in viz.keys():
            viz["layerType"] = self.typeLookup[imageType]

        # A wind-particle layer ALWAYS leaves here carrying the u/v tile
        # stretch, whoever built it.
        #
        # The browser decodes wind components out of the red and green
        # channels of these tiles, which it can only do if it knows the
        # exact range they were encoded with. wind-particles.js keeps a
        # fallback copy of that range, but a fallback is the wrong place
        # for it to come from: if the two ever disagree the decode does
        # not fail, it returns winds wrong by a scale and an offset —
        # which still look like weather, so nothing reports it.
        #
        # Setting it here rather than only in weather.addWindLayer means
        # a hand-rolled ``Map.addLayer(tiles, {"windParticles": True})``
        # is covered too.
        if viz.get("windParticles"):
            from geeViz.weather import WIND_TILE_MIN_MS, WIND_TILE_MAX_MS

            viz.setdefault("windTileMin", WIND_TILE_MIN_MS)
            viz.setdefault("windTileMax", WIND_TILE_MAX_MS)

        if not isinstance(image, dict):
            idDict["_ee_obj"] = image  # keep original for testLayers()
            idDict["_viz"] = dict(viz)  # keep original viz for testLayers()
            image = image.serialize()
            idDict["item"] = image
            idDict["function"] = "addSerializedLayer"
        # Handle passing in geojson vector layers
        else:
            idDict["item"] = json.dumps(image)
            viz["layerType"] = "geoJSONVector"
            idDict["function"] = "addLayer"
        idDict["objectName"] = "Map"
        idDict["name"] = name
        idDict["visible"] = str(visible).lower()
        idDict["viz"] = json.dumps(viz, sort_keys=False)

        idDict["workloadTag"] = self._capture_workload_tag()
        self.idDictList.append(idDict)

    ######################################################################
    # Function for adding an external XYZ tile service to the map
    def addTileLayer(
        self,
        url_template: str,
        name: str = "Tile Layer",
        visible: bool = True,
        opacity: float = 1.0,
        max_zoom: int = 20,
        legend: dict | None = None,
    ):
        """Add an external XYZ tile service (or any URL-templated raster
        service) to the map without leaving geeViz for Leaflet/Mapbox.

        The viewer (lcms-viewer.min.js) already supports tile-URL layers
        via its ``addREST`` / ``tileMapService`` paths; this Python entry
        point wraps that for the standard ``Map.*`` API.

        Args:
            url_template (str): XYZ tile URL with ``{x}``, ``{y}``, ``{z}``
                placeholders. e.g.
                ``"https://example.com/tiles/{z}/{x}/{y}.png"``.
                ArcGIS MapServer/ImageServer tile endpoints fit this
                template too (substitute appropriately).
            name (str, optional): Layer name shown in the layer list.
            visible (bool, optional): Whether the layer is on initially.
            opacity (float, optional): Initial opacity 0-1. Defaults to 1.0.
            max_zoom (int, optional): Maximum zoom level the source serves.
                Defaults to 20.

        Examples:
            CTrees AGB tiles, displayed alongside an EE layer::

                Map.addLayer(my_ee_image, viz, "EE Layer")
                Map.addTileLayer(
                    "https://viz-assets.ctrees.org/sfi/basemaps/agb_100m/{z}/{x}/{y}.png",
                    name="CTrees AGB (100m)",
                    opacity=0.7,
                )
                Map.centerObject(area, 9)
                Map.view()

            ESRI World Imagery basemap::

                Map.addTileLayer(
                    "https://server.arcgisonline.com/ArcGIS/rest/services/"
                    "World_Imagery/MapServer/tile/{z}/{y}/{x}",
                    name="ESRI World Imagery",
                )
        """
        if not isinstance(url_template, str) or not url_template:
            raise ValueError("url_template must be a non-empty string")
        if not all(tok in url_template for tok in ("{x}", "{y}", "{z}")):
            raise ValueError(
                f"url_template must contain {{x}}, {{y}}, and {{z}} placeholders. "
                f"Got: {url_template!r}"
            )

        idDict = {
            "objectName": "Map",
            "function": "addREST",
            "name": name,
            "visible": str(visible).lower(),
            # Marker consumed by _build_run_js to emit a JS function literal.
            "_is_tile_url": True,
            "_tile_url_template": url_template,
            "_tile_max_zoom": int(max_zoom),
            "_tile_opacity": float(opacity),
            # Keep parallel item/viz so list-comprehension paths don't trip.
            "item": "",
            "viz": json.dumps({"layerType": "tileMapService",
                               "opacity": float(opacity),
                               "maxZoom": int(max_zoom)}),
        }
        # LOCAL PATCH tile legend v2 (2026-09-02): a {label: '#rrggbb'} legend
        # becomes the viewer's classLegendDict (hex without '#'), so the
        # legend panel shows swatches instead of a min/max grey ramp.
        # See patches/apply_tile_legend_patch.py.
        if legend:
            if not isinstance(legend, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in legend.items()
            ):
                raise ValueError("legend must be a {label: '#rrggbb'} dict")
            viz = json.loads(idDict["viz"])
            viz["classLegendDict"] = {k: v.lstrip("#") for k, v in legend.items()}
            idDict["viz"] = json.dumps(viz)
        idDict["workloadTag"] = self._capture_workload_tag()
        self.idDictList.append(idDict)

    ######################################################################
    # Dynamic (non-cached) ArcGIS MapServer overlay.
    # Bridges to the viewer's ``addDynamicToMap(baseUrl1, baseUrl2,
    # ending1, ending2, minZoom1, minZoom2, name, visible, helpBox,
    # whichLayerList)`` function — same code path the JS uses for a
    # ``layerType: "dynamicMapService"`` layer. Google Maps requests a
    # single GroundOverlay per viewport by exporting a bbox-sized PNG
    # from ArcGIS's ``/export?f=image`` endpoint, then re-requests on
    # pan/zoom. Preserves the server's cartographic styling — flood
    # zones, legend, labels — instead of downloading raw vector
    # geometries.
    def addDynamicMapService(
        self,
        service_url: str,
        name: str = "Dynamic MapService",
        visible: bool = True,
        layers: str = "",
        transparent: bool = True,
        dpi: int = 96,
        min_zoom: int = 0,
        token: str | None = None,
    ):
        """Add a dynamic (non-cached) ArcGIS MapServer as a re-rendered
        overlay. Use this for services whose metadata reports
        ``singleFusedMapCache: false`` — e.g. FEMA NFHL, USFS Forest
        Roads, most authoritative government REST services. For CACHED
        MapServers use ``addTileLayer`` or ``esriLib.addEsriMapService``
        instead.

        Args:
            service_url (str): ArcGIS MapServer URL ending in
                ``/MapServer`` (no ``/tile/...`` suffix).
            name (str, optional): Layer name shown in the layer list.
            visible (bool, optional): Initial visibility.
            layers (str, optional): ArcGIS ``layers`` param value —
                ``"show:2,3"``, ``"hide:1"``, or ``""`` for defaults.
            transparent (bool, optional): PNG transparency for overlay
                use. Defaults to True.
            dpi (int, optional): Screen DPI for the export request.
                96 is standard; bump to 192 for HiDPI displays.
            min_zoom (int, optional): Below this zoom the overlay isn't
                requested (blank tile). Defaults to 0 (always request).
            token (str, optional): ArcGIS auth token appended to every
                export request.
        """
        if not isinstance(service_url, str) or "MapServer" not in service_url:
            raise ValueError(
                f"service_url must be an ArcGIS MapServer URL. Got: {service_url!r}"
            )
        # Strip trailing slash + any /export suffix the caller may have
        # already appended — we build the query string ourselves so the
        # base is always the bare service URL.
        _base = service_url.rstrip("/")
        if _base.lower().endswith("/export"):
            _base = _base[: -len("/export")]
        # /export params fixed BEFORE bbox (baseURL) and AFTER bbox
        # (ending). getGroundOverlay inserts
        #    ``<west>,<south>,<east>,<north>&bboxSR=3857&imageSR=3857&size=<w>,<h>``
        # between the two, so ``baseURL`` must end with ``bbox=`` and
        # ``ending`` must start with ``&``.
        _q = ["f=image", "format=png32"]
        if transparent:
            _q.append("transparent=true")
        if layers:
            _q.append(f"layers={layers}")
        _q.append("bbox=")   # trailing "bbox=" so JS appends coords
        _base_url = f"{_base}/export?" + "&".join(_q)
        _ending_bits = [f"dpi={int(dpi)}"]
        if token:
            _ending_bits.append(f"token={token}")
        _ending = "&" + "&".join(_ending_bits)
        # ``addDynamicToMap`` picks item[1] when zoom > item[1].minZoom
        # and item[0] otherwise. We use identical URLs for both — same
        # export endpoint, no HiDPI split — with min_zoom as the floor
        # so a user zoomed out beyond ``min_zoom`` gets a blank tile
        # (matches getGroundOverlay's built-in gate).
        idDict = {
            "objectName": "",     # bare function call, not a method
            "function": "addDynamicToMap",
            "name": name,
            "visible": str(visible).lower(),
            "_is_dynamic_esri": True,
            "_dyn_base_url_1": _base_url,
            "_dyn_base_url_2": _base_url,
            "_dyn_ending_1":   _ending,
            "_dyn_ending_2":   _ending,
            "_dyn_min_zoom_1": int(min_zoom),
            "_dyn_min_zoom_2": int(min_zoom),
            # Parallel item/viz so list-comprehension callers don't trip.
            "item": "",
            "viz": json.dumps({"layerType": "dynamicMapService"}),
        }
        idDict["workloadTag"] = self._capture_workload_tag()
        self.idDictList.append(idDict)

    ######################################################################
    # Pass-through wrappers so ``Map.addEsri*`` mirrors ``esriLib.addEsri*``.
    # Ergonomic win: the agent already uses ``Map.addLayer`` /
    # ``Map.addTileLayer`` — having the ArcGIS helpers on the same object
    # means one less import + better tab-completion + a single, uniform
    # "how do I put a layer on the map" surface. The heavy lifting stays
    # in ``esriLib`` (URL parsing, portal search, metadata preflight,
    # feature count guardrails); this just delegates.
    def addEsriImageService(self, url_or_result, viz_params=None, name=None, token=None):
        """See ``geeViz.esriLib.addEsriImageService``. Delegates."""
        from geeViz import esriLib as _el
        # LOCAL PATCH (2026-08-28): pass self, or the layer lands on gv.Map.
        return _el.addEsriImageService(url_or_result, viz_params=viz_params, name=name, token=token, target_map=self)

    def addEsriMapService(self, url_or_result, name=None, token=None, viz_params=None):
        """See ``geeViz.esriLib.addEsriMapService``. Delegates. If the
        service is dynamic (non-cached), esriLib now falls back to
        ``Map.addDynamicMapService`` internally instead of raising."""
        from geeViz import esriLib as _el
        # LOCAL PATCH (2026-08-28): pass self, or the layer lands on gv.Map.
        return _el.addEsriMapService(url_or_result, name=name, token=token, viz_params=viz_params, target_map=self)

    def addEsriFeatureService(self, url_or_result, viz_params=None, name=None,
                              max_features=1000, where="1=1", token=None,
                              bbox=None):
        """See ``geeViz.esriLib.addEsriFeatureService``. Delegates."""
        from geeViz import esriLib as _el
        # LOCAL PATCH (2026-08-28): pass self, or the layer lands on gv.Map.
        return _el.addEsriFeatureService(url_or_result, viz_params=viz_params, name=name,
                                          max_features=max_features, where=where, token=token,
                                          target_map=self, bbox=bbox)

    def addEsriService(self, url_or_result, viz_params=None, name=None, token=None,
                       max_features=1000, where="1=1"):
        """See ``geeViz.esriLib.addEsriService``. Auto-detects the
        service type from URL / metadata and delegates to the right
        add-helper."""
        from geeViz import esriLib as _el
        # LOCAL PATCH (2026-08-28): pass self, or the layer lands on gv.Map.
        return _el.addEsriService(url_or_result, viz_params=viz_params, name=name, token=token,
                                   max_features=max_features, where=where, target_map=self)

    ######################################################################
    # Function for adding a layer to the map
    def addTimeLapse(self, image: ee.ImageCollection, viz: dict = {}, name: str | None = None, visible: bool = True):
        """
        Adds GEE ImageCollection object to the mapper object that will then be added as an interactive time lapse in the map user interface with a `view` call.

        Args:
            image (ImageCollection): ee ImageCollecion object to add to the map UI.
            viz (dict): Primary set of parameters for map visualization, querying, charting, etc. These are largely the same as the `addLayer` function. Keys unique to `addTimeLapse` are provided here first. In addition to the parameters supported by the `addLayer` function in the GEE Code Editor, there are several additional parameters available to help facilitate legend generation, querying, and area summaries. The accepted keys are:

                {
                    "mosaic" (bool, default False): If an ImageCollection with multiple images per time step is provided, how to reduce it to create the layer that is shown on the map. Uses ee.Reducer.lastNonNull() if True or ee.Reducer.first() if False,

                    "dateFormat" (str, default "YYYY"): The format of the date to show in the slider. E.g. if your data is annual, generally "YYYY" is best. If it's monthly, generally "YYYYMM" is best. Daily, generally "YYYYMMdd"...etc.,

                    "advanceInterval" (str, default 'year'): How much to advance each frame when creating each individual mosaic. One of 'year', 'month' 'week', 'day', 'hour', 'minute', or 'second'.


                    "min" (int, list, or comma-separated numbers): One numeric value or one per band to map onto 00.,

                    "max" (int, list, or comma-separated numbers): One numeric value or one per band to map onto FF,

                    "gain" (int, list, or comma-separated numbers): One numeric value or one per band to map onto 00-FF.,

                    "bias" (int, list, or comma-separated numbers): One numeric value or one per band to map onto 00-FF.,

                    "gamma" (int, list, or comma-separated numbers): Gamma correction factor. One numeric value or one per band.,

                    "palette" (str, list, or comma-separated strings): List of CSS-style color strings (single-band previews only).,

                    "opacity" (float): a number between 0 and 1 for initially set opacity.,

                    "autoViz" (bool): Whether to take image bandName_class_values, bandName_class_names, bandName_class_palette properties to visualize, create a legend (populates `classLegendDict`), and apply class names to any query functions (populates `queryDict`),

                    "includeClassValues" (bool, default True): Whether to include the numeric value of each class in the legend when `"autoViz":True`.

                    "canQuery" (bool, default True): Whether a layer can be queried when visible.,

                    "addToLegend" (bool, default True): Whether geeViz should try to create a legend for this layer. Sometimes setting it to `False` is useful for continuous multi-band inputs.,

                    "classLegendDict" (dict): A dictionary with a key:value of the name:color(hex) to include in legend. This is auto-populated when `autoViz` : True,

                    "queryDict" (dict): A dictionary with a key:value of the queried number:label to include if queried numeric values have corresponding label names. This is auto-populated when `autoViz` : True,

                    "queryParams" (dict, optional): Dictionary of additional parameters for querying visible map layers:

                        {
                            "palette" (list, or comma-separated strings): List of hex codes for colors for charts. This is especially useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired set of colors for each band to have on the chart.,

                            "yLabel" (str, optional): Y axis label for query charts. This is useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired label for the Y axis.
                        }

                    "legendLabelLeftBefore" (str) : Label for continuous legend on the left before the numeric component,

                    "legendLabelLeftAfter" (str) : Label for continuous legend on the left after the numeric component,

                    "legendLabelRightBefore" (str) : Label for continuous legend on the right before the numeric component,

                    "legendLabelRightAfter" (str) : Label for continuous legend on the right after the numeric component,

                    "canAreaChart" (bool): whether to include this layer for area charting. If the layer is complex, area charting can be quite slow,

                    "areaChartParams" (dict, optional): Parameters for the interactive area charting
                        in the geeView map viewer. Passed to the viewer's JS ``areaChart.addLayer()``.
                        All keys are optional.

                        **Reducer & spatial resolution:**

                        * ``"reducer"`` (ee.Reducer): Reducer for zonal stats. Default
                          ``ee.Reducer.frequencyHistogram()`` for thematic data (when
                          ``bandName_class_values/names/palette`` properties exist),
                          ``ee.Reducer.mean()`` otherwise.
                        * ``"crs"`` (str, default ``"EPSG:5070"``): CRS for zonal stats.
                        * ``"transform"`` (list, default ``[30, 0, -2361915, 0, -30, 3177735]``):
                          Snap transform for zonal stats.
                        * ``"scale"`` (int, default None): Spatial resolution. Only specify
                          if ``transform`` is None.
                        * ``"minZoomSpecifiedScale"`` (int, default 11): Zoom level below
                          which spatial resolution doubles per zoom step.

                        **Chart type & display:**

                        * ``"line"`` (bool, default True): Create a line chart.
                        * ``"sankey"`` (bool, default False): Create Sankey transition charts.
                          Only for thematic ``ee.ImageCollection`` with ``system:time_start``.
                        * ``"chartType"`` (str, default ``"line"`` for ImageCollection,
                          ``"bar"`` for Image): Options: ``"line"``, ``"bar"``,
                          ``"stacked-line"``, ``"stacked-bar"``.
                        * ``"steppedLine"`` (bool, default False): Step interpolation.
                        * ``"showGrid"`` (bool, default True): Show grid lines.
                        * ``"rangeSlider"`` (bool, default False): Show x-axis range slider.
                        * ``"autoScale"`` (bool): Auto-scale chart axes.

                        **Sankey-specific:**

                        * ``"sankeyTransitionPeriods"`` (list of lists): Years for sankey
                          transitions (e.g. ``[[1985,1987],[2000,2002],[2020,2022]]``).
                        * ``"sankeyMinPercentage"`` (float, default 0.5): Min class % to
                          include in sankey.

                        **Masking / threshold support:**

                        * ``"shouldUnmask"`` (bool, default False): Include masked pixels
                          in area chart by unmasking before reducing. Use with
                          ``.selfMask()`` threshold layers so percentages are relative
                          to total area.
                        * ``"unmaskValue"`` (int/float, default 0): Value to unmask to.

                        **Labels & formatting:**

                        * ``"bandNames"`` (list or str): Bands to chart. Defaults to
                          all bands or ``viz["bands"]``.
                        * ``"dateFormat"`` (str, default ``"YYYY"``): Date format for
                          x-axis labels.
                        * ``"xAxisLabel"`` (str): Custom x-axis label.
                        * ``"yAxisLabel"`` (str): Custom y-axis label. Defaults to
                          ``"% Area"`` for thematic, ``"Mean"`` for continuous.
                        * ``"xAxisProperty"`` (str): Property for x-axis values
                          instead of date.
                        * ``"xTickDateFormat"`` (str): Date format for x-axis ticks.
                        * ``"hovermode"`` (str, default ``"closest"``): Options:
                          ``"closest"``, ``"x"``, ``"y"``, ``"x unified"``,
                          ``"y unified"``.
                        * ``"palette"`` (list or comma-separated str): Hex colors for
                          chart series.
                        * ``"chartLabelMaxWidth"`` (int, default 40): Max chars per
                          line in class labels.
                        * ``"chartLabelMaxLength"`` (int, default 100): Max total
                          chars in class labels.
                        * ``"barChartMaxClasses"`` (int, default 20): Max classes in
                          bar charts.
                        * ``"chartPrecision"`` (int, default 3): Decimal places.
                        * ``"chartDecimalProportion"`` (float, default 0.25):
                          Proportion of total decimal places to show.

                        **Sizing:**

                        * ``"chartWidth"`` (int): Chart width in pixels.
                        * ``"chartHeight"`` (int): Chart height in pixels.
                        * ``"chartTitleFontSize"`` (int): Title font size.
                        * ``"chartLabelFontSize"`` (int): Label font size.
                        * ``"chartAxisTitleFontSize"`` (int): Axis title font size.

                        **Class overrides (auto-detected from image properties):**

                        * ``"class_names"`` (dict): Override class names by band.
                        * ``"class_values"`` (dict): Override class values by band.
                        * ``"class_palette"`` (dict): Override class colors by band.
                        * ``"class_visibility"`` (dict): Override class visibility.

                }
            name (str): Descriptive name for map layer that will be shown on the map UI
            visible (bool, default True): Whether layer should be visible when map UI loads

        >>> import geeViz.geeView as gv
        >>> Map = gv.Map
        >>> ee = gv.ee
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter(ee.Filter.calendarRange(2010, 2025, "year"))
        >>> Map.addTimeLapse(lcms.select(["Land_Cover"]), {"autoViz": True, "mosaic": True}, "LCMS Land Cover Time Lapse")
        >>> Map.addTimeLapse(lcms.select(["Change"]), {"autoViz": True, "mosaic": True}, "LCMS Change Time Lapse")
        >>> Map.addTimeLapse(lcms.select(["Land_Use"]), {"autoViz": True, "mosaic": True}, "LCMS Land Use Time Lapse")
        >>> Map.turnOnInspector()
        >>> Map.view()


        """
        if name == None:
            name = "Layer " + str(self.layerNumber)
            self.layerNumber += 1
        print("Adding layer: " + name)

        # Make sure not to update viz dictionary elsewhere
        viz = dict(viz)

        # Handle reducer if ee object is given - delete it
        if "reducer" in viz.keys():
            del viz["reducer"]

        # Handle area charting reducer
        if "areaChartParams" in viz.keys():

            if "reducer" in viz["areaChartParams"].keys():
                try:
                    viz["areaChartParams"]["reducer"] = viz["areaChartParams"]["reducer"].serialize()
                except Exception as e:
                    try:
                        viz["areaChartParams"]["reducer"] = eval(viz["areaChartParams"]["reducer"]).serialize()
                    except Exception as e:  # Most likely it's already serialized
                        e = e
        # Coerce sankeyTransitionPeriods from flat list to nested pairs
        if "areaChartParams" in viz:
            stp = viz["areaChartParams"].get("sankeyTransitionPeriods")
            if stp and len(stp) > 0:
                first = stp[0]
                if isinstance(first, (list, tuple)):
                    pass  # already nested pairs
                elif isinstance(first, (int, float)):
                    viz["areaChartParams"]["sankeyTransitionPeriods"] = [[y, y] for y in stp]
                else:
                    raise TypeError(
                        f"sankeyTransitionPeriods entries must be lists (e.g. [[1985,1985],[2024,2024]]) "
                        f"or ints (e.g. [1985, 2024]), got {type(first).__name__}"
                    )

        viz["layerType"] = "ImageCollection"
        # Get the id and populate dictionary
        idDict = {}  # image.getMapId()
        idDict["_ee_obj"] = image  # keep original for testLayers()
        idDict["_viz"] = dict(viz)  # keep original viz for testLayers()
        idDict["objectName"] = "Map"
        idDict["item"] = image.serialize()
        idDict["name"] = name
        idDict["visible"] = str(visible).lower()
        idDict["viz"] = json.dumps(viz, sort_keys=False)
        idDict["function"] = "addSerializedTimeLapse"
        idDict["workloadTag"] = self._capture_workload_tag()
        self.idDictList.append(idDict)

    ######################################################################
    # Function for adding a select layer to the map
    def addSelectLayer(self, featureCollection: ee.FeatureCollection, viz: dict = {}, name: str | None = None):
        """
        Adds GEE featureCollection to the mapper object that will then be added as an interactive selection layer in the map user interface with a `view` call. This layer will be availble for selecting areas to include in area summary charts.

        Args:
            featureCollection (FeatureCollection): ee FeatureCollecion object to add to the map UI as a selectable layer, where each feature is selectable by clicking on it.
            viz (dict, optional): Primary set of parameters for map visualization and specifying which feature attribute to use as the feature name (selectLayerNameProperty), etc. In addition to the parameters supported by the `addLayer` function in the GEE Code Editor, there are several additional parameters available to help facilitate legend generation, querying, and area summaries. The accepted keys are:

                {
                    "strokeColor" (str, default random color): The color of the selection layer on the map,

                    "strokeWeight" (int, default 3): The thickness of the polygon outlines,

                    "selectLayerNameProperty" (str, default first feature attribute with "name" in it or "system:index"): The attribute name to show when a user selects a feature.



                }
            name (str, default None): Descriptive name for map layer that will be shown on the map UI. Will be auto-populated with `Layer N` if not specified

        >>> import geeViz.geeView as gv
        >>> Map = gv.Map
        >>> ee = gv.ee
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms, {"autoViz": True, "canAreaChart": True, "areaChartParams": {"line": True, "sankey": True}}, "LCMS")
        >>> mtbsBoundaries = ee.FeatureCollection("USFS/GTAC/MTBS/burned_area_boundaries/v1")
        >>> mtbsBoundaries = mtbsBoundaries.map(lambda f: f.set("system:time_start", f.get("Ig_Date")))
        >>> Map.addSelectLayer(mtbsBoundaries, {"strokeColor": "00F", "selectLayerNameProperty": "Incid_Name"}, "MTBS Fire Boundaries")
        >>> Map.turnOnSelectionAreaCharting()
        >>> Map.view()
        """
        if name == None:
            name = "Layer " + str(self.layerNumber)
            self.layerNumber += 1

        # Make sure not to update viz dictionary elsewhere
        viz = dict(viz)

        print("Adding layer: " + name)

        # Get the id and populate dictionary
        idDict = {}  # image.getMapId()
        idDict["objectName"] = "Map"
        idDict["item"] = featureCollection.serialize()
        idDict["name"] = name
        idDict["visible"] = str(False).lower()
        idDict["viz"] = json.dumps(viz, sort_keys=False)
        idDict["function"] = "addSerializedSelectLayer"
        idDict["workloadTag"] = self._capture_workload_tag()
        self.idDictList.append(idDict)

    ######################################################################
    # Function for centering on a GEE object that has a geometry
    def setCenter(self, lng: float, lat: float, zoom: int | None = None):
        """
        Center the map on a specified point and optional zoom on loading

        Args:
            lng (int or float): The longitude to center the map on
            lat (int or float): The latitude to center the map on
            zoom (int, optional): If provided, will force the map to zoom to this level after centering it on the provided coordinates. If not provided, the current zoom level will be used.

        >>> from geeViz.geeView import *
        >>> Map.setCenter(-111,41,10)
        >>> Map.view()
        """

        command = f"Map.setCenter({lng},{lat},{json.dumps(zoom)})"

        self.mapCommandList.append(command)

    ######################################################################
    # Function for setting the map zoom
    def setZoom(self, zoom: int):
        """
        Set the map zoom level

        Args:
            zoom (int): The zoom level to set the map to on loading.

        >>> from geeViz.geeView import *
        >>> Map.setZoom(10)
        >>> Map.view()
        """
        self.mapCommandList.append(f"map.setZoom({zoom})")

    ######################################################################
    # Function for centering on a GEE object that has a geometry
    def centerObject(self, feature: ee.Geometry | ee.Feature | ee.FeatureCollection | ee.Image, zoom: int | None = None):
        """
        Center the map on an object on loading

        Args:
            feature (Feature, FeatureCollection, or Geometry): The object to center the map on
            zoom (int, optional): If provided, will force the map to zoom to this level after centering it on the object. If not provided, the highest zoom level that allows the feature to be viewed fully will be used.

        >>> from geeViz.geeView import *
        >>> pt = ee.Geometry.Point([-111, 41])
        >>> Map.addLayer(pt.buffer(10), {}, "Plot")
        >>> Map.centerObject(pt)
        >>> Map.view()

        """
        try:
            bounds_info = feature.geometry().bounds(100, "EPSG:4326").getInfo()
        except Exception:
            bounds_info = feature.bounds(100, "EPSG:4326").getInfo()
        # Empty FeatureCollections / non-existent assets / failed filters
        # frequently surface here as ``None`` — emitting
        # ``synchronousCenterObject(null)`` makes the viewer center on (0,0)
        # which the user reads as "the map is broken". Refuse early with a
        # message the agent's run_code stdout will surface.
        if bounds_info is None:
            raise ValueError(
                "Map.centerObject: bounds resolved to None. The feature is "
                "probably empty (a filter returned 0 rows) or the asset "
                "doesn't exist. Verify with .size().getInfo() before "
                "centering — e.g. "
                "print(fc.size().getInfo()) — and confirm the filter "
                "property/value match the asset's schema."
            )
        command = "synchronousCenterObject(" + json.dumps(bounds_info) + ")"

        self.mapCommandList.append(command)

        if zoom is not None:
            self.setZoom(zoom)

    ######################################################################
    # Build the per-session runGeeViz JavaScript body from the mapper's
    # state. Written by `view()` to `geeView/src/gee/gee-run/<name>.js`,
    # which `index.html` already references via a normal `<script src>`.
    def _build_run_js(self, tenant: str = ""):
        # Optional tenant header — runs IMMEDIATELY at script load, before
        # ``eeInit()`` (which is deferred behind a Google Maps load).
        # ``authProxyAPIURL`` is a top-level ``let`` in lcms-viewer.min.js
        # that's accessible cross-script in classic-script lexical scope;
        # reassigning it here makes the deferred ``ee.initialize`` call use
        # a tenant-prefixed proxy URL. Each per-session run_js bakes its
        # own tenant, so every open browser tab is permanently pinned to
        # the tenant Map.view() ran with — immune to subsequent
        # eeCreds.use() switches that change process-wide state.
        prefix = ""
        if tenant:
            from urllib.parse import quote as _q
            t_enc = _q(tenant, safe="")
            prefix = (
                "try{authProxyAPIURL=window.location.origin+"
                f"'/ee-api/t/{t_enc}';}}catch(e){{}}"
            )
        lines = prefix + "var layerLoadErrorMessages=[];showMessage('Loading',staticTemplates.loadingModal[mode]);function runGeeViz(){"
        # If the Python side has a DEFAULT workload tag installed (via
        # ``ee.data.setDefaultWorkloadTag`` — including the sensible
        # one eeCreds installs at proxy start, ``geeviz__<tenant>``),
        # push it into the browser SDK so client-side compute (area
        # chart, click-to-query, elevation ping, thumbnail preview)
        # attributes the same way as the Python process. Read the
        # actual DEFAULT, not ``getWorkloadTag()`` — which returns the
        # CURRENT tag (typically whatever the user last set) and would
        # install the wrong value as the browser fallback.
        _py_default = ""
        try:
            import ee.data as _ee_data
            _state = _ee_data._get_state().workload_tag
            _py_default = (_state._default or "").strip()
        except Exception:
            _py_default = ""
        # Prefer the CURRENT tag when it's set and differs from the
        # installed default. Rationale: in an agent context, each tool
        # call scopes a per-user attribution tag via
        # ``ee.data.setWorkloadTag(wl_<hash>)`` (see the MCP tool
        # wrapper). The default remains the generic ``geeviz__<tenant>``
        # installed at eeCreds init — which has no ``ee_workload_tags``
        # mapping and gets silently skipped by the puller. Baking the
        # CURRENT tag as the JS default carries per-user attribution
        # into post-load browser compute (area chart, inspector click,
        # dynamic recompute).
        #
        # NOT done behind a proxy. There the current tag IS the
        # per-user ``wl_<hash>``, and emitting it would publish that
        # internal attribution id into page source for anyone viewing a
        # shared map — the exposure this whole branch exists to avoid.
        # It would also be pointless: the proxy rewrites the query
        # string on every POST and substitutes its own server-built tag,
        # so post-load browser compute is attributed server-side to
        # whoever is actually driving it. Falling through to ``""``
        # clears the viewer's ``${mode}---viewer-exports`` fallback,
        # which is what we want.
        #
        # Read in its OWN try: ``_state._tag`` is a private attribute
        # whose shape varies across earthengine-api versions, and
        # sharing one except with the ``_default`` read above meant a
        # failure here discarded an already-valid default and silently
        # untagged every post-load call.
        if not _EE_API_UPSTREAM:
            try:
                _py_cur = (_state._tag or "").strip()
                if _py_cur and _py_cur != _py_default:
                    _py_default = _py_cur
            except Exception:
                pass
        if _py_default:
            lines += "try{ee.data.setDefaultWorkloadTag(" + _js_str(_py_default) + ");}catch(e){}"
        else:
            # No Python-side default to push. Explicitly clear the JS
            # viewer's built-in ``${mode}---viewer-exports`` fallback
            # (installed by lcms-viewer's ``eeInitSuccessCallback``) so
            # post-load browser compute (area chart, inspector click,
            # dynamic recompute) attributes to nothing rather than a
            # cryptic ``geeviz---viewer-exports`` bucket that has no
            # matching ``ee_workload_tags`` row and gets skipped by the
            # puller anyway. Users expect ``""`` when nothing is set.
            lines += 'try{ee.data.setDefaultWorkloadTag("");}catch(e){}'
        # Clean slate for per-layer workload tags. resetWorkloadTag()
        # (no arg) resets CURRENT back to whichever default is now in
        # effect — the Python one we just pushed, or the empty string
        # we just installed above. Either way, no ``viewer-exports``.
        lines += "try{ee.data.resetWorkloadTag();}catch(e){}"
        for idDict in self.idDictList:
            # Per-layer workload tag replay. If addLayer was called under
            # eeCreds.setWorkloadTag(<X>), emit an SDK setter here so the
            # subsequent addSerializedLayer's synchronous getMapId call
            # bakes <X> into that layer's tile URL. Emits reset when the
            # layer was added under no explicit tag so a preceding layer
            # doesn't leak its tag onto this one.
            #
            # Suppressed entirely when an eeAuth proxy is in front of
            # us (``_EE_API_UPSTREAM`` set). The proxy rewrites the
            # query string on every POST — stripping whatever the
            # client sent and substituting its own server-built tag
            # (see eeAuth/server.py:_rewrite_query_with_workload_tag).
            # So under a proxy this value is never used for billing;
            # emitting it only publishes an internal ``wl_...``
            # attribution id into page source that a viewer can read.
            # Standalone geeViz keeps emitting it — with no proxy to
            # substitute one, this IS the only tagging mechanism.
            _wt = "" if _EE_API_UPSTREAM else idDict.get("workloadTag", "")
            if _wt:
                lines += "try{ee.data.setWorkloadTag(" + _js_str(_wt) + ");}catch(e){}"
            else:
                lines += "try{ee.data.resetWorkloadTag();}catch(e){}"
            if idDict.get("_is_dynamic_esri"):
                # Dynamic (non-cached) ArcGIS MapServer overlay. Emit a
                # bare ``addDynamicToMap(...)`` call — that JS function
                # is a module-level function in lcms-viewer, NOT a
                # method on Map, so no ``Map.`` prefix. Escapes match
                # the addREST branch below: any backslash / double
                # quote in the URLs is doubled for JS string safety.
                lines += (
                    'try{{addDynamicToMap({b1},{b2},{e1},{e2},'
                    '{z1},{z2},{name},{visible},"","#layer-list");}}'
                    'catch(e){{layerLoadErrorMessages.push('
                    '"Dynamic MapService \\""+{name}+"\\" failed: "+e.message);}}'
                ).format(
                    b1=_js_str(idDict["_dyn_base_url_1"]),
                    b2=_js_str(idDict["_dyn_base_url_2"]),
                    e1=_js_str(idDict["_dyn_ending_1"]),
                    e2=_js_str(idDict["_dyn_ending_2"]),
                    z1=int(idDict.get("_dyn_min_zoom_1", 0)),
                    z2=int(idDict.get("_dyn_min_zoom_2", 0)),
                    name=_js_str(idDict["name"]),
                    visible=str(idDict["visible"]).lower(),
                )
                continue
            if idDict.get("_is_tile_url"):
                # External XYZ tile service — emit a Map.addREST(...) call
                # with a JS function literal that substitutes {x}/{y}/{z}.
                # _js_str makes the URL a valid JS string literal whatever
                # characters it holds.
                tile_url_fn = (
                    'function(coord,zoom){return ' + _js_str(idDict["_tile_url_template"]) +
                    '.replace("{x}",coord.x)'
                    '.replace("{y}",coord.y)'
                    '.replace("{z}",zoom);}'
                )
                # addREST signature: (tileURLFunction, name, visible, maxZoom, helpBox, whichLayerList)
                # Wrap in a try/catch so a single bad URL can't break the whole map load.
                # LOCAL PATCH tile v1 (2026-09-02): Map.addREST builds a
                # <REST-layer> element the viewer never defines, so
                # layer.setLayer is not a function and no tile is ever
                # requested (measured in Chrome: 0 requests). The
                # tileMapService branch of addToMap is the path
                # addFeatureView uses, and it draws - go through
                # Map.addLayer with that viz. See
                # patches/apply_tile_layer_patch.py.
                lines += (
                    # LOCAL PATCH tile legend v2 (2026-09-02): the stored viz, so a legend reaches the page.
                    'try{{Map.addLayer({fn},{viz},{name},{visible});}}'
                    'catch(e){{layerLoadErrorMessages.push("Tile layer \\""+{name}+"\\" failed: "+e.message);}}'
                ).format(
                    fn=tile_url_fn,
                    name=_js_str(idDict["name"]),
                    visible=str(idDict["visible"]).lower(),
                    viz=idDict["viz"],
                )
                continue

            lines += "{}.{}({},{},{},{});".format(
                idDict["objectName"],
                idDict["function"],
                idDict["item"],
                idDict["viz"],
                _js_str(idDict["name"]),
                str(idDict["visible"]).lower(),
            )
        # Reset back to the current default tag (the Python one we
        # pushed above, or the empty override if nothing was set) so
        # anything fired AFTER the layer sequence (area chart, inspector
        # clicks, dynamic recomputes) attributes to the same default
        # rather than inheriting the last layer's tag. Notably: never
        # falls back to the JS viewer's built-in
        # ``${mode}---viewer-exports`` — that was overridden at eeInit.
        lines += "try{ee.data.resetWorkloadTag();}catch(e){}"
        lines += 'if(layerLoadErrorMessages.length>0){showMessage("Map.addLayer Error List",layerLoadErrorMessages.join("<br>"));};'
        lines += "setTimeout(function(){if(layerLoadErrorMessages.length===0){$('#close-modal-button').click();}}, 2500);"
        for mapCommand in self.mapCommandList:
            lines += mapCommand + ";"
        lines += 'queryWindowMode = "{}";'.format(self.queryWindowMode)
        lines += "Map.turnOffLayersWhenTimeLapseIsOn = {};".format(
            str(self.turnOffLayersWhenTimeLapseIsOn).lower()
        )
        lines+=f"localStorage['showToolTipModal-geeViz']={str(self.showToolTipModal).lower()};"
        lines += "};"
        # item/viz are JSON and already valid JS, but text inside them (a
        # legend label, a class name) can still contain "</script". Outside
        # of string literals the generated code never contains "</", so
        # rewriting it everywhere only ever touches string contents, where
        # "<\\/" is the same string.
        return lines.replace("</", "<\\/")

    ######################################################################
    # Access token minting — split out of view() so any code that needs
    # a fresh token can call this directly.
    def _mint_access_token(self):
        """Populate `self.accessToken` and `self.accessTokenCreationTime`
        from whichever credential source is configured. Split out of
        view() so any code that needs a fresh token can call this
        directly."""
        if self.serviceKeyPath is None:
            self.accessToken = refreshToken()
            self.accessTokenCreationTime = int(datetime.datetime.now().timestamp() * 1000)
        else:
            self.accessToken = serviceAccountToken(self.serviceKeyPath)
            if self.accessToken is None:
                # Service key failed — fall back to the persistent refresh
                # token path so users with a broken SA key still see a map.
                self.accessToken = refreshToken(self.refreshTokenPath)
                self.accessTokenCreationTime = int(datetime.datetime.now().timestamp() * 1000)
            else:
                self.accessTokenCreationTime = None

    ######################################################################
    # Standalone HTML export for embedding in chat UIs / cloud-hosted viewers
    def export_html(
        self,
        output_path: str,
        asset_base: str = "/geeView/static",
        token_placeholder: str = "__GEEVIZ_TOKEN__",
        token_time_placeholder: str = "__GEEVIZ_TOKEN_TIME__",
        project_placeholder: str = "__GEEVIZ_PROJECT__",
        auth_proxy_placeholder: str = "__GEEVIZ_AUTH_PROXY__",
    ) -> str:
        """Write a self-contained geeView HTML to `output_path`.

        Differs from :meth:`view` in three ways:

        - **No HTTP server.** This method only writes a file; it does not
          mint tokens or open a browser. Suitable for chat UIs that
          serve the HTML themselves (e.g. via blob URL).
        - **Asset paths are absolute** under ``asset_base`` (default
          ``/geeView/static``). The hosting server must mount the
          ``geeView/`` package directory at that prefix.
        - **The access token is a placeholder** (default
          ``__GEEVIZ_TOKEN__``). The host UI is responsible for
          string-replacing the placeholder with a fresh access token
          before serving the HTML to the browser. This decouples token
          lifetime from artifact storage.

        Args:
            output_path (str): Where to write the HTML file.
            asset_base (str): URL prefix where the geeView assets are
                mounted. Defaults to ``/geeView/static``.
            token_placeholder (str): String to use in place of the
                access token. The host replaces this at serve time.
            token_time_placeholder (str): String to use in place of the
                access-token creation time (millis epoch).
            project_placeholder (str): String to use in place of the
                EE project ID.

        Returns:
            str: Absolute path to the written HTML file.
        """
        # Auto-enable inspector if no turnOn commands have been set.
        if not any("turnOn" in c for c in self.mapCommandList):
            self.turnOnInspector()

        run_js = self._build_run_js()

        with open(template, "r", encoding="utf-8") as f:
            html = f.read()

        # LOCAL PATCH (2026-09-03): the template hard-codes geeViz's own
        # Google Maps key, which is HTTP-referrer-restricted to geeViz's
        # domains (plus localhost - which is why every local test passes
        # and every OTHER deployment fails with RefererNotAllowedMapError,
        # a blank grey map, and a console pointing at a key the deployer
        # does not own). If the standard env var names a key, stamp it
        # into the page instead; otherwise behave exactly as before.
        _maps_key = os.environ.get("GOOGLE_MAPS_PLATFORM_API_KEY", "").strip()
        if _maps_key:
            import re as _re_key  # self-contained: geeView has no module-level re
            html = _re_key.sub(
                r"(maps\.googleapis\.com/maps/api/js\?key=)AIza[\w-]+",
                r"\g<1>" + _maps_key, html)

        # Inject <base href> so any RELATIVE URLs the geeView JS injects at
        # runtime (icons, palette images, etc.) resolve to the asset base
        # rather than to the current page's path. Absolute URLs are unaffected.
        base_tag = '<base href="' + asset_base.rstrip("/") + '/">\n    '
        html = html.replace("<head>", "<head>\n    " + base_tag, 1)

        # Rewrite ./src/... references to absolute under asset_base.
        # Order matters: the inline runGeeViz must replace the script src first.
        html = html.replace(
            '<script type="text/javascript" src="./src/gee/gee-run/runGeeViz.js"></script>',
            (
                # Auth bootstrap — runs after lcms-viewer.min.js initializes
                # urlParams, before runGeeViz triggers Map.addLayer.
                # Either path works at runtime:
                #   * accessToken set + non-"None" → viewer uses token directly
                #     (legacy ``__GEEVIZ_TOKEN__`` substitution path).
                #   * accessToken == "None" / null → viewer falls through to
                #     ``urlParams.geeAuthProxyURL``, which routes EE API calls
                #     through the agent's ``/ee-api`` proxy. Agent injects the
                #     SA bearer token server-side; no EE token in the browser.
                "<script>(function(){"
                "  if(typeof urlParams==='undefined'){window.urlParams={};}"
                "  urlParams.accessToken='" + token_placeholder + "';"
                "  urlParams.accessTokenCreationTime=" + token_time_placeholder + ";"
                "  urlParams.projectID='" + project_placeholder + "';"
                "  urlParams.geeAuthProxyURL='" + auth_proxy_placeholder + "';"
                "})();</script>\n"
                # Inlined per-export runGeeViz JS
                "<script>" + run_js + "</script>"
            ),
        )
        # Now rewrite the rest of the ./src/ asset paths
        html = html.replace('href="./src/', 'href="' + asset_base + '/src/')
        html = html.replace('src="./src/', 'src="' + asset_base + '/src/')

        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return os.path.abspath(output_path)

    ######################################################################
    # Function for launching the web map after all adding to the map has been completed
    def view(
        self,
        open_browser: bool | None = None,
        open_iframe: bool | None = None,
        iframe_height: int = 525,
    ):
        """
        Compile all map objects and commands and start the map viewer.

        Starts an in-process threaded HTTP server (daemon thread, no
        subprocess) serving from the geeViz package directory, then
        opens the viewer in a browser or inline IFrame depending on the
        environment:

        - **Scripts / plain Python / agents (MCP, ADK)**: opens
          ``http://localhost:<port>/geeView/?accessToken=...`` in the
          default browser via ``webbrowser.open()``.
        - **Notebooks (VS Code, Jupyter)**: displays an inline
          ``IFrame`` only (no browser tab).
        - **Google Colab**: uses ``google.colab.kernel.proxyPort()``
          to get a proxy URL (auto-detected, no user action).
        - **Vertex AI Workbench**: uses ``self.proxy_url`` (set it
          once via ``Map.proxy_url = "https://..."``; prompts on first
          use if unset).
        - **Cloud Run / remote deployments**: set ``Map.proxy_url``
          to your service's public URL, same pattern as Workbench.

        When neither ``open_browser`` nor ``open_iframe`` is specified,
        only one opens: IFrame in notebooks, browser otherwise. If one
        is explicitly set (e.g. ``open_browser=True``), only that one
        opens. If one is explicitly disabled (e.g.
        ``open_browser=False``), the other opens instead. Both can be
        set to ``True`` to get both.

        Args:
            open_browser (bool | None): Open in the default browser.
                Default ``None`` (auto: ``True`` outside notebooks,
                ``False`` in notebooks).
            open_iframe (bool | None): Display an inline IFrame.
                Default ``None`` (auto: ``True`` in notebooks,
                ``False`` otherwise).
            iframe_height (int, default 525): Height of the inline
                IFrame in pixels.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms, {"autoViz": True, "canAreaChart": True, "areaChartParams": {"line": True, "sankey": True}}, "LCMS")
        >>> Map.turnOnInspector()
        >>> Map.view()
        """
        self._last_view_kwargs = {
            "open_browser": open_browser,
            "open_iframe": open_iframe,
            "iframe_height": iframe_height,
        }

        # Auto-enable inspector if no turnOn commands have been set.
        if not any("turnOn" in c for c in self.mapCommandList):
            self.turnOnInspector()

        print("Starting webmap")

        # Auth path selection: proxy (modern) vs direct-token (legacy).
        #
        # 1) PROXY MODE — preferred. Routes every EE REST call from the
        #    viewer through the ``geeViz.eeAuth`` proxy, which signs
        #    requests with the active credential. No token in the URL,
        #    no ~1h expiry, multi-tenant safe.
        #
        #    Trigger: ``eeCreds.proxy_url`` is set OR auto-discovery
        #    finds credentials (ADC, persistent EE refresh token, env
        #    SA, ...) and the proxy spins up successfully.
        #
        # 2) LEGACY MODE — fallback. Mints an EE access token now and
        #    bakes it into the URL. Single-tenant, token expires after
        #    ~1h. Used when the proxy can't start (uvicorn missing,
        #    port unavailable, no credentials discoverable) OR when the
        #    user opts out via ``GEEVIZ_EEAUTH_MODE=legacy``.
        #
        # Mode override:
        #   - ``GEEVIZ_EEAUTH_MODE=attached`` (default): try proxy, fall back
        #   - ``GEEVIZ_EEAUTH_MODE=attached_strict``: require proxy; raise if can't
        #   - ``GEEVIZ_EEAUTH_MODE=legacy``: skip proxy entirely
        ee_proxy_url = ""
        ee_proxy_tenant = ""
        ee_proxy_tenants: list[str] = []
        ee_proxy_mode = ""
        # Default ``detached`` so multi-``Map.view()`` scripts use one
        # long-lived background process for both EE auth and /geeView
        # HTML — the script can exit cleanly and the browser tab keeps
        # working. Override via ``GEEVIZ_EEAUTH_MODE=attached`` (inline
        # daemon-thread proxy, dies with the script) or ``legacy``
        # (skip proxy entirely, mint tokens into the URL).
        #
        # Exception: in Colab default to ``auto``. The detached proxy
        # runs in a separate process; when ``robust_init`` has to
        # prompt for a project id (the common Colab path — Colab's
        # ADC has no default project), the resolved project is only
        # synced into the calling process's tenant registry, not the
        # detached proxy's. Every downstream ``/ee-api`` request would
        # then be signed without ``x-goog-user-project`` and EE would
        # return 403. Auto mode keeps the proxy in-process so the
        # ``sync_oauth_project`` after the prompt actually takes
        # effect. Users on Colab who want detached can opt in
        # explicitly with ``GEEVIZ_EEAUTH_MODE=detached``.
        _default_mode = "attached" if IS_COLAB else "detached"
        # Precedence: Map.setAuthMode(...) > GEEVIZ_EEAUTH_MODE > default.
        # Instance override wins so notebook users can pin the mode
        # without touching env vars. Old names ("auto"/"proxy") still
        # work as aliases — ensure_started normalizes them.
        _auth_mode = (
            self.eeAuthMode
            or os.environ.get("GEEVIZ_EEAUTH_MODE")
            or _default_mode
        ).lower()
        if _auth_mode != "legacy":
            try:
                from geeViz.eeAuth.eeCreds import eeCreds as _eeCreds
                # Feed Map.port down so detached mode can spawn its
                # subprocess on the user's requested port (matches the
                # port-mismatch respawn check in _ensure_detached). Also
                # gives attached mode a consistent preferred port —
                # _find_free_port bumps if it's taken.
                # Pin the proxy to Map.port ONLY when a human chose it.
                #
                # Passing the default unconditionally made 8001 read as a
                # demand, and eeCreds' default is 8889 — so import-time
                # init would spawn a proxy on 8889 and view() would
                # immediately kill it and respawn on 8001. The next
                # process flipped it back, and any browser tab still
                # pointed at the previous port died with
                # ERR_CONNECTION_RESET, which is the exact thing
                # detached mode exists to avoid.
                #
                # ``None`` means "any healthy proxy will do" — reuse
                # whatever is already listening. In detached mode the
                # viewer is served BY the proxy, so a pinned port
                # necessarily moves the proxy; that respawn is intended.
                status = _eeCreds.ensure_started(
                    mode=_auth_mode,
                    proxy_port=(int(self._port)
                                if getattr(self, "_port_explicit", False)
                                else None),
                )
                if status["proxy_url"]:
                    ee_proxy_url = status["proxy_url"]
                    ee_proxy_tenant = status["current"]
                    ee_proxy_tenants = status.get("tenants", []) or []
                    ee_proxy_mode = status.get("mode", "") or ""
            except RuntimeError:
                # mode='proxy' explicitly demanded the proxy and it
                # couldn't start. Propagate so the user notices.
                raise
            except Exception:
                # auto mode: silent fallback. eeCreds import could fail
                # in environments without uvicorn / fastapi.
                pass

        # Build the per-session runGeeViz JS and write to disk. When the
        # proxy is active we bake the tenant into the JS itself (not the
        # page URL), so every tab is pinned to whatever tenant was
        # current at the moment Map.view() was called — immune to later
        # eeCreds.use() calls changing process-wide state.
        run_js = self._build_run_js(tenant=ee_proxy_tenant or "")
        self.ee_run = os.path.join(ee_run_dir, "{}.js".format(self.ee_run_name))
        with open(self.ee_run, "w", encoding="utf-8") as f:
            f.write(run_js)

        # Detached mode does NOT need the in-process daemon HTTP
        # server — the detached eeAuth proxy serves both ``/geeView/*``
        # and ``/ee-api/*`` on the same port. All other branches still
        # need the daemon for HTML hosting and/or /ee-api reverse-proxy.
        if ee_proxy_mode != "detached":
            actual_port = _ensure_server(self.port)
            if actual_port is not None:
                # Bypass the public setter so this doesn't trigger the
                # Map.port deprecation warning — we didn't pick this
                # port, the port picker did.
                self._port = actual_port

        # Build the viewer URL — proxy mode or legacy token mode.
        if ee_proxy_url:
            # Register the upstream proxy URL with the local HTTP server
            # so its handler reverse-proxies /ee-api/* requests to it.
            # With that hook in place, the JS-side default of
            # ``window.location.origin + "/ee-api"`` resolves to the live
            # proxy without the URL having to carry the address. Skip in
            # detached mode — the browser already loads from the proxy,
            # so ``/ee-api`` is same-origin and direct.
            if ee_proxy_mode != "detached":
                _set_ee_api_upstream(ee_proxy_url)

            # Cache-buster ``?v=<int>`` on each ``view()`` call.
            # Tenant is baked into the per-session run_js (see
            # ``_build_run_js(tenant=…)``) so it doesn't need a URL
            # slot — but if we leave the query empty, ``webbrowser.open``
            # calls the SAME URL every re-view, and browsers refuse to
            # reload a page whose URL hasn't changed. Result: the tab
            # keeps showing whatever layers the LAST notebook cell
            # rendered, even after the current cell called
            # ``Map.clearMap()`` and added completely different
            # layers. A monotonic version param that increments on
            # every ``view()`` forces the browser to treat each call
            # as a fresh navigation, so the JS re-runs, ``run_js``
            # rebuilds from the current ``mapCommandList``, and the
            # displayed layers match the code the user just executed.
            import time as _t_view
            _v = int(_t_view.time() * 1000)
            query = f"?v={_v}"
            # Show the actual mode picked so the user knows whether the
            # proxy is in-process (auto), a subprocess (detached), etc.
            # Also flag WHERE the mode came from so users can trace how
            # they ended up in a given lane without spelunking source.
            if self.eeAuthMode:
                _mode_src = "Map.setAuthMode"
            elif os.environ.get("GEEVIZ_EEAUTH_MODE"):
                _mode_src = "GEEVIZ_EEAUTH_MODE env"
            else:
                _mode_src = "default"
            print(
                f"Using eeCreds proxy at {ee_proxy_url}"
                f" (creds={ee_proxy_tenant or '<first registered>'},"
                f" mode={ee_proxy_mode or _auth_mode} via {_mode_src})"
            )
        else:
            # Legacy: direct token mint, baked into the URL.
            # Emit a one-time warning so users see the deprecation;
            # set GEEVIZ_EEAUTH_MODE=legacy to silence (until removal).
            import warnings as _warnings
            _warnings.warn(
                "geeViz Map.view(): falling back to legacy direct-token "
                "auth (no eeCreds proxy running). Tokens are visible in "
                "the URL and expire after ~1 hour. Set up eeCreds.addCreds() "
                "+ eeCreds.start() to use the proxy, or set "
                "GEEVIZ_EEAUTH_MODE=legacy to silence this warning. "
                "Legacy auth will be removed in a future major version.",
                DeprecationWarning,
                stacklevel=2,
            )
            self._mint_access_token()
            query = "?projectID={}&accessToken={}&accessTokenCreationTime={}".format(
                self.project, self.accessToken, self.accessTokenCreationTime
            )

        # Determine display mode — if user explicitly sets one, only that one fires.
        # If user explicitly disables one (e.g. open_browser=False), the other opens.
        in_notebook = self.isNotebook
        if open_browser is not None or open_iframe is not None:
            want_browser = open_browser if open_browser is not None else not open_iframe
            want_iframe = open_iframe if open_iframe is not None else not open_browser
        else:
            # Auto: iframe in notebooks, browser otherwise
            want_iframe = in_notebook
            want_browser = not in_notebook

        # Open viewer — environment-specific URL construction
        if IS_COLAB:
            # In detached mode (the default since 2026.7.1) the in-process
            # daemon server on ``self.port`` was skipped — the eeCreds
            # proxy serves both ``/geeView/*`` and ``/ee-api/*`` on its
            # own port. Asking Colab to expose ``self.port`` (still the
            # constructor default, e.g. 8001) would proxy to a port
            # where nothing is listening and the iframe would render
            # blank. Parse the actual proxy port out of ``ee_proxy_url``
            # and expose that one instead.
            colab_port = self.port
            if ee_proxy_mode == "detached" and ee_proxy_url:
                try:
                    from urllib.parse import urlparse as _urlparse
                    _parsed_port = _urlparse(ee_proxy_url).port
                    if _parsed_port:
                        colab_port = _parsed_port
                except Exception:
                    pass
            proxy_js = "google.colab.kernel.proxyPort({})".format(colab_port)
            proxy_url = eval_js(proxy_js)
            geeView_url = "{}/geeView/{}".format(proxy_url, query)
            print("Colab Proxy URL:", geeView_url)
            self.IFrame = IFrame(src=geeView_url, width="100%", height="{}px".format(iframe_height))
            display(self.IFrame)
        elif IS_WORKBENCH or (self.proxy_url is not None):
            # Workbench or Cloud Run — auto-detect or use cached proxy_url
            if self.proxy_url is None:
                self.proxy_url = _detect_proxy_url()
            self.proxy_url = baseDomain(self.proxy_url)
            geeView_url = "{}/proxy/{}/geeView/{}".format(
                self.proxy_url, self.port, query
            )
            print("Proxy URL:", geeView_url)
            self.IFrame = IFrame(src=geeView_url, width="100%", height="{}px".format(iframe_height))
            display(self.IFrame)
        elif ee_proxy_mode == "detached" and ee_proxy_url:
            # Local detached path. The detached eeAuth proxy mounts
            # ``/geeView/*`` over this same geeViz package — so map
            # HTML, JS, CSS, and ``/ee-api/*`` tile fetches all live
            # behind one long-lived process on one port. The script
            # can return immediately; the browser tab stays usable
            # across script exits and successive script runs.
            base = ee_proxy_url.rstrip("/")
            if base.endswith("/ee-api"):
                base = base[: -len("/ee-api")]
            url = f"{base}/geeView/{query}"
            print("geeView URL:", url)
            if want_iframe:
                self.IFrame = IFrame(src=url, width="100%", height="{}px".format(iframe_height))
                display(self.IFrame)
            if want_browser:
                webbrowser.open(url, new=1)
        else:
            # Local fallback (legacy ``auto`` mode, or detached unavailable).
            # In-process daemon-thread HTTP server (started above). Short
            # sleep so the browser can fetch the initial HTML + static
            # assets before the script returns; daemon dies when the
            # script exits, so a refresh after exit will 404.
            # Use 127.0.0.1 (not `localhost`) to match the detached-mode
            # branch above and to sidestep the IPv6-first-resolver gotcha
            # on some Windows setups where `localhost` resolves to `::1`
            # first, the http.server only binds IPv4, and naive tools
            # (older Python `requests`, curl without Happy Eyeballs)
            # fail with "connection refused" even though 127.0.0.1 works.
            url = "http://127.0.0.1:{}/geeView/{}".format(self.port, query)
            print("geeView URL:", url)
            if want_iframe:
                self.IFrame = IFrame(src=url, width="100%", height="{}px".format(iframe_height))
                display(self.IFrame)
            if want_browser:
                webbrowser.open(url, new=1)
                if not in_notebook:
                    print(f"\ngeeViz viewer running at {url}")
                    try:
                        time.sleep(3)
                    except KeyboardInterrupt:
                        pass

    ######################################################################
    def refresh(self):
        """
        Re-render the viewer with a freshly minted access token.

        The embedded access token expires ~1 hour after `view()` is called;
        call `Map.refresh()` to mint a new one and re-display the iframe (or
        re-open the browser window, depending on the last `view()` mode).
        """
        if not hasattr(self, "_last_view_kwargs"):
            print("No previous view() call to refresh — call Map.view() first.")
            return
        self.view(**self._last_view_kwargs)

    ######################################################################
    def setAuthMode(self, mode: "str | None"):
        """Set the eeAuth mode ``Map.view()`` uses when it starts / attaches
        to the eeCreds proxy. Overrides the ``GEEVIZ_EEAUTH_MODE`` env var.

        Args:
            mode: One of the canonical modes, or ``None`` to fall back
                to the env var / default.

                * ``"attached"`` — in-process daemon-thread proxy; dies
                  with the script but doesn't need a separate process.
                  Default on Colab. Silent-fallback on failure — if the
                  proxy can't start, ``Map.view()`` uses the legacy
                  token-in-URL path.
                * ``"attached_strict"`` — same as ``"attached"`` but
                  raises when the proxy can't start (vs. silent fallback).
                * ``"detached"`` — long-lived background subprocess proxy;
                  survives script exit so multi-``Map.view()`` workflows
                  and successive script runs share one proxy. **Default
                  on non-Colab.**
                * ``"legacy"`` — no proxy; mint tokens directly into the
                  ``Map.view()`` URL. Deprecated — planned for removal.

                Legacy aliases (soft-deprecated, still accepted):
                ``"auto"`` → ``"attached"``, ``"proxy"`` → ``"attached_strict"``.

        Precedence: ``Map.setAuthMode(...)`` > ``GEEVIZ_EEAUTH_MODE`` env
        var > default (``"attached"`` on Colab, ``"detached"`` elsewhere).

        >>> Map.setAuthMode("attached")   # force in-process proxy
        >>> Map.view()
        """
        if mode is not None:
            m = str(mode).strip().lower()
            aliases = {"auto": "attached", "proxy": "attached_strict"}
            canonical = {"attached", "attached_strict", "detached", "legacy"}
            if m in aliases:
                m = aliases[m]  # normalize; ensure_started will also log the deprecation
            if m not in canonical:
                raise ValueError(
                    f"Map.setAuthMode: mode must be one of "
                    f"{sorted(canonical)} (aliases {sorted(aliases)} "
                    f"also accepted); got {mode!r}"
                )
            self.eeAuthMode = m
        else:
            self.eeAuthMode = None

    def addWindLayer(self, image: ee.Image, viz: dict = {}, name: str = "Wind", visible: bool = True,
                     groupWindLayers: bool = True):
        """Add a wind field: a queryable speed raster plus animated particles.

        Two layers, in the style of windy.com — a smooth speed raster
        carrying the reading, with particle trails over it showing the
        flow. The particles are advected from wind components decoded
        out of Earth Engine PNG tiles, so they follow the map anywhere
        you pan rather than being confined to a region fixed up front.

        Args:
            image (ee.Image): Image whose bands include the wind
                components.
            viz (dict): Follows ``addLayer``'s conventions.

                * ``bands`` (list or comma-separated str): the dx/dy
                  components. Defaults to the image's FIRST TWO bands,
                  in order — by position, because every product names
                  them differently.
                * ``units`` (str): ``"km/hr"`` (default), ``"m/s"`` or
                  ``"mi/hr"``.
                * ``min`` / ``max``: speed stretch. ``max`` defaults per
                  UNIT (15 m/s, 54 km/h, 34 mi/h), so switching units
                  cannot leave the raster one flat colour.
                * ``palette`` (list or comma-separated str): speed ramp.
                * ``particleColor`` (str): trail colour, default
                  ``"#fff"``.
                * ``particleCount``, ``particleSpeedFactor``,
                  ``particleMaxAge``, ``particleTrailPersistence``,
                  ``particleLineWidth``, ``particleOpacity``: animation
                  feel. ``particleOpacity`` is the alpha at the trail
                  HEAD — a look, not a dimmer; to fade the whole flow
                  use ``opacity``.
                * ``opacity`` (1): the master. A wind layer draws two
                  things, and this sets where BOTH dimmers start, so
                  ``{"opacity": 0.8}`` gives a speed field and a flow
                  each at 0.8.
                * ``windSpeedOpacity``: the speed raster alone,
                  overriding ``opacity`` there. The counterpart to
                  ``particleOpacity`` — one number per thing drawn.
                  Both are fractions in [0, 1]; ``80`` raises rather
                  than quietly meaning 1.
                * ``directionConvention`` (str): ``"from"`` (default,
                  meteorological — 270 is a westerly) or ``"to"``.
            name (str): Layer name. Ungrouped, the two layers are
                suffixed ``" speed"`` and ``" particles"``.
            visible (bool): Initial visibility.
            groupWindLayers (bool): ``True`` (the default) draws the
                whole thing as ONE layer -- the client paints the
                colored speed field and the trails from the same
                decoded tiles, which halves the tiles and gives the two
                halves independent opacity sliders. Clicks still report
                real speed and direction. ``False`` restores the
                original two layers, where Earth Engine renders the
                speed raster instead of the client.

        Returns:
            tuple: ``(speed_direction_image, encoded_tiles_image)``.

        >>> import geeViz.weather as wx
        >>> ic = wx.getForecastData("2026-09-11", "2026-09-12", "gfs")
        >>> Map.addWindLayer(ee.Image(ic.first()), {"units": "mi/hr"})
        """
        # Imported lazily: geeViz.weather pulls in geeViz.fireLib, and
        # geeView is imported by everything. Nothing pays for it unless
        # this method is actually called.
        from geeViz.weather import addWindLayer as _addWindLayer

        return _addWindLayer(self, image, viz, name=name, visible=visible,
                             groupWindLayers=groupWindLayers)

    def addWindTimeLapse(self, collection: ee.ImageCollection, viz: dict = {},
                         name: str = "Wind", visible: bool = True,
                         dateFormat: str | None = None,
                         advanceInterval: str | None = None,
                         mosaic: bool = False,
                         groupWindLayers: bool = True):
        """Add an animated wind field that is itself a time lapse.

        The same two layers :meth:`addWindLayer` adds -- a queryable
        speed raster and the particle flow over it -- but each is a time
        lapse, so the slider scrubs the field while the particles keep
        flowing through it.

        Args:
            collection (ee.ImageCollection): images carrying the wind
                components **in m/s** with ``system:time_start`` set.
                :func:`geeViz.weather.getForecastData` returns this.
            viz (dict): exactly what :meth:`addWindLayer` accepts.
            name (str): base name; the layers appear as
                ``"<name> speed"`` and ``"<name> particles"``.
            visible (bool): whether the pair starts switched on.
            dateFormat (str): slider label format. Defaults to
                ``"YYYYMMdd HH"`` -- forecast wind is sub-daily, and
                :meth:`addTimeLapse`'s annual default would collapse
                every frame onto one label.
            advanceInterval (str): frame width. Defaults to ``"hour"``.
            mosaic (bool): reduce multiple images per step.
            groupWindLayers (bool): ``True`` (the default) animates the
                whole thing as ONE time lapse -- each frame carries the
                speed field and the particles, drawn by the client from
                one set of tiles, with independent opacity sliders.
                ``False`` restores two separate lapses.

        Returns:
            tuple: ``(speed_collection, tiles_collection)``.

        >>> import geeViz.weather as wx
        >>> ic = wx.getForecastData("2026-09-18", "2026-09-20", "gfs")
        >>> Map.addWindTimeLapse(ic, {"units": "kt"}, "GFS wind")
        >>> Map.view()
        """
        # Lazy for the same reason as addWindLayer above: geeViz.weather
        # pulls in geeViz.fireLib, and geeView is imported by everything.
        from geeViz.weather import addWindTimeLapse as _addWindTimeLapse

        return _addWindTimeLapse(self, collection, viz, name=name,
                                 visible=visible, dateFormat=dateFormat,
                                 advanceInterval=advanceInterval,
                                 mosaic=mosaic,
                                 groupWindLayers=groupWindLayers)

    def clearMap(self):
        """
        Removes all map layers and commands - useful if running geeViz in a notebook and don't want layers/commands from a prior code block to still be included.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms, {"autoViz": True}, "LCMS") # Layer
        >>> Map.turnOnInspector() # Command
        >>> Map.clearMap() # Clear map layer and commands
        >>> Map.view()
        """
        self.layerNumber = 1
        self.idDictList = []
        self.mapCommandList = []

    clear = clearMap  # Alias — LLMs frequently try Map.clear()

    def clearMapLayers(self):
        """
        Removes all map layers - useful if running geeViz in a notebook and don't want layers from a prior code block to still be included, but want commands to remain.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms, {"autoViz": True}, "LCMS") # Layer - this will be removed
        >>> Map.turnOnInspector() # Command - this will remain (even though there will be no layers to query)
        >>> Map.clearMapLayers() # Clear map layer only and leave commands
        >>> Map.view()
        """
        self.layerNumber = 1
        self.idDictList = []

    def clearMapCommands(self):
        """
        Removes all map commands - useful if running geeViz in a notebook and don't want commands from a prior code block to still be included, but want layers to remain.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms, {"autoViz": True}, "LCMS") # Layer
        >>> Map.turnOnInspector() # Command - this will be removed
        >>> Map.clearMapCommands() # Clear map comands only and leave layers
        >>> Map.view()
        """
        self.mapCommandList = []

    ######################################################################
    @staticmethod
    def _style_vector(ee_obj, viz):
        """Apply .style() to vector layers to match the geeView JS viewer rendering.

        The JS viewer (lcms-viewer.min.js) checks for styleParams and applies:
        - color, fillColor, width, pointSize, pointShape via ee.FeatureCollection.style()
        - fallback: ee.Image().paint(fc, null, strokeWeight) with palette=strokeColor

        Returns:
            tuple: (styled_ee_obj, style_mode) — the styled EE object and the mode:
            ``"styled"`` (.style() RGBA, no viz needed), ``"painted"`` (paint, needs palette),
            or ``False`` (not a vector, no styling applied).
        """
        obj_cls = ee_obj.__class__.__name__
        if obj_cls == "Geometry":
            ee_obj = ee.FeatureCollection([ee.Feature(ee_obj)])
            obj_cls = "FeatureCollection"
        elif obj_cls == "Feature":
            ee_obj = ee.FeatureCollection([ee_obj])
            obj_cls = "FeatureCollection"

        lt = viz.get("layerType", "")
        is_vector = obj_cls == "FeatureCollection" or "Vector" in lt or "vector" in lt

        if not is_vector:
            return ee_obj, False

        # Build styleParams matching JS viewer defaults
        has_style_keys = any(k in viz for k in ("color", "strokeColor", "fillColor", "pointSize", "pointRadius", "width"))
        if has_style_keys:
            style = {
                "color": viz.get("color") or viz.get("strokeColor") or "000",
                "fillColor": viz.get("fillColor", "00000011"),
                "width": viz.get("width") or viz.get("strokeWeight", 2),
                "pointSize": viz.get("pointSize") or viz.get("pointRadius", 3),
            }
            # .style() returns a styled RGBA image — colors are baked in
            return ee_obj.style(**style), "styled"
        else:
            # Default: paint with thin black outline (single-band, needs palette)
            sw = viz.get("strokeWeight", 2)
            styled = ee.Image().paint(ee_obj, 0, sw)
            return styled, "painted"

    ######################################################################
    def exportLayerJson(self, filename: str | None = None, output_dir: str | None = None):
        """Bundle all currently-added layers into a JSON file suitable for
        a custom HTML dashboard.

        Mirrors the input-type handling of :meth:`testLayers` and
        :meth:`previewMap`: vectors (Geometry, Feature, FeatureCollection)
        are wrapped/styled via :meth:`_style_vector`, ImageCollections are
        collapsed with ``.mosaic()``, and ``ee.Element`` results from
        ``copyProperties`` are coerced to ``ee.Image`` upstream by
        :meth:`addLayer`. The result of these conversions is then
        serialized — a downstream ``/api/dashboard/urls`` endpoint
        deserializes and calls ``getMapId`` on each entry to mint fresh
        tile URLs on every page load.

        Args:
            filename (str, optional): Output filename (saved under
                ``output_dir``). Must end with ``.json``. Defaults to
                ``"dashboard_layers.json"``.
            output_dir (str, optional): Override the directory to write
                into. Defaults to the per-session ``generated_outputs``
                directory used by the rest of the artifact pipeline.

        Returns:
            dict: ``{"path": <abs_path>, "layer_names": [...],
            "layer_count": N, "skipped": [...], "warnings": [...]}``.

        Notes on skipped layer types:
            - ``dict`` / GeoJSON layers — no EE object to re-mint;
              skipped with a warning.
            - Tile-URL layers (added via :meth:`addTileLayer`) — already
              have a static URL; included with ``"static_url"`` key
              instead of ``"serialized"``.
        """
        import os as _os
        import json as _json

        if filename is None:
            filename = "dashboard_layers.json"
        if not filename.lower().endswith(".json"):
            filename = filename + ".json"

        if output_dir is None:
            output_dir = _os.path.join(
                _os.path.dirname(_os.path.abspath(__file__)), "mcp", "generated_outputs"
            )
        _os.makedirs(output_dir, exist_ok=True)
        full_path = _os.path.join(output_dir, _os.path.basename(filename))

        # Display-relevant viz keys (matches _test_layer)
        _VIZ_KEYS = ("bands", "min", "max", "gain", "bias", "gamma", "palette", "opacity", "format")

        layers = {}
        seen_names = {}      # base_name -> count assigned so far
        skipped = []
        warnings = []

        def _unique_name(name):
            count = seen_names.get(name, 0)
            seen_names[name] = count + 1
            if count == 0:
                return name
            new_name = f"{name}_{count + 1}"
            warnings.append(
                f"Layer name {name!r} collided; renamed to {new_name!r}"
            )
            return new_name

        def _try_resolve_auto_viz(ee_obj, viz, map_viz):
            """If autoViz=True, attempt to read class_values/class_palette
            and convert to a concrete viz so the refresh endpoint doesn't
            need to know about autoViz. Best-effort — falls back silently."""
            if not viz.get("autoViz"):
                return map_viz
            try:
                check = ee_obj
                if ee_obj.__class__.__name__ == "ImageCollection":
                    check = ee.Image(ee_obj.first())
                if not hasattr(check, "bandNames"):
                    return map_viz
                band_names = check.bandNames().getInfo() or []
                if not band_names:
                    return map_viz
                first_band = band_names[0]
                cv_key = f"{first_band}_class_values"
                cp_key = f"{first_band}_class_palette"
                d = check.toDictionary([cv_key, cp_key]).getInfo() or {}
                values = d.get(cv_key)
                palette = d.get(cp_key)
                # Normalize string-encoded values (some assets use "1,2,3")
                if isinstance(values, str):
                    values = [int(p.strip()) if p.strip().lstrip("-").isdigit()
                              else p.strip() for p in values.split(",") if p.strip()]
                if isinstance(palette, str):
                    palette = [p.strip() for p in palette.split(",") if p.strip()]
                if values and palette:
                    numeric_vals = [v for v in values if isinstance(v, (int, float))]
                    if numeric_vals:
                        return {
                            "bands": [first_band],
                            "min": min(numeric_vals),
                            "max": max(numeric_vals),
                            "palette": [str(p).replace("#", "") for p in palette],
                        }
            except Exception as e:
                warnings.append(f"autoViz resolve failed for {ee_obj.__class__.__name__}: {e}")
            return map_viz

        for idx, idDict in enumerate(self.idDictList):
            name = idDict.get("name", f"Layer {idx}")

            # Tile-URL layers (Map.addTileLayer): already have a static URL.
            if idDict.get("_is_tile_url"):
                out_name = _unique_name(name)
                layers[out_name] = {
                    "static_url": idDict["_tile_url_template"],
                    "visible": idDict.get("visible", "true") == "true",
                    "opacity": float(idDict.get("_tile_opacity", 1.0)),
                    "max_zoom": int(idDict.get("_tile_max_zoom", 20)),
                }
                continue

            ee_obj = idDict.get("_ee_obj")
            viz = idDict.get("_viz", {}) or {}
            visible = idDict.get("visible", "true") == "true"

            # GeoJSON dict layers: no EE object, can't mint a tile URL
            if ee_obj is None:
                skipped.append({"name": name, "reason": "GeoJSON layer (no EE object to re-mint)"})
                continue

            # Build the display viz (same keys as _test_layer)
            map_viz = {k: viz[k] for k in _VIZ_KEYS if k in viz}

            try:
                styled_obj, style_mode = mapper._style_vector(ee_obj, viz)
                if style_mode == "painted":
                    # paint() returns single-band — use strokeColor as palette
                    sc = viz.get("color") or viz.get("strokeColor")
                    if sc:
                        map_viz["palette"] = [sc.replace("#", "")]
                    map_viz.pop("bands", None)
                elif style_mode == "styled":
                    # .style() bakes colors into RGBA — no viz needed
                    map_viz = {}
                else:
                    # Image / ImageCollection path. Mosaic ImageCollections
                    # so getMapId returns one set of consistent tiles
                    # instead of an arbitrary first-image tile.
                    if styled_obj.__class__.__name__ == "ImageCollection":
                        styled_obj = styled_obj.mosaic()
                    # autoViz pre-resolution (best-effort) — gives the
                    # refresh endpoint a concrete viz with min/max/palette.
                    map_viz = _try_resolve_auto_viz(ee_obj, viz, map_viz)
            except Exception as e:
                skipped.append({"name": name, "reason": f"styling failed: {e}"})
                continue

            try:
                serialized = styled_obj.serialize()
            except Exception as e:
                skipped.append({"name": name, "reason": f"serialize failed: {e}"})
                continue

            # Validate the layer can actually be rendered by calling
            # getMapId(viz). This catches EE-side errors that only surface
            # at tile-mint time (e.g. "Description length exceeds maximum"
            # from CONUS-wide filterBounds, computation errors, asset access
            # failures). Without this check, the dashboard JSON looks fine
            # but the refresh endpoint silently drops the layer at view
            # time and the agent never knows.
            # Coerce ee.Element-returning chains to ee.Image (same trick
            # as the addLayer autocast) so getMapId is callable for
            # expressions like image.copyProperties(other_image) whose
            # top-level operation returns Element by EE's typing.
            mapid_target = styled_obj
            if not hasattr(mapid_target, "getMapId"):
                try:
                    mapid_target = ee.Image(mapid_target)
                except Exception:
                    pass
            try:
                mapid_target.getMapId(map_viz)
            except Exception as e:
                err = str(e)
                # Truncate verbose tracebacks so the agent sees something
                # actionable rather than a wall of text.
                if "\n" in err:
                    err = err.split("\n")[0]
                if len(err) > 300:
                    err = err[:300] + "…"
                skipped.append({"name": name, "reason": f"getMapId failed: {err}"})
                continue

            out_name = _unique_name(name)
            layers[out_name] = {
                "serialized": serialized,
                "viz": map_viz,
                "visible": visible,
            }

        payload = {
            "version": 1,
            "layer_count": len(layers),
            "layers": layers,
        }
        with open(full_path, "w", encoding="utf-8") as f:
            _json.dump(payload, f, indent=2)

        return {
            "path": full_path,
            "layer_names": list(layers.keys()),
            "layer_count": len(layers),
            "skipped": skipped,
            "warnings": warnings,
        }

    ######################################################################
    def testLayers(self):
        """Validate all map layers by requesting a map tile ID from Earth Engine in parallel.

        Calls ``getMapId(viz)`` on every ee object added via ``addLayer`` or
        ``addTimeLapse``.  This catches bad band names, invalid viz params,
        missing properties, and computation errors -- without launching a
        browser.  Runs all requests in parallel via ``ThreadPoolExecutor``.

        When ``autoViz: True`` is set in a layer's viz params, the method also
        validates that the image carries the class properties the viewer
        expects: ``<bandName>_class_values``, ``<bandName>_class_names``, and
        ``<bandName>_class_palette`` for at least one band.

        Returns:
            dict: Structure::

                {
                    "pass": bool,          # True only if every layer has status "ok"
                    "layers": [
                        {
                            "name": str,
                            "status": "ok" | "error",
                            "error": str | None,
                            "warnings": list[str] | None  # present only when non-empty
                        },
                        ...
                    ]
                }

            Error vs warning distinction:

            - **Error** (``status="error"``): ``autoViz: True`` but *no* band
              has any matching class properties, so the viewer will break.
              Also raised when class properties exist but are keyed to band
              names that don't exist on the image (orphaned properties).
            - **Warning** (``status="ok"`` with ``warnings``): A band has
              *partial* class properties (e.g. ``_class_values`` is present
              but ``_class_palette`` is missing). Rendering may be incorrect.

        Example:
            >>> Map.clearMap()
            >>> Map.addLayer(ee.Image(1), {}, "Valid")
            >>> Map.addLayer(ee.Image(1).select("nonexistent"), {}, "Bad Band")
            >>> result = Map.testLayers()
            >>> result["pass"]
            False
        """
        import concurrent.futures

        layers = []
        futures = {}

        def _test_layer(idx, idDict):
            ee_obj = idDict.get("_ee_obj")
            viz = idDict.get("_viz", {})
            name = idDict.get("name", f"Layer {idx}")
            # ── Non-EE layer types: probe the service URL ──
            # These layers don't have an EE object to getMapId on; the
            # only meaningful test is "does the underlying service
            # respond". A HEAD/GET on a single tile (or the dynamic
            # service metadata endpoint) catches the common failure
            # modes: URL typo, service moved / retired, 401/403 for
            # tokenless secured services, DNS resolution failing.
            if idDict.get("_is_tile_url"):
                # Plug in z=1, x=0, y=0 — the "world tile" — for a
                # dirt-cheap probe. Uses `requests` if present, urllib
                # otherwise; short timeout so a slow tile server can't
                # stall the whole export.
                _tpl = idDict.get("_tile_url_template", "")
                _probe = (_tpl.replace("{z}", "1")
                              .replace("{x}", "0")
                              .replace("{y}", "0"))
                try:
                    import urllib.request as _ur, urllib.error as _ue
                    _req = _ur.Request(_probe, method="HEAD")
                    with _ur.urlopen(_req, timeout=8) as _rsp:
                        if _rsp.status >= 400:
                            return {"name": name, "status": "error",
                                    "error": f"tile URL returned HTTP {_rsp.status} — check the template"}
                except _ue.HTTPError as _he:
                    return {"name": name, "status": "error",
                            "error": f"tile URL returned HTTP {_he.code} — check the template"}
                except Exception as _te:
                    return {"name": name, "status": "error",
                            "error": f"tile URL unreachable: {_te}"}
                return {"name": name, "status": "ok", "error": None}
            if idDict.get("_is_dynamic_esri"):
                # Dynamic Esri MapServer: probe the service metadata
                # endpoint (strip the ``/export?...bbox=`` we appended).
                _bu = idDict.get("_dyn_base_url_1", "")
                _svc = _bu.split("/export?")[0]
                try:
                    import urllib.request as _ur, urllib.error as _ue
                    with _ur.urlopen(f"{_svc}?f=json", timeout=8) as _rsp:
                        if _rsp.status >= 400:
                            return {"name": name, "status": "error",
                                    "error": f"MapServer returned HTTP {_rsp.status}"}
                except _ue.HTTPError as _he:
                    return {"name": name, "status": "error",
                            "error": f"MapServer returned HTTP {_he.code}"}
                except Exception as _te:
                    return {"name": name, "status": "error",
                            "error": f"MapServer unreachable: {_te}"}
                return {"name": name, "status": "ok", "error": None}
            if ee_obj is None:
                # GeoJSON layers — no ee object to test
                return {"name": name, "status": "ok", "error": None}
            # Build viz params for getMapId — only pass recognized keys
            map_viz = {}
            for k in ("bands", "min", "max", "gain", "bias", "gamma", "palette", "opacity", "format"):
                if k in viz:
                    map_viz[k] = viz[k]
            warnings = []
            try:
                # Style vectors to match geeView viewer rendering
                test_obj, style_mode = mapper._style_vector(ee_obj, viz)
                if style_mode == "painted":
                    # paint() returns single-band — use strokeColor as palette
                    sc = viz.get("color") or viz.get("strokeColor")
                    if sc:
                        map_viz["palette"] = [sc.replace("#", "")]
                    map_viz.pop("bands", None)
                elif style_mode == "styled":
                    # .style() returns RGBA — colors baked in, no viz needed
                    map_viz = {}
                else:
                    # For ImageCollections (incl. time lapses), .mosaic() to get a single
                    # representative tile preview. Otherwise getMapId picks an arbitrary
                    # image which may be blank/wrong-area for tiled collections.
                    obj_cls = test_obj.__class__.__name__
                    if obj_cls == "ImageCollection":
                        try:
                            test_obj = test_obj.mosaic()
                            idDict["_is_mosaic_preview"] = True
                        except Exception:
                            pass

                map_id = test_obj.getMapId(map_viz)
                # Cache the tile fetcher so previewMap can reuse it
                idDict["_tile_fetcher"] = map_id.get("tile_fetcher")
            except Exception as e:
                return {"name": name, "status": "error", "error": str(e)}

            # --- autoViz validation: check class properties exist for band names ---
            # When autoViz is True, the viewer expects <bandName>_class_values,
            # <bandName>_class_names, <bandName>_class_palette properties on the
            # image. If these are missing, the viewer fails silently or shows a
            # cryptic JS error like "Cannot read properties of undefined".
            try:
                if viz.get("autoViz"):
                    # Get the ee object to check — for ImageCollection, use .first()
                    check_obj = ee_obj
                    obj_type = ee_obj.__class__.__name__
                    if obj_type == "ImageCollection":
                        check_obj = ee_obj.first()

                    if hasattr(check_obj, "bandNames") and hasattr(check_obj, "toDictionary"):
                        band_names = check_obj.bandNames().getInfo()
                        # Fetch full property dict so we can inspect VALUES (not just keys)
                        # and detect string-encoded class properties that need normalizing.
                        full_props = check_obj.toDictionary().getInfo()
                        prop_keys = set(full_props.keys())

                        # ── Normalize string-encoded class properties ──
                        # Some assets store class_values/names/palette as comma-separated
                        # strings ("1,2,3") instead of lists. The JS viewer's autoViz can't
                        # handle strings — it expects arrays. Detect strings and re-set
                        # corrected list values on the image, then re-serialize.
                        def _normalize_str_prop(v, as_int=False):
                            if not isinstance(v, str):
                                return None  # already a list, no normalization needed
                            # LCMS convention: true delimiter is a bare comma;
                            # intra-name commas always have a trailing space
                            # ("Insect, Disease, or Drought Stress" is ONE
                            # class name). Split on comma-not-followed-by-space
                            # so that reconstitutes correctly.
                            import re as _re
                            parts = [p.strip() for p in _re.split(r",(?! )", v) if p.strip()]
                            if as_int:
                                out = []
                                for p in parts:
                                    try:
                                        out.append(int(p))
                                    except (ValueError, TypeError):
                                        try:
                                            out.append(int(float(p)))
                                        except (ValueError, TypeError):
                                            out.append(p)
                                return out
                            return parts

                        corrected = {}
                        for bn in band_names:
                            for suffix, as_int in (("values", True), ("names", False), ("palette", False)):
                                key = f"{bn}_class_{suffix}"
                                if key in full_props:
                                    fixed = _normalize_str_prop(full_props[key], as_int=as_int)
                                    if fixed is not None:
                                        corrected[key] = fixed

                        if corrected:
                            # Apply corrected props to the EE object and re-serialize
                            # so the viewer (which uses idDict["item"]) gets lists.
                            try:
                                if obj_type == "ImageCollection":
                                    fixed_ee = ee_obj.map(lambda img: img.set(corrected))
                                else:
                                    fixed_ee = ee_obj.set(corrected)
                                idDict["_ee_obj"] = fixed_ee
                                idDict["item"] = fixed_ee.serialize()
                                # Drop cached tile fetcher — it's tied to the old object
                                idDict.pop("_tile_fetcher", None)
                                warnings.append(
                                    f"Normalized {len(corrected)} string-encoded class "
                                    f"properties to lists (asset stored them comma-separated)."
                                )
                            except Exception as norm_err:
                                warnings.append(
                                    f"Detected string-encoded class properties but failed "
                                    f"to normalize: {norm_err}"
                                )

                        for bn in band_names:
                            cv_key = f"{bn}_class_values"
                            cn_key = f"{bn}_class_names"
                            cp_key = f"{bn}_class_palette"
                            has_cv = cv_key in prop_keys
                            has_cn = cn_key in prop_keys
                            has_cp = cp_key in prop_keys

                            if has_cv or has_cn or has_cp:
                                # At least one exists — check all three are present
                                missing = []
                                if not has_cv:
                                    missing.append(cv_key)
                                if not has_cn:
                                    missing.append(cn_key)
                                if not has_cp:
                                    missing.append(cp_key)
                                if missing:
                                    warnings.append(
                                        f"Band '{bn}' has partial class properties "
                                        f"(missing: {', '.join(missing)}). "
                                        f"autoViz may not render correctly."
                                    )
                            # If none exist for this band, that's fine — autoViz
                            # will use continuous viz for that band.

                        # Check if NO band has any class properties at all
                        has_any_class_props = any(
                            f"{bn}_class_values" in prop_keys for bn in band_names
                        )
                        if not has_any_class_props:
                            # This is an error — the map will break
                            # Check if class props exist for OTHER names (wrong band names)
                            orphan_prefixes = set()
                            for pk in prop_keys:
                                if pk.endswith("_class_values"):
                                    prefix = pk[: -len("_class_values")]
                                    if prefix not in band_names:
                                        orphan_prefixes.add(prefix)

                            if orphan_prefixes:
                                err_msg = (
                                    f"autoViz is True but class properties are set for "
                                    f"bands that don't exist in this image "
                                    f"({', '.join(sorted(orphan_prefixes)[:3])}). "
                                    f"Actual bands: {', '.join(band_names[:5])}. "
                                    f"Rename the properties to match the band names "
                                    f"(e.g. {band_names[0]}_class_values)."
                                )
                            else:
                                err_msg = (
                                    f"autoViz=True but no band has class properties "
                                    f"({band_names[0]}_class_values... not found). "
                                    f"If the image came from a reducer (.mosaic/.median/.reduce), "
                                    f"those strip user properties — reattach with "
                                    f"ee.Image(img.copyProperties(collection.first()))."
                                )
                            return {"name": name, "status": "error", "error": err_msg}
            except Exception as e:
                # Don't let validation failure block the test
                warnings.append(f"autoViz check failed: {e}")

            result = {"name": name, "status": "ok", "error": None}
            if warnings:
                result["warnings"] = warnings
            return result

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for idx, idDict in enumerate(self.idDictList):
                futures[pool.submit(_test_layer, idx, idDict)] = idx

            for future in concurrent.futures.as_completed(futures):
                layers.append(future.result())

        # Sort by original layer order
        layers.sort(key=lambda x: next(
            (i for i, d in enumerate(self.idDictList) if d.get("name") == x["name"]), 0
        ))

        all_passed = all(l["status"] == "ok" for l in layers)
        return {"pass": all_passed, "layers": layers}

    ######################################################################
    def previewMap(self, grid_size=3, zoom=None):
        """Fetch a small grid of map tiles for each layer and return as a dict.

        This gives the LLM a quick visual preview of each map layer without
        launching a browser.  Uses ``getMapId`` + ``tile_fetcher.fetch_tile``
        to grab tiles around the current map center, then stitches them with
        Pillow into a single PNG per layer.

        Args:
            grid_size (int): Number of tiles per side (e.g. 3 = 3x3 = 9 tiles).
                Default 3, producing a 768x768 px image per layer.
            zoom (int, optional): Zoom level for tiles.  If None, uses the zoom
                from the last ``setCenter``/``setZoom`` call, or auto-calculates
                from ``centerObject`` bounds.  Falls back to 8.

        Returns:
            dict: ``{"layers": {layer_name: png_bytes, ...}, "center": [lng, lat], "zoom": int}``
                Each value in ``layers`` is raw PNG bytes of the stitched tile grid.
                Layers that fail to render are included with a ``None`` value.
        """
        import concurrent.futures
        import math
        import re
        import io

        from PIL import Image as PILImage

        # ── Parse center / zoom from mapCommandList ──
        center_lng, center_lat = 0.0, 0.0
        parsed_zoom = None
        bounds_coords = None

        for cmd in self.mapCommandList:
            m = re.match(r'Map\.setCenter\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]*)\s*\)', cmd)
            if m:
                center_lng = float(m.group(1))
                center_lat = float(m.group(2))
                z_str = m.group(3).strip()
                if z_str and z_str != "null":
                    parsed_zoom = int(float(z_str))
                continue
            m = re.match(r'map\.setZoom\((\d+)\)', cmd)
            if m:
                parsed_zoom = int(m.group(1))
                continue
            m = re.match(r'synchronousCenterObject\((.+)\)', cmd)
            if m:
                try:
                    geojson = json.loads(m.group(1))
                    coords = geojson.get("coordinates", [[]])[0]
                    if coords:
                        lngs = [c[0] for c in coords]
                        lats = [c[1] for c in coords]
                        center_lng = (min(lngs) + max(lngs)) / 2
                        center_lat = (min(lats) + max(lats)) / 2
                        bounds_coords = (min(lngs), min(lats), max(lngs), max(lats))
                except Exception:
                    pass

        # Determine zoom
        if zoom is not None:
            z = zoom
        elif parsed_zoom is not None:
            z = parsed_zoom
        elif bounds_coords is not None:
            # Auto-calculate zoom to fit bounds in grid_size tiles
            lng_span = bounds_coords[2] - bounds_coords[0]
            lat_span = bounds_coords[3] - bounds_coords[1]
            span = max(lng_span, lat_span)
            if span > 0:
                z = max(1, min(15, int(math.log2(360 / span * grid_size)) - 1))
            else:
                z = 10
        else:
            z = 8

        # ── Tile coordinate math ──
        def _lat_lon_to_tile(lat, lon, zoom_level):
            n = 2 ** zoom_level
            x = int((lon + 180) / 360 * n)
            lat_rad = math.radians(max(-85, min(85, lat)))
            y = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)
            return x, y

        cx, cy = _lat_lon_to_tile(center_lat, center_lng, z)
        half = grid_size // 2
        tiles_xy = [(cx + dx, cy + dy)
                     for dy in range(-half, half + 1)
                     for dx in range(-half, half + 1)]

        # ── Get tile fetchers for each layer (reuse cached from testLayers) ──
        layer_fetchers = {}
        for idx, idDict in enumerate(self.idDictList):
            ee_obj = idDict.get("_ee_obj")
            viz = idDict.get("_viz", {})
            name = idDict.get("name", f"Layer {idx}")
            if ee_obj is None:
                continue
            # Reuse tile fetcher cached by testLayers if available
            cached_fetcher = idDict.get("_tile_fetcher")
            if cached_fetcher is not None:
                layer_fetchers[name] = cached_fetcher
                continue
            # Otherwise create a new one (with vector styling)
            map_viz = {}
            for k in ("bands", "min", "max", "gain", "bias", "gamma", "palette", "opacity", "format"):
                if k in viz:
                    map_viz[k] = viz[k]
            try:
                test_obj, style_mode = mapper._style_vector(ee_obj, viz)
                if style_mode == "painted":
                    sc = viz.get("color") or viz.get("strokeColor")
                    if sc:
                        map_viz["palette"] = [sc.replace("#", "")]
                    map_viz.pop("bands", None)
                elif style_mode == "styled":
                    map_viz = {}
                else:
                    # For ImageCollections (incl. time lapses), mosaic to a single tile
                    if test_obj.__class__.__name__ == "ImageCollection":
                        try:
                            test_obj = test_obj.mosaic()
                            idDict["_is_mosaic_preview"] = True
                        except Exception:
                            pass
                map_id = test_obj.getMapId(map_viz)
                idDict["_tile_fetcher"] = map_id["tile_fetcher"]
                layer_fetchers[name] = map_id["tile_fetcher"]
            except Exception:
                layer_fetchers[name] = None

        # ── Fetch tiles in parallel and stitch per layer ──
        result_layers = {}
        tile_size = 256

        def _fetch_tile(fetcher, tx, ty, tz):
            try:
                return fetcher.fetch_tile(tx, ty, tz)
            except Exception:
                return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            for layer_name, fetcher in layer_fetchers.items():
                if fetcher is None:
                    result_layers[layer_name] = None
                    continue

                # Submit all tile fetches for this layer
                futures = {}
                for tx, ty in tiles_xy:
                    futures[(tx, ty)] = pool.submit(_fetch_tile, fetcher, tx, ty, z)

                # Stitch tiles
                img = PILImage.new("RGBA", (grid_size * tile_size, grid_size * tile_size), (0, 0, 0, 0))
                for i, (tx, ty) in enumerate(tiles_xy):
                    tile_bytes = futures[(tx, ty)].result()
                    if tile_bytes:
                        try:
                            tile_img = PILImage.open(io.BytesIO(tile_bytes)).convert("RGBA")
                            col = i % grid_size
                            row = i // grid_size
                            img.paste(tile_img, (col * tile_size, row * tile_size))
                        except Exception:
                            pass

                # Downscale to ~300px to keep LLM context small
                max_dim = 300
                if max(img.size) > max_dim:
                    ratio = max_dim / max(img.size)
                    new_size = (int(img.width * ratio), int(img.height * ratio))
                    img = img.resize(new_size, PILImage.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                result_layers[layer_name] = buf.getvalue()

        return {
            "layers": result_layers,
            "center": [center_lng, center_lat],
            "zoom": z,
        }

    ######################################################################
    def testView(self, width=1280, height=900, wait_seconds=12):
        """Capture a screenshot of the map via headless Chrome CDP and check for tile errors.

        This is a slower but more thorough test than ``testLayers`` — it
        renders the full map viewer in a headless browser and captures JS
        console errors and HTTP tile failures.  Use ``testLayers`` for fast
        validation; use ``testView`` when you need a visual screenshot or
        want to catch client-side rendering issues.

        Args:
            width (int): Viewport width in pixels.
            height (int): Viewport height in pixels.
            wait_seconds (int): Max seconds to wait for tiles to load.

        Returns:
            dict: ``{"screenshot_path": str, "tile_errors": list, "console_messages": list}``
        """
        from geeViz.outputLib import charts as _cl
        import datetime as _dt

        # Get the viewer URL without opening a browser
        url = self.view(open_browser=False)
        if not url:
            return {"error": "No viewer URL available — add layers first."}

        png_bytes, console_msgs = _cl.screenshot_url(url, width=width, height=height, wait_seconds=wait_seconds)

        if not png_bytes:
            return {"error": "Screenshot failed.", "console_messages": console_msgs}

        tile_errors = [m for m in console_msgs if "earthengine" in m or "googleapis" in m
                       or "HTTP 4" in m or "HTTP 5" in m or "LOAD FAIL" in m]
        other_msgs = [m for m in console_msgs if m not in tile_errors]

        # Save screenshot
        import os
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp", "generated_outputs")
        os.makedirs(output_dir, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(output_dir, f"map_screenshot_{ts}.png")
        with open(screenshot_path, "wb") as fp:
            fp.write(png_bytes)

        return {
            "screenshot_path": screenshot_path,
            "tile_errors": tile_errors,
            "console_messages": other_msgs,
        }

    ######################################################################
    def setMapTitle(self, title):
        """
        Set the title that appears in the left sidebar header and the page title

        Args:
            title (str, default geeViz Data Explorer): The title to appear in the header on the left sidebar as well as the title of the viewer webpage.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms, {"autoViz": True}, "LCMS")
        >>> Map.turnOnInspector()
        >>> Map.setMapTitle("<h2>A Custom Title!!!</h2>")  # Set custom map title
        >>> Map.view()
        """
        title_command = f"Map.setTitle({_js_str(title)})"
        if title_command not in self.mapCommandList:
            self.mapCommandList.append(title_command)

    ######################################################################
    def setTitle(self, title):
        """
        Redundant function for setMapTitle.
        Set the title that appears in the left sidebar header and the page title

        Args:
            title (str, default geeViz Data Explorer): The title to appear in the header on the left sidebar as well as the title of the viewer webpage.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms, {"autoViz": True}, "LCMS")
        >>> Map.turnOnInspector()
        >>> Map.setMapTitle("<h2>A Custom Title!!!</h2>")  # Set custom map title
        >>> Map.view()
        """
        self.setMapTitle(title)

    ######################################################################
    # Functions to set various click query properties
    def setQueryCRS(self, crs: str):
        """
        The coordinate reference system string to query layers with

        Args:
            crs (str, default "EPSG:5070"): Which projection (CRS) to use for querying map layers.

        >>> import geeViz.getImagesLib as gil
        >>> from geeViz.geeView import *
        >>> crs = gil.common_projections["NLCD_AK"]["crs"]
        >>> transform = gil.common_projections["NLCD_AK"]["transform"]
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="AK"')
        >>> Map.addLayer(lcms, {"autoViz": True}, "LCMS")
        >>> Map.turnOnInspector()
        >>> Map.setQueryCRS(crs)
        >>> Map.setQueryTransform(transform)
        >>> Map.setCenter(-144.36390353, 60.20479529215, 8)
        >>> Map.view()
        """
        print("Setting click query crs to: {}".format(crs))
        cmd = f"Map.setQueryCRS({_js_str(crs)})"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryScale(self, scale: int):
        """
        What scale to query map layers with. Will also update the size of the box drawn on the map query layers are queried.

        Args:
            scale (int, default None): The spatial resolution to use for querying map layers in meters. If set, the query transform will be set to None in the map viewer.

        >>> import geeViz.getImagesLib as gil
        >>> from geeViz.geeView import *
        >>> s2s = gil.superSimpleGetS2(ee.Geometry.Point([-107.61, 37.85]), "2024-01-01", "2024-12-31", 190, 250)
        >>> projection = s2s.first().select(["nir"]).projection().getInfo()
        >>> Map.addLayer(s2s.median(), gil.vizParamsFalse10k, "Sentinel-2 Composite")
        >>> Map.turnOnInspector()
        >>> Map.setQueryCRS(projection["crs"])
        >>> Map.setQueryScale(projection["transform"][0])
        >>> Map.centerObject(s2s.first())
        >>> Map.view()

        """
        print("Setting click query scale to: {}".format(scale))
        cmd = f"Map.setQueryScale({scale})"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryTransform(self, transform: list[int]):
        """
        What transform to query map layers with. Will also update the size of the box drawn on the map query layers are queried.

        Args:
            transform (list, default [30, 0, -2361915, 0, -30, 3177735]): The snap to grid to use for querying layers on the map. If set, the query scale will be set to None in the map viewer.

        >>> import geeViz.getImagesLib as gil
        >>> from geeViz.geeView import *
        >>> s2s = gil.superSimpleGetS2(ee.Geometry.Point([-107.61, 37.85]), "2024-01-01", "2024-12-31", 190, 250)
        >>> projection = s2s.first().select(["nir"]).projection().getInfo()
        >>> Map.addLayer(s2s.median(), gil.vizParamsFalse10k, "Sentinel-2 Composite")
        >>> Map.turnOnInspector()
        >>> Map.setQueryCRS(projection["crs"])
        >>> Map.setQueryTransform(projection["transform"])
        >>> Map.centerObject(s2s.first())
        >>> Map.view()

        """
        print("Setting click query transform to: {}".format(transform))
        cmd = f"Map.setQueryTransform({transform})"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryPrecision(self, chartPrecision: int = 3, chartDecimalProportion: float = 0.25):
        """
        What level of precision to show for queried layers. This avoids showing too many digits after the decimal.

        Args:
            chartPrecision (int, default 3): Will show the larger of `chartPrecision` decimal places or ceiling(`chartDecimalProportion` * total decimal places). E.g. if the number is 1.12345678, 0.25 of 8 decimal places is 2, so 3 will be used and yield 1.123.
            chartDecimalProportion (float, default 0.25): Will show the larger of `chartPrecision` decimal places or `chartDecimalProportion` * total decimal places. E.g. if the number is 1.1234567891234, ceiling(0.25 of 13) decimal places is 4, so 4 will be used and yield 1.1235.

        >>> import geeViz.getImagesLib as gil
        >>> from geeViz.geeView import *
        >>> s2s = gil.superSimpleGetS2(ee.Geometry.Point([-107.61, 37.85]), "2024-01-01", "2024-12-31", 190, 250).select(["blue", "green", "red", "nir", "swir1", "swir2"])
        >>> projection = s2s.first().select(["nir"]).projection().getInfo()
        >>> s2s = s2s.map(lambda img: ee.Image(img).divide(10000).set("system:time_start",img.date().millis()))
        >>> Map.addLayer(s2s, gil.vizParamsFalse, "Sentinel-2 Images")
        >>> Map.addLayer(s2s.median(), gil.vizParamsFalse, "Sentinel-2 Composite")
        >>> Map.turnOnInspector()
        >>> Map.setQueryCRS(projection["crs"])
        >>> Map.setQueryTransform(projection["transform"])
        >>> Map.setQueryPrecision(chartPrecision=2, chartDecimalProportion=0.1)
        >>> Map.centerObject(s2s.first())
        >>> Map.view()
        """
        print("Setting click query precision to: {}".format(chartPrecision))
        cmd = f"Map.setQueryPrecision({chartPrecision},{chartDecimalProportion})"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryDateFormat(self, defaultQueryDateFormat: str = "YYYY-MM-dd"):
        """
        Set the date format to be used for any dates when querying.

        Args:
            defaultQueryDateFormat (str, default "YYYY-MM-dd"): The date format string to use for query outputs with dates. To simplify date outputs, "YYYY" is often used instead of the default.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.addLayer(lcms.select([0]), {"autoViz": True}, "LCMS Change")
        >>> Map.turnOnInspector()
        >>> Map.setQueryDateFormat("YYYY")
        >>> Map.view()

        """
        print("Setting default query date format to: {}".format(defaultQueryDateFormat))
        cmd = f"Map.setQueryDateFormat({_js_str(defaultQueryDateFormat)})"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    def setQueryBoxColor(self, color: str):
        """
        Set the color of the query box to something other than yellow

        Args:
            color (str, default "FFFF00"): Set the default query box color shown on the map by providing a hex color.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.turnOnInspector()
        >>> Map.setQueryBoxColor("0FF")
        >>> Map.view()
        """
        print("Setting click query box color to: {}".format(color))
        cmd = f"Map.setQueryBoxColor({_js_str(color)})"
        if cmd not in self.mapCommandList:
            self.mapCommandList.append(cmd)

    ######################################################################
    # Functions to handle location of query outputs
    def setQueryWindowMode(self, mode):
        """Set where inspector query results are rendered.

        Low-level setter — prefer ``setQueryToInfoWindow()`` or
        ``setQueryToSidePane()`` unless you know the exact mode string
        the frontend expects.

        Args:
            mode (str): One of ``"infoWindow"`` (popup over the map) or
                ``"sidePane"`` (dedicated results panel).
        """
        self.queryWindowMode = mode

    def setQueryToInfoWindow(self):
        """
        Set the location of query outputs to an info window popup over the map

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.turnOnInspector()
        >>> Map.setQueryToInfoWindow()
        >>> Map.view()
        """
        self.setQueryWindowMode("infoWindow")

    def setQueryToSidePane(self):
        """
        Set the location of query outputs to the right sidebar above the legend

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.turnOnInspector()
        >>> Map.setQueryToSidePane()
        >>> Map.view()
        """
        self.setQueryWindowMode("sidePane")

    ######################################################################
    # Turn on query inspector
    def turnOnInspector(self):
        """
        Turn on the query inspector tool upon map loading. This is used frequently so map layers can be queried as soon as the map viewer loads.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.turnOnInspector()
        >>> Map.view()
        """
        query_command = "Map.turnOnInspector()"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    # Turn on area charting
    def turnOnAutoAreaCharting(self):
        """
        Turn on automatic area charting upon map loading. This will automatically update charts by summarizing any visible layers with "canAreaChart" : True any time the map finishes panning or zooming.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True,'canAreaChart':True}, "LCMS Land Cover")
        >>> Map.turnOnAutoAreaCharting()
        >>> Map.view()
        """
        query_command = "Map.turnOnAutoAreaCharting()"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    def turnOnUserDefinedAreaCharting(self):
        """
        Turn on area charting by a user defined area upon map loading. This will update charts by summarizing any visible layers with "canAreaChart" : True when the user draws an area to summarize and hits the `Chart Selected Areas` button in the user interface under `Area Tools -> User-Defined Area`.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True,'canAreaChart':True}, "LCMS Land Cover")
        >>> Map.turnOnUserDefinedAreaCharting()
        >>> Map.view()
        """
        query_command = "Map.turnOnUserDefinedAreaCharting()"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    def turnOnSelectionAreaCharting(self):
        """
        Turn on area charting by a user selected area upon map loading. This will update charts by summarizing any visible layers with "canAreaChart" : True when the user selects selection areas to summarize and hits the `Chart Selected Areas` button in the user interface under `Area Tools -> Select an Area on Map`.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True,'canAreaChart':True}, "LCMS Land Cover")
        >>> mtbsBoundaries = ee.FeatureCollection("USFS/GTAC/MTBS/burned_area_boundaries/v1")
        >>> mtbsBoundaries = mtbsBoundaries.map(lambda f: f.set("system:time_start", f.get("Ig_Date")))
        >>> Map.addSelectLayer(mtbsBoundaries, {"strokeColor": "00F", "selectLayerNameProperty": "Incid_Name"}, "MTBS Fire Boundaries")
        >>> Map.turnOnSelectionAreaCharting()
        >>> Map.view()
        """
        query_command = "Map.turnOnSelectionAreaCharting()"
        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    def addAreaChartLayer(self, image: ee.Image | ee.ImageCollection, params: dict = {}, name: str | None = None, shouldChart: bool = True):
        """
        Use this method to add a layer for area charting that you do not want as a map layer as well. Once you add all area chart layers to the map, you can turn them on using the `Map.populateAreaChartLayerSelect` method. This will create a selection menu inside the `Area Tools -> Area Tools Parameters` menu. You can then turn layers to include in any area charts on and off from that menu.

        Args:
            image (ImageCollection, Image): ee Image or ImageCollection to add to include in area charting.
            params (dict): Primary set of parameters for charting setup (colors, chart types, etc), charting, etc. The accepted keys are:

                {

                    "reducer" (Reducer, default `ee.Reducer.mean()` if no bandName_class_values, bandName_class_names, bandName_class_palette properties are available. `ee.Reducer.frequencyHistogram` if those are available or `thematic`:True (see below)): The reducer used to compute zonal summary statistics.,

                    "crs" (str, default "EPSG:5070"): the coordinate reference system string to use for are chart zonal stats,

                    "transform" (list, default [30, 0, -2361915, 0, -30, 3177735]): the transform to snap to for zonal stats,

                    "scale" (int, default None): The spatial resolution to use for zonal stats. Only specify if transform : None.

                    "line" (bool, default True): Whether to create a line chart,

                    "sankey" (bool, default False): Whether to create Sankey charts - only available for thematic (discrete) inputs that have a `system:time_start` property set for each image,

                    "chartLabelMaxWidth" (int, default 40): The maximum number of characters, including spaces, allowed in a single line of a chart class label. The class name will be broken at this number of characters, including spaces, to go to the next line,

                    "chartLabelMaxLength" (int, default 100): The maximum number of characters, including spaces, allowed in a chart class label. Any class name with more characters, including spaces, than this number will be cut off at this number of characters,

                    "sankeyTransitionPeriods" (list of lists, default None): The years to use as transition periods for sankey charts (e.g. [[1985,1987],[2000,2002],[2020,2022]]). If not provided, users can enter years in the map user interface under `Area Tools -> Transition Charting Periods`. These will automatically be used for any layers where no sankeyTransitionPeriods were provided. If years are provided, the years in the user interface will not be used for that layer,

                    "sankeyMinPercentage" (float, default 0.5): The minimum percentage a given class has to be to be shown in the sankey chart,

                    "thematic" (bool): Whether input has discrete values or not. If True, it forces the reducer to `ee.Reducer.frequencyHistogram()` even if not specified and even if bandName_class_values, bandName_class_names, bandName_class_palette properties are not available,

                    "palette" (list, or comma-separated strings): List of hex codes for colors for charts. This is especially useful when bandName_class_values, bandName_class_names, bandName_class_palette properties are not available, but there is a desired set of colors for each band to have on the chart,

                    "showGrid" (bool, default True): Whether to show the grid lines on the line or bar graph,

                    "rangeSlider" (bool,default False): Whether to include the x-axis range selector on the bottom of each graph (`https://plotly.com/javascript/range-slider/>`),

                    "barChartMaxClasses" (int, default 20): The maximum number of classes to show for image bar charts. Will automatically only show the top `bartChartMaxClasses` in any image bar chart. Any downloaded csv table will still have all of the class counts,

                    "minZoomSpecifiedScale" (int, default 11): The map zoom level where any lower zoom level, not including this zoom level, will multiply the spatial resolution used for the zonal stats by 2 for each lower zoom level. E.g. if the `minZoomSpecifiedScale` is 9 and the `scale` is 30, any zoom level >= 9 will compute zonal stats at 30m spatial resolution. Then, at zoom level 8, it will be 60m. Zoom level 7 will be 120m, etc,

                    "chartPrecision" (int, default 3): Used to override the default global precision settings for a specific area charting layer. See `setQueryPrecision` for setting the global charting precision. When specified, for this specific area charting layer, will show the larger of `chartPrecision` decimal places or ceiling(`chartDecimalProportion` * total decimal places). E.g. if the number is 1.12345678, 0.25 of 8 decimal places is 2, so 3 will be used and yield 1.123,

                    "chartDecimalProportion" (float, default 0.25): Used to override the default global precision settings for a specific area charting layer. See `setQueryPrecision` for setting the global charting precision. When specified, for this specific area charting layer, will show the larger of `chartPrecision` decimal places or `chartDecimalProportion` * total decimal places. E.g. if the number is 1.1234567891234, ceiling(0.25 of 13) decimal places is 4, so 4 will be used and yield 1.1235,

                    "hovermode" (str, default "closest"): The mode to show hover text in area summary charts. Options include "closest", "x", "y", "x unified", and "y unified",

                    "yAxisLabel" (str, default an appropriate label based on whether data are thematic or continuous): The Y axis label that will be included in charts. Defaults to a unit of % area for thematic and mean for continuous data,

                    "chartType" (str, default "line" for `ee.ImageCollection` and "bar" for `ee.Image` objects): The type of chart to show. Options include "line", "bar", "stacked-line", and "stacked-bar". This is only used for `ee.ImageCollection` objects. For `ee.Image` objects, the chartType is always "bar".

                }
            name (str): Descriptive name for map layer that will be shown on the map UI
            shouldChart (bool, optional): Whether layer should be charted when map UI loads

        >>> import geeViz.geeView as gv
        >>> Map = gv.Map
        >>> ee = gv.ee
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select(["Change_Raw_Probability.*"]), {"reducer": ee.Reducer.stdDev(), "min": 0, "max": 10}, "LCMS Change Prob")
        >>> Map.addAreaChartLayer(lcms, {"line": True, "layerType": "ImageCollection"}, "LCMS All Thematic Classes Line", True)
        >>> Map.addAreaChartLayer(lcms, {"sankey": True}, "LCMS All Thematic Classes Sankey", True)
        >>> Map.populateAreaChartLayerSelect()
        >>> Map.turnOnAutoAreaCharting()
        >>> Map.view()

        """
        if name == None:
            name = "Area Chart Layer " + str(self.layerNumber)
            self.layerNumber += 1
        print("Adding area chart layer: " + name)

        # Handle reducer if ee object is given
        if "reducer" in params.keys():

            try:
                params["reducer"] = params["reducer"].serialize()
            except Exception as e:
                try:
                    params["reducer"] = eval(params["reducer"]).serialize()
                except Exception as e:  # Most likely it's already serialized
                    e = e

        # Get the id and populate dictionary
        idDict = {}

        if not isinstance(image, dict):
            params["serialized"] = True
            params["layerType"] = type(image).__name__
            image = image.serialize()

        idDict["item"] = image
        idDict["function"] = "addLayer"
        idDict["objectName"] = "areaChart"
        idDict["name"] = name
        idDict["visible"] = str(shouldChart).lower()
        idDict["viz"] = json.dumps(params, sort_keys=False)

        idDict["workloadTag"] = self._capture_workload_tag()
        self.idDictList.append(idDict)

    def populateAreaChartLayerSelect(self):
        """
        Once you add all area chart layers to the map, you can turn them on using this method- `Map.populateAreaChartLayerSelect`. This will create a selection menu inside the `Area Tools -> Area Tools Parameters` menu. You can then turn layers to include in any area charts on and off from that menu.

        >>> import geeViz.geeView as gv
        >>> Map = gv.Map
        >>> ee = gv.ee
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select(["Change_Raw_Probability.*"]), {"reducer": ee.Reducer.stdDev(), "min": 0, "max": 10}, "LCMS Change Prob")
        >>> Map.addAreaChartLayer(lcms, {"line": True, "layerType": "ImageCollection"}, "LCMS All Thematic Classes Line", True)
        >>> Map.addAreaChartLayer(lcms, {"sankey": True}, "LCMS All Thematic Classes Sankey", True)
        >>> Map.populateAreaChartLayerSelect()
        >>> Map.turnOnAutoAreaCharting()
        >>> Map.view()
        """
        query_command = "areaChart.populateChartLayerSelect()"

        if query_command not in self.mapCommandList:
            self.mapCommandList.append(query_command)

    # Functions to handle setting query output y labels
    def setYLabelMaxLength(self, maxLength: int):
        """
        Set the maximum length a Y axis label can have in charts

        Args:
            maxLength (int, default 30): Maximum number of characters in a Y axis label.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.setYLabelMaxLength(10)  # Double-click on map to inspect area. Change to a larger number and rerun to see how Y labels are impacted
        >>> Map.turnOnInspector()
        >>> Map.setCenter(-109.446, 43.620, 12)
        >>> Map.view()
        """
        command = f"yLabelMaxLength = {maxLength}"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    def setYLabelBreakLength(self, maxLength: int):
        """
        Set the maximum length per line a Y axis label can have in charts

        Args:
            maxLength (int, default 10): Maximum number of characters in each line of a Y axis label. Will break total characters (setYLabelMaxLength) until maxLines (setYLabelMaxLines) is reached

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.setYLabelBreakLength(5)  # Double-click on map to inspect area. Change to a larger number and rerun to see how Y labels are impacted
        >>> Map.turnOnInspector()
        >>> Map.setCenter(-109.446, 43.620, 12)
        >>> Map.view()
        """
        command = f"yLabelBreakLength = {maxLength}"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    def setYLabelMaxLines(self, maxLines):
        """
        Set the max number of lines each y-axis label can have.

        Args:
            maxLines (int, default 5): The maximum number of lines each y-axis label can have. Will simply exclude any remaining lines.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.setYLabelMaxLines(3)  # Double-click on map to inspect area. Change to a larger number and rerun to see how Y labels are impacted
        >>> Map.turnOnInspector()
        >>> Map.setCenter(-109.446, 43.620, 12)
        >>> Map.view()
        """
        command = f"yLabelMaxLines = {maxLines}"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    def setYLabelFontSize(self, fontSize: int):
        """
        Set the size of the font on the y-axis labels. Useful when y-axis labels are too large to fit on the chart.

        Args:
            fontSize (int, default 10): The font size used on the y-axis labels for query charting.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.setYLabelFontSize(8)  # Double-click on map to inspect area. Change to a different number and rerun to see how Y labels are impacted
        >>> Map.turnOnInspector()
        >>> Map.setCenter(-109.446, 43.620, 12)
        >>> Map.view()
        """
        command = f"yLabelFontSize = {fontSize}"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    # Specify whether layers can be re-ordered by the user
    def setCanReorderLayers(self, canReorderLayers: bool):
        """
        Set whether layers can be reordered by dragging layer user interface objects. By default all non timelapse and non geojson layers can be reordereed by dragging.

        Args:
            canReorderLayers (bool, default True): Set whether layers can be reordered by dragging layer user interface objects. By default all non timelapse and non geojson layers can be reordereed by dragging.

        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([2]), {"autoViz": True}, "LCMS Land Use")
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.addLayer(lcms.select([0]), {"autoViz": True}, "LCMS Change")
        >>> Map.turnOnInspector()
        >>> Map.setCanReorderLayers(False) # Notice you cannot drag and reorder layers. Change to True and rerun and notice you now can drag layers to reorder
        >>> Map.setCenter(-109.446, 43.620, 12)
        >>> Map.view()
        """
        command = f"Map.canReorderLayers = {str(canReorderLayers).lower()};"
        if command not in self.mapCommandList:
            self.mapCommandList.append(command)

    # Functions to handle batch layer toggling
    def turnOffAllLayers(self):
        """
        Turn off all layers added to the mapper object. Typically used in notebooks or iPython when you want to allow existing layers to remain, but want to turn them all off.

        >>> #%%
        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([2]), {"autoViz": True}, "LCMS Land Use")
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover")
        >>> Map.turnOnInspector()
        >>> Map.setCenter(-109.446, 43.620, 5)
        >>> Map.view()
        >>> #%%
        >>> Map.turnOffAllLayers()
        >>> Map.addLayer(lcms.select([0]), {"autoViz": True}, "LCMS Change")
        >>> Map.view()
        """
        update = {"visible": "false"}
        self.idDictList = [{**d, **update} for d in self.idDictList]

    def turnOnAllLayers(self):
        """
        Turn on all layers added to the mapper object

        >>> #%%
        >>> from geeViz.geeView import *
        >>> lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11").filter('study_area=="CONUS"')
        >>> Map.addLayer(lcms.select([2]), {"autoViz": True}, "LCMS Land Use",False)
        >>> Map.addLayer(lcms.select([1]), {"autoViz": True}, "LCMS Land Cover",False)
        >>> Map.turnOnInspector()
        >>> Map.setCenter(-109.446, 43.620, 5)
        >>> Map.view()
        >>> #%%
        >>> Map.turnOnAllLayers()
        >>> Map.addLayer(lcms.select([0]), {"autoViz": True}, "LCMS Change")
        >>> Map.view()
        """
        update = {"visible": "true"}
        self.idDictList = [{**d, **update} for d in self.idDictList]


# Instantiate Map object
Map = mapper()
