// Delta entry point. Boots the store, the UI shell and the Map API.
// Until the real engine lands, every run (including ?delta-test=shell) uses a
// stub engine with no Google Maps or Earth Engine, so tests drive the shell
// through window.__delta.store.
import { createStore } from "./state.js";
import { createMapApi } from "./api.js";
import { mountShell, initialShellState } from "./ui/shell.js";
import { mountStatus } from "./ui/status.js";

const store = createStore();
store.set(initialShellState(store), "boot");

const shell = mountShell(store, { mapEl: document.getElementById("map") });
const status = mountStatus(store, document.getElementById("status"), document.getElementById("loadbar"));

// The stub engine has no hooks: every engine call is ignored. The real engine
// replaces it in a later task.
const engine = {};
const api = createMapApi(store, engine);

window.__delta = { store, api, engine, shell, status };
