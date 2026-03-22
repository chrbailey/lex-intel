import { createClient } from "jsr:@supabase/supabase-js@2";
import { TOOL_DEFINITIONS, handleToolCall } from "./tools.ts";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, content-type, x-client-info, apikey",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function jsonRpc(
  id: string | number | null,
  result: unknown,
  error: { code: number; message: string } | null,
): Response {
  const body: Record<string, unknown> = { jsonrpc: "2.0" };
  if (id !== null && id !== undefined) body.id = id;
  if (error) body.error = error;
  else body.result = result;
  return new Response(JSON.stringify(body), {
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req) => {
  // CORS preflight
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: CORS_HEADERS });
  }

  if (req.method !== "POST") {
    return new Response("Method not allowed", {
      status: 405,
      headers: CORS_HEADERS,
    });
  }

  // Auth: bearer token or ?key= query param
  const apiKey = Deno.env.get("KNOWLEDGE_API_KEY");
  if (apiKey) {
    const url = new URL(req.url);
    const authHeader = req.headers.get("authorization");
    const provided =
      (authHeader?.toLowerCase().startsWith("bearer ")
        ? authHeader.slice(7)
        : null) ||
      url.searchParams.get("key");
    if (provided !== apiKey) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
      });
    }
  }

  // Supabase client (service role for full DB access)
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return jsonRpc(null, null, { code: -32700, message: "Parse error" });
  }

  const { method, params, id } = body as {
    method: string;
    params?: Record<string, unknown>;
    id?: string | number;
  };

  switch (method) {
    case "initialize":
      return jsonRpc(id ?? null, {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: "knowledge-mcp", version: "1.0.0" },
      }, null);

    case "notifications/initialized":
      return new Response(null, { status: 204, headers: CORS_HEADERS });

    case "tools/list":
      return jsonRpc(id ?? null, { tools: TOOL_DEFINITIONS }, null);

    case "tools/call": {
      const toolParams = params as {
        name: string;
        arguments?: Record<string, unknown>;
      };
      try {
        const result = await handleToolCall(
          supabase,
          toolParams.name,
          toolParams.arguments ?? {},
        );
        return jsonRpc(id ?? null, result, null);
      } catch (err) {
        return jsonRpc(id ?? null, null, {
          code: -32603,
          message: err instanceof Error ? err.message : "Internal error",
        });
      }
    }

    case "ping":
      return jsonRpc(id ?? null, {}, null);

    default:
      return jsonRpc(id ?? null, null, {
        code: -32601,
        message: `Unknown method: ${method}`,
      });
  }
});
