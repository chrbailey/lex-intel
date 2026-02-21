TITLE:
[Project] Built an MCP server that adds pre-execution governance to AI agent tool calls — intercepts before agents act, not after

BODY:
I've been building PromptSpeak, an MCP server that validates agent tool calls *before* they execute. The problem it solves: agents make tool calls (file writes, API calls, shell commands) and current approaches are either "allow everything" or "deny everything." There's no middle ground where you validate the action, check for behavioral drift, and maintain an audit trail.

**What it does:**
- 8-stage validation pipeline (syntax → semantics → permissions → drift detection → circuit breaker → interceptor → audit → execute)
- Hold queue for risky-but-not-blocked operations (human approves/rejects before execution)
- Behavioral drift detection — flags when an agent starts acting outside its established patterns
- Full audit trail of every tool call decision

**Stack:** TypeScript, 41 MCP tools, 563 tests, MIT licensed.

**Why MCP:** Any agent framework that supports MCP can plug this in. The governance layer sits between the agent and its tools — the agent calls PromptSpeak's `ps_execute_dry_run` before executing risky actions, and gets back allowed/blocked/held.

GitHub: github.com/chrbailey/promptspeak-mcp-server

Interested in feedback from anyone building multi-agent systems or worried about agent safety in production.
