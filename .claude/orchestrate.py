#!/usr/bin/env python3
"""
Lex Intel Multi-Agent Orchestrator

Uses Claude Agent SDK to coordinate 6+ specialized agents:
- Scout: Research across all sources
- Analyst: Deep analysis of research
- Strategist: Opportunity identification
- Synthesizer: Cross-domain synthesis + weekly guest rotation
- Executor: Actionable plan creation
- Chief: Overall coordination and daily digest
- Email: Email triage and response drafting

Usage:
    python .claude/orchestrate.py --mode daily    # Full daily cycle
    python .claude/orchestrate.py --mode weekly   # Weekly deep analysis + guest rotation
    python .claude/orchestrate.py --mode email    # Email triage only
    python .claude/orchestrate.py --mode status   # Check agent health
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Claude Agent SDK imports
# NOTE: The Agent SDK (Agent Teams) was released Feb 5, 2026. The exact API
# surface may evolve. These imports reflect the documented pattern as of
# Feb 2026. Adjust if the SDK updates its public interface.
# ---------------------------------------------------------------------------
try:
    from claude_code_sdk import query, AgentDefinition
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    logging.warning(
        "claude_code_sdk not installed. Running in dry-run mode. "
        "Install with: pip install claude-code-sdk"
    )

# ---------------------------------------------------------------------------
# Project imports — Supabase operations via lib.db
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.db import _get_client  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("orchestrator")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
AGENTS_DIR = PROJECT_ROOT / ".claude" / "agents"
GUESTS_DIR = AGENTS_DIR / "guests"

# Guest agent rotation: week-of-month -> filename
GUEST_ROTATION = {
    1: "market-analyst.md",
    2: "tech-architect.md",
    3: "growth-hacker.md",
    4: "risk-assessor.md",
}

# Core agent names — these correspond to .claude/agents/<name>.md files
# that the Chief, Scout, Analyst, etc. will be loaded from once those
# prompt files are created.
CORE_AGENTS = [
    "scout",
    "analyst",
    "strategist",
    "synthesizer",
    "executor",
    "chief",
    "email",
]


# ═══════════════════════════════════════════════════════════════════════════
# Agent Definition Loading
# ═══════════════════════════════════════════════════════════════════════════

def load_agent_prompt(name: str) -> Optional[str]:
    """Load an agent's system prompt from its markdown file.

    Looks for .claude/agents/<name>.md in the project root.
    Returns None if the file does not exist (agent not yet defined).
    """
    path = AGENTS_DIR / f"{name}.md"
    if path.exists():
        return path.read_text().strip()
    logger.warning("Agent prompt file not found: %s", path)
    return None


def load_guest_prompt() -> Optional[str]:
    """Load this week's guest agent prompt based on week-of-month.

    Week 1 = Market Analyst, Week 2 = Tech Architect,
    Week 3 = Growth Hacker, Week 4 = Risk Assessor.
    If the month has a 5th week, Week 4's guest carries over.
    """
    today = datetime.now(timezone.utc)
    # Week of month: day 1-7 = week 1, 8-14 = week 2, etc.
    week_of_month = min((today.day - 1) // 7 + 1, 4)

    guest_file = GUEST_ROTATION.get(week_of_month)
    if not guest_file:
        logger.warning("No guest rotation defined for week %d", week_of_month)
        return None

    guest_path = GUESTS_DIR / guest_file
    if guest_path.exists():
        logger.info(
            "Guest agent for week %d: %s", week_of_month, guest_file
        )
        return guest_path.read_text().strip()

    logger.warning("Guest prompt file not found: %s", guest_path)
    return None


def get_current_guest_name() -> str:
    """Return the human-readable name of the current week's guest agent."""
    today = datetime.now(timezone.utc)
    week_of_month = min((today.day - 1) // 7 + 1, 4)
    guest_file = GUEST_ROTATION.get(week_of_month, "unknown")
    return guest_file.replace(".md", "").replace("-", " ").title()


def build_agent_definitions() -> List[Dict[str, Any]]:
    """Build the list of agent definitions for the Agent SDK.

    Returns a list of dicts with 'name' and 'prompt' keys.
    Agents whose prompt files are missing are skipped with a warning.
    """
    agents = []

    for name in CORE_AGENTS:
        prompt = load_agent_prompt(name)
        if prompt:
            agents.append({"name": name, "prompt": prompt})

    # Add guest agent if available
    guest_prompt = load_guest_prompt()
    if guest_prompt:
        guest_name = get_current_guest_name()
        agents.append({
            "name": f"guest-{guest_name.lower().replace(' ', '-')}",
            "prompt": guest_prompt,
        })

    return agents


# ═══════════════════════════════════════════════════════════════════════════
# Supabase Logging — agent_runs table
# ═══════════════════════════════════════════════════════════════════════════

def log_agent_run(
    agent_name: str,
    mode: str,
    status: str = "started",
    output: Optional[str] = None,
    error: Optional[str] = None,
    duration_s: Optional[float] = None,
    metadata: Optional[Dict] = None,
) -> Optional[str]:
    """Log an agent run to the agent_runs table in Supabase.

    Returns the row ID on success, None on failure.
    """
    try:
        client = _get_client()
        row = {
            "agent_id": agent_name,
            "run_type": mode,
            "status": status,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        if error:
            row["error"] = error[:5000]
        if duration_s is not None:
            row["duration_s"] = round(duration_s, 2)
        meta = metadata or {}
        if output:
            meta["output"] = output[:50000]
        if meta:
            row["metadata"] = meta

        result = client.table("agent_runs").insert(row).execute()
        return result.data[0]["id"] if result.data else None
    except Exception as e:
        logger.error("Failed to log agent run: %s", e)
        return None


def update_agent_run(
    run_id: str,
    status: str,
    output: Optional[str] = None,
    error: Optional[str] = None,
    duration_s: Optional[float] = None,
) -> None:
    """Update an existing agent_run record with completion data."""
    try:
        client = _get_client()
        updates: Dict[str, Any] = {
            "status": status,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        if error:
            updates["error"] = error[:5000]
        if duration_s is not None:
            updates["duration_s"] = round(duration_s, 2)

        client.table("agent_runs").update(updates).eq("id", run_id).execute()
    except Exception as e:
        logger.error("Failed to update agent run %s: %s", run_id, e)


# ═══════════════════════════════════════════════════════════════════════════
# Agent Execution
# ═══════════════════════════════════════════════════════════════════════════

async def run_agent(
    name: str,
    prompt: str,
    system_prompt: str,
    mode: str,
    subagent_defs: Optional[List] = None,
) -> Dict[str, Any]:
    """Run a single agent via the Claude Agent SDK.

    Args:
        name: Human-readable agent name (for logging).
        prompt: The task prompt to send to this agent.
        system_prompt: The agent's persona/system prompt.
        mode: Run mode (daily/weekly/email/status) for logging.
        subagent_defs: Optional list of sub-agent definitions for
                       agents that coordinate other agents (e.g. Chief).

    Returns:
        Dict with 'output', 'status', 'duration_s', and 'error' keys.
    """
    start = datetime.now(timezone.utc)
    run_id = log_agent_run(agent_name=name, mode=mode, status="running")

    result = {
        "agent": name,
        "output": "",
        "status": "success",
        "error": None,
        "duration_s": 0.0,
    }

    try:
        if not SDK_AVAILABLE:
            # Dry-run mode: log what would happen
            logger.info("[DRY RUN] Would run agent '%s' with prompt: %.80s...", name, prompt)
            result["output"] = f"[DRY RUN] Agent '{name}' would execute: {prompt[:200]}"
            result["status"] = "dry_run"
        else:
            # ---------------------------------------------------------
            # TODO: Claude Agent SDK integration point
            #
            # The Agent Teams API (released Feb 5, 2026) uses this pattern:
            #
            #   agent_def = AgentDefinition(
            #       name=name,
            #       system_prompt=system_prompt,
            #   )
            #
            #   options = {
            #       "model": "opus",
            #       "permission_mode": "bypassPermissions",
            #   }
            #
            #   if subagent_defs:
            #       options["subagents"] = subagent_defs
            #
            #   collected_output = []
            #   async for event in query(
            #       prompt=prompt,
            #       options=options,
            #   ):
            #       # event may be TextEvent, ToolUseEvent, etc.
            #       # Collect text output for logging
            #       if hasattr(event, "text"):
            #           collected_output.append(event.text)
            #
            #   result["output"] = "".join(collected_output)
            #
            # As the SDK API stabilizes, replace this block with the
            # actual implementation. The surrounding logging, error
            # handling, and Supabase integration are ready to go.
            # ---------------------------------------------------------
            logger.info(
                "SDK available but integration pending — "
                "running '%s' in stub mode", name
            )
            result["output"] = f"[STUB] Agent '{name}' — SDK integration pending"
            result["status"] = "stub"

    except Exception as e:
        logger.error("Agent '%s' failed: %s", name, e, exc_info=True)
        result["status"] = "error"
        result["error"] = str(e)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    result["duration_s"] = elapsed

    # Update the agent_run record
    if run_id:
        update_agent_run(
            run_id=run_id,
            status=result["status"],
            output=result.get("output"),
            error=result.get("error"),
            duration_s=elapsed,
        )

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Run Modes
# ═══════════════════════════════════════════════════════════════════════════

async def run_daily() -> Dict[str, Any]:
    """Execute the full daily cycle.

    Pipeline: Scout -> Analyst -> Strategist -> Synthesizer (+guest) -> Executor -> Chief digest

    Each stage receives the output of the previous stage as context.
    """
    logger.info("=" * 60)
    logger.info("DAILY CYCLE — %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    logger.info("=" * 60)

    agents = build_agent_definitions()
    agent_map = {a["name"]: a["prompt"] for a in agents}
    results = []

    # Stage 1: Scout — research across all sources
    scout_prompt = agent_map.get("scout", "")
    if scout_prompt:
        scout_result = await run_agent(
            name="scout",
            prompt=(
                "Execute your daily research sweep. Check all configured sources "
                "(RSS feeds, government databases, social media, email). "
                "Return a structured summary of today's new signals."
            ),
            system_prompt=scout_prompt,
            mode="daily",
        )
        results.append(scout_result)
    else:
        scout_result = {"output": "[No scout agent configured]"}
        logger.warning("Scout agent not configured — skipping research phase")

    # Stage 2: Analyst — deep analysis of research
    analyst_prompt = agent_map.get("analyst", "")
    if analyst_prompt:
        analyst_result = await run_agent(
            name="analyst",
            prompt=(
                "Analyze today's research signals from the Scout:\n\n"
                f"{scout_result.get('output', 'No scout data')}\n\n"
                "Categorize by relevance, identify patterns, and flag high-priority items."
            ),
            system_prompt=analyst_prompt,
            mode="daily",
        )
        results.append(analyst_result)
    else:
        analyst_result = {"output": "[No analyst agent configured]"}

    # Stage 3: Strategist — opportunity identification
    strategist_prompt = agent_map.get("strategist", "")
    if strategist_prompt:
        strategist_result = await run_agent(
            name="strategist",
            prompt=(
                "Review the Analyst's assessment and identify actionable opportunities:\n\n"
                f"{analyst_result.get('output', 'No analysis data')}\n\n"
                "Focus on SDVOSB-eligible opportunities, consulting leads, and content angles."
            ),
            system_prompt=strategist_prompt,
            mode="daily",
        )
        results.append(strategist_result)
    else:
        strategist_result = {"output": "[No strategist agent configured]"}

    # Stage 4: Synthesizer + Guest Agent
    synthesizer_prompt = agent_map.get("synthesizer", "")
    guest_name = get_current_guest_name()
    guest_key = f"guest-{guest_name.lower().replace(' ', '-')}"
    guest_prompt = agent_map.get(guest_key, "")

    combined_context = (
        f"## Scout Findings\n{scout_result.get('output', 'N/A')}\n\n"
        f"## Analyst Assessment\n{analyst_result.get('output', 'N/A')}\n\n"
        f"## Strategist Opportunities\n{strategist_result.get('output', 'N/A')}"
    )

    if synthesizer_prompt:
        synth_task = (
            f"Synthesize today's intelligence from all agents:\n\n"
            f"{combined_context}\n\n"
            f"This week's guest perspective is: {guest_name}.\n"
        )
        if guest_prompt:
            synth_task += (
                f"\nIncorporate the guest agent's perspective:\n{guest_prompt[:500]}"
            )

        synth_result = await run_agent(
            name="synthesizer",
            prompt=synth_task,
            system_prompt=synthesizer_prompt,
            mode="daily",
        )
        results.append(synth_result)
    else:
        synth_result = {"output": "[No synthesizer agent configured]"}

    # Stage 5: Executor — actionable plans
    executor_prompt = agent_map.get("executor", "")
    if executor_prompt:
        executor_result = await run_agent(
            name="executor",
            prompt=(
                "Based on today's synthesis, create specific action items:\n\n"
                f"{synth_result.get('output', 'No synthesis data')}\n\n"
                "Output a prioritized task list with deadlines and owners."
            ),
            system_prompt=executor_prompt,
            mode="daily",
        )
        results.append(executor_result)
    else:
        executor_result = {"output": "[No executor agent configured]"}

    # Stage 6: Chief — daily digest
    digest = await generate_daily_digest(results)

    chief_prompt = agent_map.get("chief", "")
    if chief_prompt:
        chief_result = await run_agent(
            name="chief",
            prompt=(
                "Review today's full pipeline output and produce the daily digest:\n\n"
                f"{digest}\n\n"
                "Highlight the top 3 priorities and any items requiring immediate attention."
            ),
            system_prompt=chief_prompt,
            mode="daily",
        )
        results.append(chief_result)

    logger.info("Daily cycle complete. Ran %d agents.", len(results))
    return {
        "mode": "daily",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents_run": len(results),
        "results": results,
        "guest_agent": guest_name,
    }


async def run_weekly() -> Dict[str, Any]:
    """Execute the weekly deep analysis cycle.

    Runs on top of the daily cycle with additional depth:
    - Extended research window (7-day lookback)
    - Guest agent gets a dedicated deep-dive pass
    - Strategist produces a weekly opportunity brief
    - Chief produces a weekly summary with trend analysis
    """
    logger.info("=" * 60)
    logger.info("WEEKLY CYCLE — %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    logger.info("Guest Agent: %s", get_current_guest_name())
    logger.info("=" * 60)

    agents = build_agent_definitions()
    agent_map = {a["name"]: a["prompt"] for a in agents}
    results = []

    # Run the daily cycle first
    daily_results = await run_daily()
    results.extend(daily_results.get("results", []))

    # Guest agent deep dive
    guest_name = get_current_guest_name()
    guest_key = f"guest-{guest_name.lower().replace(' ', '-')}"
    guest_prompt = agent_map.get(guest_key, "")

    if guest_prompt:
        daily_summary = "\n\n".join(
            f"[{r.get('agent', '?')}]: {r.get('output', 'N/A')[:500]}"
            for r in results
        )
        guest_result = await run_agent(
            name=guest_key,
            prompt=(
                f"This is your weekly deep-dive as the {guest_name}. "
                f"Review the full week's intelligence and provide your specialized assessment:\n\n"
                f"{daily_summary}\n\n"
                f"Produce a comprehensive {guest_name.lower()} report for the week."
            ),
            system_prompt=guest_prompt,
            mode="weekly",
        )
        results.append(guest_result)
    else:
        logger.warning("No guest agent available for weekly deep dive")

    # Strategist weekly opportunity brief
    strategist_prompt = agent_map.get("strategist", "")
    if strategist_prompt:
        strat_weekly = await run_agent(
            name="strategist",
            prompt=(
                "Produce the weekly opportunity brief. Review the past 7 days of "
                "signals and identify the top 5 opportunities to pursue this week. "
                "Include revenue estimates and effort levels for each."
            ),
            system_prompt=strategist_prompt,
            mode="weekly",
        )
        results.append(strat_weekly)

    # Chief weekly summary
    chief_prompt = agent_map.get("chief", "")
    if chief_prompt:
        chief_weekly = await run_agent(
            name="chief",
            prompt=(
                "Produce the weekly summary. Include:\n"
                "1. Key trends from this week\n"
                "2. Top opportunities (from Strategist)\n"
                f"3. {guest_name}'s assessment highlights\n"
                "4. Action items for next week\n"
                "5. Pipeline health metrics"
            ),
            system_prompt=chief_prompt,
            mode="weekly",
        )
        results.append(chief_weekly)

    logger.info("Weekly cycle complete. Ran %d total agents.", len(results))
    return {
        "mode": "weekly",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents_run": len(results),
        "results": results,
        "guest_agent": guest_name,
    }


async def run_email() -> Dict[str, Any]:
    """Execute email triage mode.

    Runs only the Email agent to:
    - Check inbox for new messages
    - Categorize and prioritize
    - Draft responses for review
    - Flag anything requiring urgent human attention
    """
    logger.info("=" * 60)
    logger.info("EMAIL TRIAGE — %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    logger.info("=" * 60)

    agents = build_agent_definitions()
    agent_map = {a["name"]: a["prompt"] for a in agents}

    email_prompt = agent_map.get("email", "")
    if not email_prompt:
        logger.error("Email agent not configured. Create .claude/agents/email.md")
        return {
            "mode": "email",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agents_run": 0,
            "results": [],
            "error": "Email agent not configured",
        }

    email_result = await run_agent(
        name="email",
        prompt=(
            "Execute email triage:\n"
            "1. Check inbox for unread messages from the last 24 hours\n"
            "2. Categorize each: [action-required, informational, opportunity, spam]\n"
            "3. Draft responses for action-required items\n"
            "4. Flag any items matching active opportunities from the Strategist\n"
            "5. Output a structured triage report"
        ),
        system_prompt=email_prompt,
        mode="email",
    )

    return {
        "mode": "email",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents_run": 1,
        "results": [email_result],
    }


async def run_status() -> Dict[str, Any]:
    """Check agent health and system status.

    Reports on:
    - Which agent prompt files exist
    - Current guest agent rotation
    - Recent agent_run records from Supabase
    - Any errors in the last 24 hours
    """
    logger.info("=" * 60)
    logger.info("STATUS CHECK — %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    logger.info("=" * 60)

    status = {
        "mode": "status",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents": {},
        "guest_agent": get_current_guest_name(),
        "guest_agent_file_exists": False,
        "recent_runs": [],
        "errors": [],
    }

    # Check which agents have prompt files
    for name in CORE_AGENTS:
        path = AGENTS_DIR / f"{name}.md"
        status["agents"][name] = {
            "prompt_file": str(path),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }

    # Check guest agent
    today = datetime.now(timezone.utc)
    week_of_month = min((today.day - 1) // 7 + 1, 4)
    guest_file = GUEST_ROTATION.get(week_of_month, "")
    guest_path = GUESTS_DIR / guest_file
    status["guest_agent_file_exists"] = guest_path.exists()

    # Check all guest files
    status["guest_files"] = {}
    for week, filename in GUEST_ROTATION.items():
        gpath = GUESTS_DIR / filename
        status["guest_files"][f"week_{week}"] = {
            "name": filename.replace(".md", "").replace("-", " ").title(),
            "file": str(gpath),
            "exists": gpath.exists(),
        }

    # Query recent agent runs from Supabase
    try:
        client = _get_client()
        cutoff = (
            datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=24)
        ).isoformat()
        recent = (
            client.table("agent_runs")
            .select("agent_id, run_type, status, started_at, duration_s, error")
            .gte("started_at", cutoff)
            .order("started_at", desc=True)
            .limit(20)
            .execute()
        )
        status["recent_runs"] = recent.data

        # Extract errors
        status["errors"] = [
            r for r in recent.data if r.get("status") == "error"
        ]
    except Exception as e:
        logger.warning("Could not query agent_runs: %s", e)
        status["db_error"] = str(e)

    # Pretty-print status
    print("\n" + "=" * 60)
    print("LEX INTEL — AGENT STATUS")
    print("=" * 60)
    print(f"\nTimestamp: {status['timestamp']}")
    print(f"Current Guest: {status['guest_agent']}")
    print(f"Guest File Exists: {status['guest_agent_file_exists']}")
    print("\nAgent Prompt Files:")
    for name, info in status["agents"].items():
        marker = "[OK]" if info["exists"] else "[MISSING]"
        print(f"  {marker} {name:15s} — {info['prompt_file']}")

    print("\nGuest Rotation:")
    for week_key, info in status.get("guest_files", {}).items():
        marker = "[OK]" if info["exists"] else "[MISSING]"
        print(f"  {marker} {week_key}: {info['name']}")

    if status.get("recent_runs"):
        print(f"\nRecent Runs (last 24h): {len(status['recent_runs'])}")
        for run in status["recent_runs"][:5]:
            print(
                f"  {run.get('started_at', '?')[:16]} | "
                f"{run.get('agent_id', '?'):15s} | "
                f"{run.get('run_type', '?'):8s} | "
                f"{run.get('status', '?'):8s} | "
                f"{run.get('duration_s', 0):.1f}s"
            )

    if status.get("errors"):
        print(f"\nErrors (last 24h): {len(status['errors'])}")
        for err in status["errors"]:
            print(f"  [{err.get('agent_id')}] {err.get('error', 'unknown')[:100]}")

    if status.get("db_error"):
        print(f"\nDatabase Error: {status['db_error']}")

    print("\n" + "=" * 60)
    return status


# ═══════════════════════════════════════════════════════════════════════════
# Daily Digest Generation
# ═══════════════════════════════════════════════════════════════════════════

async def generate_daily_digest(results: List[Dict[str, Any]]) -> str:
    """Summarize what all agents did today into a readable digest.

    This digest is passed to the Chief agent for final review and
    can also be stored/emailed independently.

    Args:
        results: List of result dicts from each agent run.

    Returns:
        Formatted markdown digest string.
    """
    now = datetime.now(timezone.utc)
    guest_name = get_current_guest_name()

    lines = [
        f"# Lex Intel Daily Digest",
        f"**Date:** {now.strftime('%A, %B %d, %Y')}",
        f"**Guest Perspective:** {guest_name} (Week {min((now.day - 1) // 7 + 1, 4)})",
        f"**Agents Run:** {len(results)}",
        "",
    ]

    # Summary stats
    succeeded = sum(1 for r in results if r.get("status") in ("success", "stub", "dry_run"))
    failed = sum(1 for r in results if r.get("status") == "error")
    total_time = sum(r.get("duration_s", 0) for r in results)

    lines.append(f"## Pipeline Summary")
    lines.append(f"- Agents succeeded: {succeeded}/{len(results)}")
    if failed:
        lines.append(f"- Agents failed: {failed}")
    lines.append(f"- Total processing time: {total_time:.1f}s")
    lines.append("")

    # Per-agent summaries
    lines.append("## Agent Reports")
    lines.append("")

    for r in results:
        agent = r.get("agent", "unknown")
        status = r.get("status", "unknown")
        duration = r.get("duration_s", 0)
        output = r.get("output", "")
        error = r.get("error")

        status_icon = {
            "success": "PASS",
            "stub": "STUB",
            "dry_run": "DRY",
            "error": "FAIL",
        }.get(status, "????")

        lines.append(f"### [{status_icon}] {agent.title()} ({duration:.1f}s)")

        if error:
            lines.append(f"**Error:** {error}")
        elif output:
            # Truncate output for digest readability
            preview = output[:300].strip()
            if len(output) > 300:
                preview += "..."
            lines.append(preview)

        lines.append("")

    # Footer
    lines.append("---")
    lines.append(
        f"*Generated by Lex Intel Orchestrator at "
        f"{now.strftime('%H:%M UTC')}*"
    )

    digest = "\n".join(lines)

    # Persist the digest to Supabase
    try:
        log_agent_run(
            agent_name="orchestrator",
            mode="digest",
            status="success",
            output=digest,
        )
    except Exception as e:
        logger.warning("Failed to persist daily digest: %s", e)

    return digest


# ═══════════════════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Lex Intel Multi-Agent Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Run modes:
  daily    Full daily cycle: Scout -> Analyst -> Strategist -> Synthesizer -> Executor -> Chief
  weekly   Weekly deep analysis with guest agent deep dive and trend analysis
  email    Email triage only (inbox check, categorize, draft responses)
  status   Check agent health, prompt files, and recent run history

Examples:
  python .claude/orchestrate.py --mode daily
  python .claude/orchestrate.py --mode status
  python .claude/orchestrate.py --mode weekly --verbose
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["daily", "weekly", "email", "status"],
        default="status",
        help="Run mode (default: status)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug-level logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would happen without making SDK calls",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.dry_run:
        global SDK_AVAILABLE
        SDK_AVAILABLE = False
        logger.info("Dry-run mode enabled — no SDK calls will be made")

    # Dispatch to the appropriate run mode
    mode_handlers = {
        "daily": run_daily,
        "weekly": run_weekly,
        "email": run_email,
        "status": run_status,
    }

    handler = mode_handlers[args.mode]

    try:
        result = asyncio.run(handler())

        # Print summary for non-status modes (status prints its own output)
        if args.mode != "status":
            print(f"\n{'=' * 60}")
            print(f"Orchestrator complete: mode={args.mode}")
            print(f"Agents run: {result.get('agents_run', 0)}")
            if result.get("guest_agent"):
                print(f"Guest agent: {result['guest_agent']}")
            errors = [
                r for r in result.get("results", [])
                if r.get("status") == "error"
            ]
            if errors:
                print(f"Errors: {len(errors)}")
                for e in errors:
                    print(f"  [{e.get('agent')}] {e.get('error', 'unknown')}")
            print(f"{'=' * 60}")

    except KeyboardInterrupt:
        logger.info("Orchestrator interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error("Orchestrator failed: %s", e, exc_info=True)
        # Log the failure
        log_agent_run(
            agent_name="orchestrator",
            mode=args.mode,
            status="error",
            error=str(e),
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
