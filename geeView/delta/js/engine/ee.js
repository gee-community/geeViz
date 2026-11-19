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
