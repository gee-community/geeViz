# Justification for Enabling Model Context Protocol (MCP) Server Access in VS Code GitHub Copilot

**Requested By:** Ian Housman, Geospatial Office (GO)
**Date:** March 2026

---

## 1. What is MCP?

The Model Context Protocol (MCP) is an open standard that allows AI coding assistants (such as GitHub Copilot) to interact with *locally running* tool servers. An MCP server runs as a subprocess on the developer's own machine and exposes project-specific tools — such as code execution, API lookups, and dataset inspection — to the AI assistant via a structured JSON-RPC interface over standard input/output (stdio).

MCP is not a cloud service, a browser extension, or a network daemon. It is a communication protocol between two processes already running on the developer's workstation.

## 2. The geeViz MCP Server

geeViz is a USFS-developed Python package for Google Earth Engine (GEE) geospatial analysis, maintained by the Geospatial Office (GO). The geeViz MCP server provides tools that allow an AI assistant to:

- **Look up function signatures and documentation** from the 16,000+ line geeViz codebase instead of generating incorrect API calls from stale training data
- **Execute and test code** in a persistent Python REPL before presenting it to the developer, catching errors before the developer ever sees them
- **Inspect GEE datasets** (bands, date ranges, projections) in real time rather than relying on outdated information
- **Search the USFS Enterprise Data Warehouse (EDW)** for authoritative Forest Service geospatial data across 215+ services
- **Generate thumbnails, charts, and reports** from Earth Engine data for rapid analysis and dissemination

## 3. Efficiency Gains

| Without MCP | With MCP |
|---|---|
| AI guesses function signatures from training data, producing frequent errors that require manual correction cycles | AI looks up actual current signatures and produces correct code on first attempt |
| Developer manually searches 40+ example scripts and cross-references documentation to find relevant patterns | AI searches and retrieves examples programmatically in seconds |
| AI cannot test code — developer is the first person to discover bugs, often after multiple round-trips | AI executes and validates code in an isolated REPL before presenting it, delivering working solutions |
| Developer must manually navigate ArcGIS REST service directories to inspect GEE asset metadata (bands, dates, CRS) | AI inspects assets directly and incorporates real metadata into generated code |
| Writing EDW spatial queries requires navigating complex service endpoints, understanding field schemas, and constructing SQL filters manually | AI searches 215+ EDW services by keyword, inspects layer schemas, and constructs properly formatted queries |
| Onboarding new analysts to geeViz and GEE requires weeks of training on API patterns and conventions | AI with MCP acts as an always-available expert on the codebase, dramatically reducing the learning curve |

In practice, this reduces the iteration cycle for geospatial analysis tasks from hours to minutes. Tasks that previously required deep familiarity with both the GEE API and geeViz internals can now be accomplished by analysts with less specialized knowledge, broadening the workforce capable of producing geospatial products for the Forest Service.

## 4. Security Considerations

### 4.1 Network Architecture — No New Attack Surface

The MCP server communicates exclusively via **stdio** (standard input/output streams) with the parent VS Code process. It does **not**:

- Open any network ports or listening sockets
- Accept inbound connections from any source
- Create HTTP/HTTPS endpoints
- Establish WebSocket or other persistent network connections

The communication path is: `VS Code (GitHub Copilot) → stdio pipe → local Python subprocess`. This is the same mechanism VS Code already uses for language servers (Python, TypeScript, etc.) and terminal processes. No firewall rules, proxy configurations, or network policy changes are required.

### 4.2 Authentication — No New Credentials

The MCP server uses the developer's **existing** Google Earth Engine authentication, which is already present on the workstation from normal GEE development workflows. It does **not**:

- Store, cache, or transmit authentication tokens
- Create new OAuth flows or authentication endpoints
- Require any additional API keys, service accounts, or secrets
- Access any systems the developer cannot already access from their terminal

If the developer can run `python -c "import ee; ee.Initialize()"` from their command line, the MCP server has exactly the same access — nothing more.

### 4.3 Code Auditability

The geeViz MCP server is:

- **Open source** under the Apache 2.0 license: [github.com/gee-community/geeViz](https://github.com/gee-community/geeViz)
- **Maintained by USFS staff** within the Geospatial Office
- **Reviewed through standard version control** (git) with full commit history
- **~800 lines of Python** — small enough for complete manual audit

The server source code (`mcp/server.py`) can be reviewed by IT security staff at any time. There are no compiled binaries, obfuscated code, or third-party dependencies beyond the standard Python ecosystem (Pillow, NumPy, Pandas) that are already approved for use.

### 4.4 Sandboxing Capabilities

The MCP server supports a `--sandbox` mode that restricts code execution by blocking:

- `open()` — no arbitrary file system reads/writes
- `os` and `sys` module access — no system-level operations
- `eval()` and `exec()` — no dynamic code execution outside the controlled REPL
- `subprocess` — no shell command execution

Even in the default unsandboxed mode (appropriate for local development), all code execution occurs within a single Python process with the developer's standard user permissions. The server cannot escalate privileges.

### 4.5 Data Flow — What Goes Where

| Data | Direction | Destination |
|---|---|---|
| Function signatures, docstrings | Server → VS Code | Local only (displayed in editor) |
| Code execution results | Server → VS Code | Local only |
| GEE API calls (getInfo, export) | Server → Google Earth Engine | Same as normal GEE development |
| EDW queries | Server → USFS ArcGIS REST services | Same as browser-based EDW access |
| Generated files (charts, thumbnails) | Server → local filesystem | `geeViz/mcp/generated_outputs/` directory |

No data is sent to any new third-party services. The AI assistant (GitHub Copilot) communicates with its own cloud backend as it already does — MCP does not change or intercept that communication. The MCP server only provides *local context* to the assistant.

### 4.6 Comparison to Already-Approved Tools

| Capability | VS Code Terminal (approved) | MCP Server (requested) |
|---|---|---|
| Run Python code | Yes | Yes (same Python interpreter) |
| Access GEE API | Yes | Yes (same credentials) |
| Read/write local files | Yes (unrestricted) | Yes (sandboxable) |
| Open network connections | Yes (unrestricted) | No (stdio only) |
| Run arbitrary shell commands | Yes | No (Python REPL only) |

The MCP server is actually **more restricted** than the VS Code integrated terminal that developers already use daily. It cannot run shell commands, does not open network ports, and can be sandboxed to prevent file system access.

## 5. Comparison to Current State

The AI assistant (GitHub Copilot) is already approved and running in VS Code. Without MCP, it operates "blind" — generating code based solely on training data, which is frequently outdated or incorrect for specialized libraries like geeViz and for rapidly evolving GEE datasets. Enabling MCP does not grant the AI any new system access; it simply allows it to *read documentation and test code* before presenting results.

Disabling MCP is analogous to requiring a developer to write code without access to documentation, a REPL, or a debugger — they can still produce output, but the error rate and time cost are significantly higher, and the organization bears the cost of those inefficiencies.

## 6. Recommendation

Enable the **"Chat > MCP: Access"** setting to `allowedTools` (restricted to specific approved servers) rather than `none`. This permits the geeViz MCP server — a locally-running, open-source, USFS-maintained tool — to function while maintaining full organizational control over which MCP servers are permitted.

Alternatively, the setting can be configured to allow only specific named servers via VS Code's `settings.json`:

```json
{
  "chat.mcp.access": "allowedTools",
  "chat.mcp.allowedServers": ["geeViz"]
}
```

This ensures that only the approved geeViz MCP server can be used, with no ability for developers to connect arbitrary third-party MCP servers.
