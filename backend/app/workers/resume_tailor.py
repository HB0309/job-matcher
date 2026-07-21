"""Resume tailoring pipeline.

Step 1 — Gemini Flash: analyze resume + job description → structured JSON diff
Step 2 — Groq (llama-3.3-70b): apply JSON diff to LaTeX → updated .tex source
Step 3 — tectonic: compile .tex → PDF bytes
Step 4 — persist TailoredResume row
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import JobMatch, JobPosting, Profile, SavedJob, TailoredResume

logger = logging.getLogger(__name__)

RESUME_DIR = Path(__file__).parent.parent.parent / "resume_latex"
TECTONIC = RESUME_DIR / "tectonic.exe"


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _load_source_files() -> tuple[str, str]:
    tex = (RESUME_DIR / "main.tex").read_text(encoding="utf-8")
    cls = (RESUME_DIR / "resume.cls").read_text(encoding="utf-8")
    return tex, cls


# ---------------------------------------------------------------------------
# Step 1 — Gemini Flash analysis
# ---------------------------------------------------------------------------

_VALID_JSON_ESCAPES = {'"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u'}


def _fix_json_escapes(s: str) -> str:
    """State-machine fixer: doubles lone backslashes inside JSON string values.

    Handles cases like \\item (valid pair kept), \\item (lone backslash fixed),
    and mixed sequences that a simple regex would mishandle.
    """
    out: list[str] = []
    in_string = False
    i = 0
    while i < len(s):
        c = s[i]
        if not in_string:
            out.append(c)
            if c == '"':
                in_string = True
        elif c == '\\':
            nc = s[i + 1] if i + 1 < len(s) else ''
            if nc in _VALID_JSON_ESCAPES:
                out.append(c)
                out.append(nc)
                i += 2
                continue
            else:
                out.append('\\')
                out.append('\\')
        elif c == '"':
            in_string = False
            out.append(c)
        else:
            out.append(c)
        i += 1
    return ''.join(out)


_GEMINI_PROMPT = """You are a professional resume tailor. Analyze the LaTeX resume and job description below, then return a JSON object specifying exactly what changes to make to tailor the resume for this specific job.

JOB DESCRIPTION:
{job_description}

USER NOTES (special emphasis):
{user_notes}

CURRENT RESUME (LaTeX):
{tex}

Return ONLY valid JSON in this exact structure — no markdown fences, no explanation:
{{
  "professional_summary": "rewritten 2-3 sentence summary emphasizing skills that are revelent to the JD",
  "skills_table": [
    {{"category": "Detection & Monitoring", "value": "comma-separated tools, most relevant first"}},
    {{"category": "Security Tools", "value": "..."}},
    {{"category": "AI Development Tools", "value": "..."}},
    {{"category": "Threat & Vuln. Frameworks", "value": "..."}},
    {{"category": "Infrastructure & Data", "value": "..."}},
    {{"category": "Network & Programming", "value": "..."}},
    {{"category": "Certifications", "value": "..."}}
  ],
  "experience_bullets": {{
    "Security Engineer – V2X Communication": ["bullet 1", "bullet 2", "bullet 3"],
    "Course Assistant, Graduate Cybersecurity": ["bullet 1", "bullet 2"],
    "Cybersecurity Intern": ["bullet 1", "bullet 2"]
  }},
  "projects_include": ["Project Name 1", "Project Name 2", "Project Name 3"],
  "project_bullets": {{
    "End-to-End Blue Team Lab": ["bullet 1", "bullet 2", "bullet 3"],
    "Assuring Airspace Safety Below 400 Feet under Congested and Malicious Conditions": ["bullet 1", "bullet 2"],
    "Multi-VM Layered Defense CTF": ["bullet 1", "bullet 2", "bullet 3"]
  }},
  "tailoring_rationale": "1-2 sentence explanation of the main changes made"
}}

Rules:
- Preserve all numbers and metrics exactly (98% accuracy, 1ms latency, etc.)
- Do NOT invent skills, tools, or achievements not present in the original resume
- Natural keyword integration only — do not keyword-stuff
- Limit projects_include to 3 projects maximum to stay within one page not more than that
- Bullet text should be plain text — no \\item, \\textbf, or other LaTeX commands
- Reorder skills_table rows to put most job-relevant categories first
"""


_GEMINI_MODELS = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]


def _analyze_with_gemini(tex: str, job_description: str, user_notes: str) -> dict:
    import time
    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = _GEMINI_PROMPT.format(
        job_description=job_description[:6000],
        user_notes=user_notes or "No special notes.",
        tex=tex,
    )

    last_exc: Exception | None = None
    for model in _GEMINI_MODELS:
        for attempt in range(3):
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                logger.info("resume_tailor: Gemini analysis OK (model=%s)", model)
                raw = response.text.strip()
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    fixed = _fix_json_escapes(raw)
                    try:
                        return json.loads(fixed)
                    except json.JSONDecodeError as e:
                        debug_path = Path(__file__).parent.parent.parent / "llm_debug.txt"
                        debug_path.write_text(
                            f"pos={e.pos} msg={e.msg}\n\nRAW:\n{raw}\n\nFIXED:\n{fixed}",
                            encoding="utf-8",
                        )
                        raise
            except Exception as e:
                s = str(e)
                is_quota = "429" in s or "RESOURCE_EXHAUSTED" in s
                is_not_found = "404" in s or "NOT_FOUND" in s
                if is_not_found:
                    logger.warning("resume_tailor: model %s not found, trying next", model)
                    last_exc = e
                    break  # skip retries for this model
                elif is_quota:
                    if attempt == 2:
                        logger.warning("resume_tailor: quota exhausted for %s, trying next model", model)
                        last_exc = e
                        break
                    wait = 15 * (2 ** attempt)  # 15s, 30s
                    logger.warning("resume_tailor: Gemini rate limit on %s, retry in %ds (attempt %d/2)", model, wait, attempt + 1)
                    time.sleep(wait)
                else:
                    raise  # unexpected error — surface immediately

    assert last_exc is not None
    raise last_exc


# ---------------------------------------------------------------------------
# Step 2 — Groq applies diff to LaTeX
# ---------------------------------------------------------------------------

_GROQ_PROMPT = """You are a LaTeX editor. Apply the following JSON changes to the LaTeX resume file.

CHANGES TO APPLY:
{analysis}

ORIGINAL LATEX FILE:
{tex}

Return ONLY the complete updated .tex file. No explanation, no markdown fences, no preamble.

Rules:
- Replace the Professional Summary paragraph with the value in "professional_summary"
- Replace the tabular rows in Technical Skills with the "skills_table" rows, reordering as specified
- Replace \\item bullets in each Work Experience job section using "experience_bullets" (match by job title text)
- Include ONLY the projects listed in "projects_include", in that order
- Replace \\item bullets in each included project using "project_bullets"
- Keep ALL LaTeX commands, environments, spacing commands (\\vspace, \\hfill, \\textbf, etc.) intact
- Bullet text should be wrapped in \\item as in the original
- Bold numbers/metrics with \\textbf{{}} as in the original where appropriate
- Output must be valid LaTeX that compiles with the resume.cls class file
"""


def _apply_with_groq(tex: str, analysis: dict) -> str:
    import time
    from groq import Groq, RateLimitError

    client = Groq(api_key=settings.groq_api_key)
    prompt = _GROQ_PROMPT.format(
        analysis=json.dumps(analysis, indent=2),
        tex=tex,
    )

    for attempt in range(4):
        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=16384,
            )
            break
        except RateLimitError as e:
            if attempt == 3:
                raise
            wait = 5 * (2 ** attempt)  # 5s, 10s, 20s
            logger.warning("resume_tailor: Groq rate limit, retrying in %ds (attempt %d/3)", wait, attempt + 1)
            time.sleep(wait)

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    finish_reason = response.choices[0].finish_reason
    if finish_reason == "length":
        logger.warning("resume_tailor: Groq output was truncated (finish_reason=length) — increase max_tokens or reduce input size")
    if r"\end{document}" not in raw:
        logger.warning("resume_tailor: Groq output may be incomplete (no \\end{document} found)")

    return raw


# ---------------------------------------------------------------------------
# Step 3 — tectonic compile
# ---------------------------------------------------------------------------

def _compile_pdf(tex: str, cls: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "main.tex").write_text(tex, encoding="utf-8")
        (tmp / "resume.cls").write_text(cls, encoding="utf-8")

        result = subprocess.run(
            [str(TECTONIC), "main.tex"],
            capture_output=True,
            cwd=tmpdir,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"tectonic compile failed:\n{result.stderr.decode(errors='replace')}"
            )

        pdf_path = tmp / "main.pdf"
        if not pdf_path.exists():
            raise RuntimeError("tectonic ran but main.pdf not produced")
        return pdf_path.read_bytes()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def tailor_resume(
    db: Session,
    *,
    profile: Profile,
    saved_job: SavedJob,
    job_posting: JobPosting,
    user_notes: str | None = None,
) -> TailoredResume:
    """Run the full Gemini → Groq → tectonic pipeline and persist the result."""
    tex, cls = _load_source_files()

    job_description = job_posting.raw_description or job_posting.title
    logger.info("resume_tailor: START v2 debug")

    # Step 1 — analysis (Groq llama-3.3-70b)
    logger.info("resume_tailor: calling Gemini for analysis, job %s", job_posting.id)
    try:
        analysis = _analyze_with_gemini(tex, job_description, user_notes or "")
    except Exception as exc:
        logger.error("resume_tailor: STEP 1 FAILED — %s", exc, exc_info=True)
        raise
    logger.info("resume_tailor: step 1 OK — %s", analysis.get("tailoring_rationale", ""))

    # Step 2 — Groq applies changes to a copy; main.tex is never modified
    logger.info("resume_tailor: calling Groq to apply changes")
    updated_tex = _apply_with_groq(tex, analysis)

    safe_title = re.sub(r"[^\w\-]", "_", job_posting.title or "resume")[:40]
    draft_path = RESUME_DIR / f"draft_{safe_title}_{saved_job.id[:8]}.tex"
    draft_path.write_text(updated_tex, encoding="utf-8")
    logger.info("resume_tailor: draft copy written to %s", draft_path.name)

    # Step 3 — compile PDF from draft copy, then delete it
    pdf_bytes: bytes | None = None
    try:
        logger.info("resume_tailor: compiling with tectonic")
        pdf_bytes = _compile_pdf(draft_path.read_text(encoding="utf-8"), cls)
        logger.info("resume_tailor: PDF compiled, %d bytes", len(pdf_bytes))
    except Exception as exc:
        logger.warning("resume_tailor: tectonic failed (%s) — saving .tex only", exc)
    finally:
        draft_path.unlink(missing_ok=True)
        logger.info("resume_tailor: draft copy deleted")

    # Step 4 — persist (upsert by saved_job_id)
    existing = (
        db.query(TailoredResume)
        .filter(TailoredResume.saved_job_id == saved_job.id)
        .first()
    )
    if existing:
        existing.latex_source = updated_tex
        existing.pdf_bytes = pdf_bytes
        existing.user_notes = user_notes
        existing.gemini_analysis = analysis
        existing.version = (existing.version or 1) + 1
        record = existing
    else:
        record = TailoredResume(
            profile_id=profile.id,
            job_id=job_posting.id,
            saved_job_id=saved_job.id,
            latex_source=updated_tex,
            pdf_bytes=pdf_bytes,
            user_notes=user_notes,
            gemini_analysis=analysis,
            version=1,
        )
        db.add(record)

    db.commit()
    db.refresh(record)
    return record

