// Earth Engine initialization. No DOM access.
//
// The caller passes the proxy url (the top-level `authProxyAPIURL` in
// compat.js, which the generated runGeeViz.js reassigns with a tenant
// prefix) as a string or a getter, so it is read at call time, never copied.

const NO_TOKEN = [null, undefined, "null", "None", ""];

export function hasAccessToken(urlParams) {
  return !NO_TOKEN.includes(urlParams && urlParams.accessToken);
}

export function projectIdFrom(urlParams) {
  const p = urlParams && urlParams.projectID;
  return p === null || p === undefined || p === "None" || p === "" ? null : p;
}

// The same-origin proxy default, used when nothing sets a proxy url.
function defaultProxyUrl(urlParams) {
  return urlParams.geeAuthProxyURL || globalThis.location.origin + "/ee-api";
}

// port of 1variables.js (token vs proxy mode) and 4map-manager.js eeInit and
// eeInitSuccessCallback. Resolves once ee.initialize succeeds, with the
// default workload tag set; rejects with the failure.
export function initEE(urlParams = globalThis.urlParams || {}, authProxyAPIURL = "") {
  let proxy;
  let apiUrl = "https://earthengine.googleapis.com";
  if (hasAccessToken(urlParams)) {
    proxy = null;
    apiUrl = null;
    ee.data.setAuthToken("", "Bearer", urlParams.accessToken, 3600, [], undefined, false);
  } else {
    const tenantUrl = typeof authProxyAPIURL === "function" ? authProxyAPIURL() : authProxyAPIURL;
    proxy = typeof tenantUrl === "string" && tenantUrl ? tenantUrl : defaultProxyUrl(urlParams);
  }
  return new Promise((resolve, reject) => {
    ee.initialize(
      proxy,
      apiUrl,
      () => {
        ee.data.setDefaultWorkloadTag(`${globalThis.mode || "geeViz"}---viewer-exports`.toLowerCase());
        resolve();
      },
      (failure) => reject(new Error("Failed to authenticate to GEE: " + failure)),
      null,
      projectIdFrom(urlParams)
    );
  });
}

// Message shown when initEE fails, specialized for token mode as in the
// original's eeInitFailureCallback.
export function describeEEFailure(failure, urlParams = {}) {
  const text = String(failure && failure.message ? failure.message : failure);
  const parts = ["Error message: " + text];
  if (hasAccessToken(urlParams)) {
    if (text.indexOf("invalid authentication credentials") > -1)
      parts.push("The access token looks invalid or expired. Rerun the geeViz code to create a new one.");
    if (urlParams.projectID === "None")
      parts.push('Your Google Cloud project id is "None". Try ee.Initialize(project="SomeProjectID") before importing geeViz.');
    if (text.indexOf("not found or deleted") > -1)
      parts.push("The project " + urlParams.projectID + " cannot be found.");
    if (text.indexOf("Caller does not have required permission to use project") > -1)
      parts.push("The project " + urlParams.projectID + " cannot be accessed. Initialize with another project or re-authenticate.");
  }
  return parts.join("<br>");
}

// ---- loading Earth Engine on demand ----
// The page does not load the Earth Engine library up front: a map with no
// Earth Engine layers never needs it. The first Earth Engine layer asks for
// it through a loader, which loads the script and signs in once.
export const EE_SCRIPT_URL = "https://cdn.jsdelivr.net/gh/google/earthengine-api@0.1.384/javascript/build/ee_api_js.js";
// Subresource integrity for that exact file, as the page's script tag had it.
export const EE_SCRIPT_INTEGRITY = "sha384-tVeKMyegigBNslCtw6N8XPV6d0lspVooP+BNun6SrZw5uy4aLRu2ihAeA129D5Lo";

// The Earth Engine library, read when used rather than when a module starts
// (it may load later). Reading it before it has loaded is an error that says so.
export const lazyEE = new Proxy(
  {},
  {
    get(_, prop) {
      if (globalThis.ee === undefined) throw new Error("Earth Engine is not loaded");
      return globalThis.ee[prop];
    },
  }
);

function loadScriptTag(url) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = url;
    if (url === EE_SCRIPT_URL) {
      s.integrity = EE_SCRIPT_INTEGRITY;
      s.crossOrigin = "anonymous";
    }
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("The Earth Engine library could not be loaded from " + url));
    document.head.appendChild(s);
  });
}

// createEELoader({urlParams, proxyUrl, loadScript, init}): ensure() loads the
// library and signs in once (every caller shares the one attempt), isReady(),
// error() (the described failure, or null), and whenReady(fn), which runs fn
// after a successful sign-in, in call order, or at once if already signed in.
export function createEELoader({ urlParams = {}, proxyUrl = "", loadScript = loadScriptTag, init = initEE } = {}) {
  let attempt = null;
  let ready = false;
  let failure = null;
  const queued = [];
  function ensure() {
    if (!attempt) {
      attempt = Promise.resolve()
        .then(() => (globalThis.ee === undefined || loadScript !== loadScriptTag ? loadScript(EE_SCRIPT_URL) : undefined))
        .then(() => init(urlParams, proxyUrl))
        .then(
          () => {
            ready = true;
            queued.splice(0).forEach((fn) => fn());
          },
          (e) => {
            failure = describeEEFailure(e, urlParams);
            queued.length = 0;
            throw new Error(failure);
          }
        );
    }
    return attempt;
  }
  return {
    ensure,
    isReady: () => ready,
    error: () => failure,
    whenReady(fn) {
      if (ready) fn();
      else if (!failure) queued.push(fn);
    },
  };
}
