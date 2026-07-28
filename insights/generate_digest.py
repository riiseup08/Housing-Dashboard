"""
Generate the monthly housing insight digest.

Pipeline:
  1. Connect to DuckDB and pull KPI bundles via `insights.queries`.
  2. Verify freshness via `quality.check_freshness` (skip publishing if stale).
  3. Ask DeepSeek to write 3 short newsletter sections from the raw stats.
  4. Render `insights/email_template.html` with the data + narrative.
  5. Write `data/insights/latest.json` and `data/insights/YYYY-MM.json`.

The n8n workflow only reads the JSON; it doesn't need to call any of this.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import DB_PATH, PROJECT_ROOT
from insights import queries
from quality import check_freshness

logger = logging.getLogger("insights")

INSIGHTS_DIR = PROJECT_ROOT / "data" / "insights"
TEMPLATE_DIR = PROJECT_ROOT / "insights"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


# ── Narrative ──────────────────────────────────────────────────
NARRATIVE_PROMPT = """You are writing the body of a short monthly newsletter on the Canadian housing market for a single retail reader. Tone: analytical, plain English, no hype, no jargon left unexplained, no bullet lists.

Write exactly three sections. For each, return ONE short paragraph (2–4 sentences). The titles must be exactly:
1. "What moved"
2. "Affordability lens"
3. "What to watch next"

Use only the numbers below — don't invent figures. If a number is missing, work around it instead of guessing.

Stats:
{stats_json}

Return JSON with this exact shape:
{{"sections": [{{"title": "What moved", "body": "..."}}, {{"title": "Affordability lens", "body": "..."}}, {{"title": "What to watch next", "body": "..."}}]}}
"""


def _llm_narrative(stats: dict) -> list[dict]:
    """Call DeepSeek to produce three short newsletter sections. Falls back to a
    templated narrative if no API key is set (so local dev / CI without a
    secret still produces a valid digest)."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY not set — using templated narrative fallback")
        return _fallback_narrative(stats)

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai SDK not installed — using templated narrative fallback")
        return _fallback_narrative(stats)

    try:
        client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            max_tokens=900,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": NARRATIVE_PROMPT.format(
                        stats_json=json.dumps(stats, indent=2)
                    ),
                }
            ],
        )
        parsed = json.loads(resp.choices[0].message.content)
        return parsed["sections"]
    except Exception as exc:
        logger.warning(
            "DeepSeek narrative generation failed (%s) — using templated fallback",
            exc,
        )
        return _fallback_narrative(stats)


def _fallback_narrative(stats: dict) -> list[dict]:
    """Deterministic narrative built from the stats — used when Claude is unavailable."""
    h = stats["headline"]
    movers = stats["cma_movers"]
    rc = stats["rate_context"]
    st = stats["starts_trend"]

    nhpi_yoy = h["nhpi"]["yoy_pct"]
    rate = h["boc_rate"]["overnight_target_pct"]
    chg_30 = rc.get("change_30d_bps")
    top = movers["top"][0] if movers["top"] else None
    bot = movers["bottom"][0] if movers["bottom"] else None
    starts_yoy = st.get("yoy_pct")

    moved = (
        f"The national NHPI is up {nhpi_yoy:+.1f}% year-over-year as of {h['nhpi']['as_of']}. "
        + (f"{top['geo']} led gains at {top['yoy_pct']:+.1f}%, while {bot['geo']} lagged at {bot['yoy_pct']:+.1f}%."
           if top and bot else "")
    )
    affordability = (
        f"Bank of Canada's overnight target sits at {rate:.2f}%"
        + (f", a {chg_30:+d} bp move over the trailing 30 days." if chg_30 is not None else ".")
        + " Rate direction continues to anchor mortgage carrying costs and, by extension, affordability for new buyers."
    )
    watch = (
        f"Housing starts (12-month rolling) are {starts_yoy:+.1f}% vs. a year ago"
        if starts_yoy is not None
        else "Housing-starts momentum bears watching"
    ) + ". Track whether supply matches population growth — that gap remains the structural driver."

    return [
        {"title": "What moved", "body": moved},
        {"title": "Affordability lens", "body": affordability},
        {"title": "What to watch next", "body": watch},
    ]


# ── Formatting helpers ─────────────────────────────────────────
def _format_kpis(stats: dict) -> dict:
    """Pre-format numbers into strings the template can drop in directly."""
    h = stats["headline"]
    nhpi_yoy = h["nhpi"]["yoy_pct"]
    starts_12m = h["housing_starts_12m_total"]
    starts_yoy = stats["starts_trend"].get("yoy_pct")
    chg_30 = stats["rate_context"].get("change_30d_bps")
    rate = h["boc_rate"]["overnight_target_pct"]
    nhpi_idx = h["nhpi"]["index"]

    return {
        "nhpi_index": f"{nhpi_idx:.1f}" if nhpi_idx is not None else "—",
        "nhpi_yoy_str": f"{nhpi_yoy:+.1f}%" if nhpi_yoy is not None else "—",
        "nhpi_yoy_color": "#1b7a3f" if (nhpi_yoy or 0) >= 0 else "#a8232a",
        "boc_rate_str": f"{rate:.2f}%" if rate is not None else "—",
        "boc_30d_str": f"{chg_30:+d} bps" if chg_30 is not None else "no change",
        "starts_12m_str": f"{starts_12m:,}" if starts_12m is not None else "—",
        "starts_yoy_str": f"{starts_yoy:+.1f}%" if starts_yoy is not None else "—",
    }


def _render_html(stats: dict, narrative: list[dict], subject: str, generated_at: datetime) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    tpl = env.get_template("email_template.html")
    return tpl.render(
        subject=subject,
        month_long=generated_at.strftime("%B %Y"),
        generated_at_short=generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        kpis=_format_kpis(stats),
        narrative_sections=narrative,
        cma_top=stats["cma_movers"]["top"],
        cma_bottom=stats["cma_movers"]["bottom"],
    )


# ── Main ───────────────────────────────────────────────────────
def generate(preview: bool = False, strict: bool = False) -> Path:
    """Build the digest. Returns the path to `latest.json`."""
    INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)

    if not Path(DB_PATH).exists():
        raise FileNotFoundError(
            f"DuckDB file not found at {DB_PATH}. Run `python run_pipeline.py --load-db` first."
        )

    logger.info("Connecting to %s", DB_PATH)
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        freshness_errors = check_freshness(conn)
        if freshness_errors:
            for e in freshness_errors:
                logger.warning("Freshness: %s", e)
            if strict:
                raise RuntimeError("Refusing to publish digest with stale data (strict mode)")

        stats = queries.collect_all(conn)
    finally:
        conn.close()

    generated_at = datetime.now(timezone.utc)
    month = generated_at.strftime("%Y-%m")
    subject = f"Canadian Housing Monthly — {generated_at.strftime('%B %Y')}"

    logger.info("Generating narrative via %s", DEEPSEEK_MODEL)
    narrative = _llm_narrative(stats)

    html = _render_html(stats, narrative, subject, generated_at)

    payload = {
        "month": month,
        "generated_at": generated_at.isoformat(),
        "subject": subject,
        "stats": stats,
        "narrative": narrative,
        "html": html,
    }

    latest = INSIGHTS_DIR / "latest.json"
    archive = INSIGHTS_DIR / f"{month}.json"
    latest.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    archive.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.info("Wrote %s and %s", latest.name, archive.name)

    if preview:
        preview_path = INSIGHTS_DIR / "preview.html"
        preview_path.write_text(html, encoding="utf-8")
        logger.info("Opening preview: %s", preview_path)
        webbrowser.open(preview_path.as_uri())

    return latest


def _cli() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Generate monthly housing insight digest")
    parser.add_argument("--preview", action="store_true", help="Open the rendered HTML in a browser")
    parser.add_argument("--strict", action="store_true", help="Fail if data freshness checks return errors")
    args = parser.parse_args()
    try:
        path = generate(preview=args.preview, strict=args.strict)
        print(f"\nDigest written to {path}")
    except Exception as e:
        logger.error("Digest generation failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    _cli()
