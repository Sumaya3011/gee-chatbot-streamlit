# change_report_utils.py
"""
Phase 2: Change-analysis report generator (website version)

This is a direct port of your Colab Phase-2 logic:
- same JSON schema
- same extract_core_facts
- same build_prompt
- same structured JSON output
- multi-region (abudhabi, germany, portugal, india, spain)

Differences:
- OUTPUTS_DIR = Path("outputs") (local folder in the repo)
- No Colab / Drive / pip install stuff
- API key taken from environment / Streamlit secrets, NOT hardcoded
- Does not save files (returns report_text + report_json to the caller)
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from openai import OpenAI

# Folder where your Phase-1 JSON files live (put them here in the repo)
OUTPUTS_DIR = Path("outputs")

# Main Abu Dhabi stats file (for backward compatibility)
CHANGE_STATS_PATH = OUTPUTS_DIR / "change_stats.json"

# Map of region -> (filename, human-readable name)
REGION_JSON_MAP: Dict[str, Tuple[str, str]] = {
    "abudhabi": ("change_stats.json", "Abu Dhabi (AOI)"),
    "germany": ("change_stats_germany_flood_2021.json", "Germany (2021 flood)"),
    "portugal": ("change_stats_portugal_flood_2022.json", "Portugal (Lisbon/Tagus flood)"),
    "india": ("change_stats_india_monsoon_flood_2023.json", "India (Himachal Pradesh monsoon)"),
    "spain": ("change_stats_spain_donana_drought_2023.json", "Spain (Doñana drought)"),
}

# Keywords used to auto-detect region from question text
REGION_KEYWORDS: Dict[str, List[str]] = {
    "abudhabi": ["abu dhabi", "abudhabi", "uae", "emirates", "dhabi"],
    "germany": ["germany", "german"],
    "portugal": ["portugal", "portuguese", "lisbon", "tagus"],
    "india": ["india", "indian", "himachal"],
    "spain": ["spain", "spanish", "donana", "doñana"],
}


def _get_openai_client() -> OpenAI:
    """
    Get OpenAI client.

    IMPORTANT:
    - Do NOT hardcode the key here.
    - Set OPENAI_API_KEY in:
      - Streamlit secrets (recommended), OR
      - environment variables.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        # if Streamlit is used, user can set secrets and pass into env in app.py
        raise ValueError("OPENAI_API_KEY environment variable is not set.")
    return OpenAI(api_key=api_key)


def get_stats_path_and_area(region_key: str) -> Tuple[Path, str]:
    """
    Return (path_to_change_stats_json, study_area_name) for a given region key.
    Region key must be one of REGION_JSON_MAP keys.
    """
    key = region_key.strip().lower()
    if key not in REGION_JSON_MAP:
        raise KeyError(
            "Unknown region. Choose from: " + str(list(REGION_JSON_MAP.keys()))
        )
    filename, area = REGION_JSON_MAP[key]
    return OUTPUTS_DIR / filename, area


def detect_region_from_question(user_question: str) -> str:
    """
    Detect which region the user is asking about from the text.
    Falls back to 'abudhabi' if no keyword is found.
    """
    q = (user_question or "").lower()
    for region, keywords in REGION_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return region
    return "abudhabi"  # default


def get_available_region_for_question(user_question: str) -> Tuple[str, Path, str]:
    """
    Detect region from the question, then:
    - If that region's JSON exists, use it.
    - Otherwise, use the first region in REGION_JSON_MAP that has a JSON file.
    Raises FileNotFoundError if none found.
    """
    region = detect_region_from_question(user_question)
    path, area = get_stats_path_and_area(region)
    if path.exists():
        return region, path, area

    # fallback: first region with an existing file
    for r in REGION_JSON_MAP:
        if r == region:
            continue
        p, a = get_stats_path_and_area(r)
        if p.exists():
            return r, p, a

    raise FileNotFoundError(
        f"No change-stats JSON found in {OUTPUTS_DIR}. "
        "Place your Phase-1 outputs there."
    )


# Dynamic World label mapping (kept for compatibility if needed later)
DW_LABEL_TO_NAME = {
    0: "Water",
    1: "Trees",
    2: "Grass",
    3: "Flooded vegetation",
    4: "Crops",
    5: "Shrub & scrub",
    6: "Built-up",
    7: "Bare ground",
    8: "Snow & ice",
}

VEG_LABELS = {1, 2, 3, 4, 5}  # vegetation-ish
BUILT_LABEL = 6


def load_change_stats(path: str | Path) -> dict:
    """
    Load Phase-1 change_stats JSON from path.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Change stats not found: {path}. Run Phase 1 for this region."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _safe_get(d: dict, key: str, default=None):
    return d[key] if key in d else default


def extract_core_facts(change_stats: dict) -> dict:
    """
    Convert Phase-1 stats into a clean "facts" bundle:
    - dates
    - key % stats
    - top transitions (top 3)
    - derived built-up gain %
    (Same logic as your notebook.)
    """
    before_date = _safe_get(change_stats, "before_date", "unknown")
    after_date = _safe_get(change_stats, "after_date", "unknown")

    overall_change_percent = float(
        _safe_get(change_stats, "overall_change_percent", 0.0)
    )
    water_gain_percent = float(_safe_get(change_stats, "water_gain_percent", 0.0))
    water_loss_percent = float(_safe_get(change_stats, "water_loss_percent", 0.0))
    vegetation_loss_percent = float(
        _safe_get(change_stats, "vegetation_loss_percent", 0.0)
    )

    transitions = _safe_get(change_stats, "top_transitions", [])
    transitions_sorted = sorted(
        transitions, key=lambda x: float(x.get("percent", 0.0)), reverse=True
    )
    top3 = transitions_sorted[:3]

    built_up_gain = 0.0
    for t in transitions:
        to_val = t.get("to")
        to_name = str(to_val).lower()
        if to_val == BUILT_LABEL or "built" in to_name:
            built_up_gain += float(t.get("percent", 0.0))

    return {
        "time_range": f"{before_date} → {after_date}",
        "before_date": before_date,
        "after_date": after_date,
        "key_stats": {
            "overall_change_percent": overall_change_percent,
            "water_gain_percent": water_gain_percent,
            "water_loss_percent": water_loss_percent,
            "vegetation_loss_percent": vegetation_loss_percent,
            "built_up_gain_percent_derived": round(built_up_gain, 4),
        },
        "top_transitions": top3,
    }


def build_prompt(user_question: str, facts: dict) -> str:
    """
    Build prompt exactly like your notebook (shortened comments only).
    """
    facts_blob = json.dumps(facts, indent=2)

    return f"""
You are an expert climate-risk analyst for satellite-based change detection. You must THINK and REASON from the data — do NOT memorize or repeat a fixed template. Tailor every part of your answer to (1) the specific USER QUESTION and (2) the actual numbers and transitions in FACTS. Different questions should get different emphasis and phrasing.

RULES:
1) Use ONLY the provided FACTS for numbers, dates, and transitions. Do NOT invent figures.
2) If FACTS has no spatial locations, do NOT invent places; say spatial hotspots are not available.
3) Temperature is NOT available; state that heatwave hazard is INFERRED / qualitative.

FACTS (from Phase 1):
{facts_blob}

USER QUESTION:
{user_question}

---
Output a report in report_text (markdown) and fill report_json to match. Structure:

A) Change Detection
- Step 1: Land-Cover Classification (Dynamic World)
- Step 2: Pixel-by-Pixel Comparison
- Step 3: Statistics (overall_change_percent, water_gain_percent, water_loss_percent, vegetation_loss_percent)
- Natural-language summary: what changed, where, how much — using top_transitions and key_stats. Be specific to THIS data.

B) Risk Analysis (Heatwave)
1) Hazard: Infer from built-up increase and vegetation loss. State clearly: no temperature data — hazard is inferred.
2) Exposure: Describe risk zones (Low/Medium/High) and where changes likely occur (from transitions).
3) Vulnerability: Built-up = high vulnerability; vegetation/water = low vulnerability.
4) Risk Scoring: Risk = Hazard × Exposure × Vulnerability. Give risk_level (low/medium/high) and justification using the stats.

RECOMMENDATION RULE (severity-based): Based on the risk_level you assigned above, EMPHASIZE the appropriate recommendation type: if risk_level is high → lead with and expand Avoidance; if medium → Mitigation; if low → Monitoring. Still output all three subsections but tailor content and emphasis to severity.

C) Recommendations (Decision Support)
Format this section EXACTLY as follows in report_text (and mirror in report_json). Use the heading "C) Recommendations" only (not "GPT Recommendations").

First, an intro paragraph:
"Based on the detected land-cover transitions and associated risk analysis, it is recommended to:"

Then 3–5 bullet points (examples): limit dense urban development in high-risk expansion zones; increase urban green infrastructure to mitigate heat accumulation; continuously monitor land-cover changes using satellite imagery to identify emerging risk hotspots. Tailor these to the actual transitions and risk level.

Then three numbered subsections:

1) Avoidance Recommendations
   Used when risk is high and persistent.
   Give concrete, data-informed examples, e.g.: "This area should be avoided for future urban expansion due to persistent high heat-risk scores caused by dense built-up land cover." Adapt to the actual stats and transitions.

2) Mitigation Recommendations
   Used when risk is manageable.
   Give concrete examples, e.g.: "Increase vegetation cover to enhance evapotranspiration and reduce surface heat accumulation." Tailor to the observed changes.

3) Monitoring Recommendations
   Used when risk is emerging (or always).
   Give concrete examples, e.g.: "Continuous satellite monitoring is recommended to detect early changes before risk becomes critical." Tie to the study period and top transitions.

Put "Suggested questions" only at the very end of report_text (after C) Recommendations), not in the middle of sections.
Include suggested_questions (3–6 items) relevant to this report.
Return JSON only, matching the schema.
""".strip()


# JSON schema (copied from notebook)
REPORT_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "report_text": {"type": "string"},
        "report_json": {
            "type": "object",
            "properties": {
                "change_detection": {
                    "type": "object",
                    "properties": {
                        "time_range": {"type": "string"},
                        "study_area": {"type": "string"},
                        "headline_summary": {"type": "string"},
                        "observed_changes": {"type": "array", "items": {"type": "string"}},
                        "key_stats": {
                            "type": "object",
                            "properties": {
                                "overall_change_percent": {"type": "number"},
                                "water_gain_percent": {"type": "number"},
                                "water_loss_percent": {"type": "number"},
                                "vegetation_loss_percent": {"type": "number"},
                            },
                            "required": [
                                "overall_change_percent",
                                "water_gain_percent",
                                "water_loss_percent",
                                "vegetation_loss_percent",
                            ],
                            "additionalProperties": False,
                        },
                        "top_transitions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "from": {"type": "string"},
                                    "to": {"type": "string"},
                                    "percent": {"type": "number"},
                                    "count": {"type": "number"},
                                },
                                "required": ["from", "to", "percent", "count"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": [
                        "time_range",
                        "study_area",
                        "headline_summary",
                        "observed_changes",
                        "key_stats",
                        "top_transitions",
                    ],
                    "additionalProperties": False,
                },
                "risk_analysis": {
                    "type": "object",
                    "properties": {
                        "hazard": {
                            "type": "object",
                            "properties": {
                                "statement": {"type": "string"},
                                "evidence": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["statement", "evidence"],
                            "additionalProperties": False,
                        },
                        "exposure": {
                            "type": "object",
                            "properties": {
                                "statement": {"type": "string"},
                                "risk_zones": {
                                    "type": "object",
                                    "properties": {
                                        "low": {"type": "string"},
                                        "medium": {"type": "string"},
                                        "high": {"type": "string"},
                                    },
                                    "required": ["low", "medium", "high"],
                                    "additionalProperties": False,
                                },
                            },
                            "required": ["statement", "risk_zones"],
                            "additionalProperties": False,
                        },
                        "vulnerability": {
                            "type": "object",
                            "properties": {
                                "statement": {"type": "string"},
                                "high_vulnerability_classes": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "low_vulnerability_classes": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": [
                                "statement",
                                "high_vulnerability_classes",
                                "low_vulnerability_classes",
                            ],
                            "additionalProperties": False,
                        },
                        "risk_scoring": {
                            "type": "object",
                            "properties": {
                                "formula": {"type": "string"},
                                "risk_level": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high"],
                                },
                                "justification": {"type": "string"},
                            },
                            "required": ["formula", "risk_level", "justification"],
                            "additionalProperties": False,
                        },
                    },
                    "required": ["hazard", "exposure", "vulnerability", "risk_scoring"],
                    "additionalProperties": False,
                },
                "recommendations": {
                    "type": "object",
                    "properties": {
                        "recommendations_intro": {"type": "string"},
                        "recommendations_bullets": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "avoidance": {"type": "array", "items": {"type": "string"}},
                        "mitigation": {"type": "array", "items": {"type": "string"}},
                        "monitoring": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "recommendations_intro",
                        "recommendations_bullets",
                        "avoidance",
                        "mitigation",
                        "monitoring",
                    ],
                    "additionalProperties": False,
                },
                "suggested_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "change_detection",
                "risk_analysis",
                "recommendations",
                "suggested_questions",
            ],
            "additionalProperties": False,
        },
    },
    "required": ["report_text", "report_json"],
    "additionalProperties": False,
}


def run_change_report(user_question: str, region: str | None = None) -> Dict[str, Any]:
    """
    Main function you will call from app.py.

    Returns:
    {
      "report_text": str,
      "report_json": {...},  # matches REPORT_JSON_SCHEMA
      "region": "abudhabi" | "germany" | ...
    }
    """
    client = _get_openai_client()

    if region is None:
        region_key, stats_path, study_area = get_available_region_for_question(
            user_question
        )
    else:
        region_key = region
        stats_path, study_area = get_stats_path_and_area(region)

    change_stats = load_change_stats(stats_path)
    facts = extract_core_facts(change_stats)
    prompt = build_prompt(user_question, facts)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "chatbot_report",
                "strict": True,
                "schema": REPORT_JSON_SCHEMA,
            },
        },
    )

    parsed = json.loads(response.choices[0].message.content)

    # Force correct time_range + study_area + key_stats + transitions from our facts
    parsed["report_json"]["change_detection"]["time_range"] = facts["time_range"]
    parsed["report_json"]["change_detection"]["study_area"] = study_area
    parsed["report_json"]["change_detection"]["key_stats"] = {
        "overall_change_percent": facts["key_stats"]["overall_change_percent"],
        "water_gain_percent": facts["key_stats"]["water_gain_percent"],
        "water_loss_percent": facts["key_stats"]["water_loss_percent"],
        "vegetation_loss_percent": facts["key_stats"]["vegetation_loss_percent"],
    }
    parsed["report_json"]["change_detection"]["top_transitions"] = facts["top_transitions"]

    return {
        "report_text": parsed["report_text"],
        "report_json": parsed["report_json"],
        "region": region_key,
    }
