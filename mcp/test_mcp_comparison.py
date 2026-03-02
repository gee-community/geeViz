"""
Three-way comparison: Gemini with no tools vs Google Search vs MCP server.

  Run 1: Bare Gemini -- no tools, pure LLM generation from training data
  Run 2: Google Search -- Gemini with built-in Google Search grounding
  Run 3: MCP Server -- Gemini with live geeViz MCP tools (real server subprocess)

Run:
  set GOOGLE_API_KEY=your-key-here
  cd C:\RCR\geeVizBuilder
  python -m geeViz.mcp.test_mcp_comparison

Requires:  pip install google-genai mcp dotenv
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_GEEVIZ_DIR = os.path.dirname(_THIS_DIR)
_PACKAGE_ROOT = os.path.dirname(_GEEVIZ_DIR)
if _PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, _PACKAGE_ROOT)

from google import genai
from google.genai import types as gtypes

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
import dotenv
dotenv.load_dotenv()    
API_KEY = os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    sys.exit("Error: GOOGLE_API_KEY not found in .env file.")
print(f"API_KEY: {API_KEY}")
PROMPT = (
    "Write a full workflow using s2 data with multi-year change detection near yellowstone from 2018 to 2025."
)

MAX_TOOL_ROUNDS = 15
RESULT_TRUNCATE = 30_000  # max chars per tool result sent to Gemini

gemini = genai.Client(api_key=API_KEY)


# ---------------------------------------------------------------------------
# MCP schema -> Gemini FunctionDeclaration conversion
# ---------------------------------------------------------------------------
_JSON_TO_GEMINI_TYPE = {
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
}


def _schema_to_gemini(json_schema: dict) -> gtypes.Schema:
    """Convert a JSON Schema dict (from MCP tool.inputSchema) to a Gemini Schema."""
    gtype = _JSON_TO_GEMINI_TYPE.get(json_schema.get("type", "string"), "STRING")
    props = {}
    for pname, pschema in json_schema.get("properties", {}).items():
        props[pname] = gtypes.Schema(
            type=_JSON_TO_GEMINI_TYPE.get(pschema.get("type", "string"), "STRING"),
            description=pschema.get("description", ""),
        )
    required = json_schema.get("required", [])
    return gtypes.Schema(type=gtype, properties=props, required=required or None)


def _mcp_tools_to_gemini(mcp_tools) -> gtypes.Tool:
    """Convert a list of MCP Tool objects to a single Gemini Tool with FunctionDeclarations."""
    decls = []
    for tool in mcp_tools:
        schema = _schema_to_gemini(tool.inputSchema) if tool.inputSchema else None
        decls.append(gtypes.FunctionDeclaration(
            name=tool.name,
            description=tool.description or "",
            parameters=schema,
        ))
    return gtypes.Tool(function_declarations=decls)


# ---------------------------------------------------------------------------
# Run 1: bare (no tools)
# ---------------------------------------------------------------------------
def run_bare() -> str:
    print("=" * 70)
    print("RUN 1: NO TOOLS (bare Gemini)")
    print("=" * 70, flush=True)

    resp = gemini.models.generate_content(model=MODEL, contents=PROMPT)
    text = resp.text or "(empty response)"
    print(text)
    return text


# ---------------------------------------------------------------------------
# Run 2: Google Search grounding
# ---------------------------------------------------------------------------
def run_with_search() -> str:
    print("=" * 70)
    print("RUN 2: GOOGLE SEARCH GROUNDING")
    print("=" * 70, flush=True)

    search_tool = gtypes.Tool(google_search=gtypes.GoogleSearch())
    resp = gemini.models.generate_content(
        model=MODEL,
        contents=PROMPT,
        config=gtypes.GenerateContentConfig(tools=[search_tool]),
    )
    text = resp.text or "(empty response)"

    # Show which URLs Gemini grounded on, if available
    grounding = getattr(resp.candidates[0], "grounding_metadata", None)
    if grounding:
        chunks = getattr(grounding, "grounding_chunks", None) or []
        if chunks:
            print("  Grounding sources:")
            for chunk in chunks[:10]:
                web = getattr(chunk, "web", None)
                if web:
                    print(f"    - {getattr(web, 'title', '?')}: {getattr(web, 'uri', '?')}")
            print()

    print(text)
    return text


# ---------------------------------------------------------------------------
# Run 3: with live MCP server
# ---------------------------------------------------------------------------
async def run_with_mcp_server() -> str:
    print("=" * 70)
    print("RUN 3: WITH MCP SERVER")
    print("=" * 70, flush=True)

    server_params = StdioServerParameters(
        command=sys.executable,  # same Python that's running this script
        args=["-m", "geeViz.mcp.server"],
        cwd=_PACKAGE_ROOT,
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("  MCP server connected and initialized.")

            # Discover tools
            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            print(f"  Available tools: {tool_names}")

            # Convert to Gemini declarations
            gemini_tools = _mcp_tools_to_gemini(tools_result.tools)

            # Conversation loop
            history: list[gtypes.Content] = [
                gtypes.Content(role="user", parts=[gtypes.Part(text=PROMPT)])
            ]

            for round_num in range(1, MAX_TOOL_ROUNDS + 1):
                resp = gemini.models.generate_content(
                    model=MODEL,
                    contents=history,
                    config=gtypes.GenerateContentConfig(tools=[gemini_tools]),
                )

                # Check for function calls
                fn_calls = [
                    p for p in (resp.candidates[0].content.parts or [])
                    if p.function_call
                ]

                if not fn_calls:
                    text = resp.text or "(empty response)"
                    print(text)
                    return text

                # Append the model's turn
                history.append(resp.candidates[0].content)

                # Execute each tool call through the MCP server
                response_parts = []
                for part in fn_calls:
                    fc = part.function_call
                    fn_name = fc.name
                    fn_args = dict(fc.args) if fc.args else {}

                    print(f"  [round {round_num}] tool: {fn_name}({_short_args(fn_args)})")

                    try:
                        mcp_result = await session.call_tool(
                            name=fn_name, arguments=fn_args
                        )
                        # Extract text from MCP result
                        result_str = "\n".join(
                            c.text for c in mcp_result.content
                            if hasattr(c, "text")
                        )
                        if mcp_result.isError:
                            result_str = json.dumps({"error": result_str})
                    except Exception as exc:
                        result_str = json.dumps({"error": str(exc)})

                    # Truncate so we don't blow Gemini's context
                    if len(result_str) > RESULT_TRUNCATE:
                        result_str = result_str[:RESULT_TRUNCATE] + "\n...(truncated)"

                    response_parts.append(
                        gtypes.Part(function_response=gtypes.FunctionResponse(
                            name=fn_name, response={"result": result_str}
                        ))
                    )

                history.append(gtypes.Content(role="user", parts=response_parts))

            print("  (hit max tool rounds)")
            return "(max rounds reached)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _short_args(args: dict, maxlen: int = 100) -> str:
    s = ", ".join(f"{k}={repr(v)[:60]}" for k, v in args.items())
    return s[:maxlen] + ("..." if len(s) > maxlen else "")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def async_main():
    bare_output = run_bare()
    print("\n")
    search_output = run_with_search()
    print("\n")
    mcp_output = await run_with_mcp_server()

    print("\n" + "=" * 70)
    print("COMPARISON")
    print("=" * 70)
    print(f"  Run 1 (bare):          {len(bare_output):,} chars")
    print(f"  Run 2 (Google Search): {len(search_output):,} chars")
    print(f"  Run 3 (MCP server):    {len(mcp_output):,} chars")


if __name__ == "__main__":
    asyncio.run(async_main())
