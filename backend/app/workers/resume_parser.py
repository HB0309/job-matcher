import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_CURRENT_YEAR = date.today().year
_CURRENT_MONTH = date.today().month

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

SKILL_KEYWORDS: list[str] = [
    # ---------- Languages ----------
    "python", "java", "javascript", "typescript", "go", "rust",
    "c++", "c#", "ruby", "php", "swift", "kotlin", "scala",
    "elixir", "erlang", "haskell", "ocaml", "lua", "dart", "clojure", "groovy", "f#",
    # ---------- Web / frontend ----------
    "react", "vue", "angular", "svelte", "sveltekit", "astro", "remix",
    "next.js", "nuxt", "html", "css",
    # ---------- Web / backend ----------
    "node.js", "nest.js", "fastapi", "django", "flask", "express",
    "spring", "spring boot", "rails", "laravel", "phoenix", "asp.net",
    # ---------- Mobile ----------
    "react native", "flutter", "swiftui", "jetpack compose", "xamarin", "ionic",
    # ---------- API / data layer ----------
    "graphql", "grpc", "protobuf", "openapi", "rest", "api", "websockets", "mqtt", "avro",
    # ---------- Databases – relational ----------
    "sql", "postgresql", "mysql", "sqlite", "mariadb", "oracle",
    # ---------- Databases – NoSQL / document ----------
    "mongodb", "dynamodb", "cassandra", "redis", "memcached",
    "firebase", "firestore", "neo4j", "couchdb", "cockroachdb",
    # ---------- Databases – search / vector ----------
    "elasticsearch", "opensearch", "pinecone", "weaviate", "chroma",
    # ---------- Databases – analytical / data warehouse ----------
    "snowflake", "bigquery", "redshift", "clickhouse", "influxdb",
    # ---------- Cloud ----------
    "aws", "azure", "gcp",
    # ---------- Containers / orchestration ----------
    "docker", "kubernetes", "helm", "istio", "linkerd", "envoy",
    # ---------- IaC / config management ----------
    "terraform", "pulumi", "ansible", "vagrant", "cloudformation",
    # ---------- CI/CD ----------
    "ci/cd", "jenkins", "github actions", "gitlab ci", "circleci", "argocd",
    # ---------- Observability / monitoring ----------
    "prometheus", "grafana", "datadog", "sentry", "new relic", "opentelemetry",
    # ---------- OS / shell / VCS ----------
    "linux", "bash", "shell", "git", "nginx",
    # ---------- Message queues / streaming ----------
    "kafka", "rabbitmq", "nats", "pulsar", "activemq",
    # ---------- Testing ----------
    "jest", "pytest", "cypress", "playwright", "selenium", "junit", "vitest", "k6",
    "tdd", "bdd",
    # ---------- Data engineering ----------
    "spark", "flink", "dbt", "airflow", "pandas", "numpy", "polars", "dask",
    # ---------- ML / AI ----------
    "machine learning", "deep learning", "pytorch", "tensorflow", "jax",
    "scikit-learn", "xgboost", "lightgbm", "catboost",
    "langchain", "llamaindex", "hugging face", "mlflow", "weights and biases",
    # ---------- Build tools / package managers ----------
    "webpack", "vite", "gradle", "maven", "npm", "yarn",
    # ---------- Auth / security protocols ----------
    "oauth", "saml", "oidc", "jwt", "tls",
    # ---------- Security ----------
    "cryptography", "splunk", "wazuh", "siem", "wireshark", "nmap", "metasploit",
    "burp suite", "penetration testing", "threat hunting", "incident response",
    "soc", "ids", "ips", "firewall", "vpn",
    "owasp", "malware analysis", "digital forensics", "snyk", "sonarqube",
    # ---------- Tools ----------
    "postman", "jira", "figma",
    # ---------- Architecture / practices ----------
    "microservices", "serverless", "event-driven", "cqrs", "devops",
    "agile", "scrum", "kanban",
    # ---------- Networking ----------
    "tcp/ip", "dns", "http",
]

# Maps variant/abbreviation → canonical skill name.
# extract_skills() checks these first so both "k8s" and "kubernetes" normalize to "kubernetes".
SKILL_ALIASES: dict[str, str] = {
    # ---------- JavaScript ecosystem ----------
    "js": "javascript",
    "ts": "typescript",
    "nodejs": "node.js",
    "node js": "node.js",
    "reactjs": "react",
    "react.js": "react",
    "vuejs": "vue",
    "vue.js": "vue",
    "vue3": "vue",
    "nextjs": "next.js",
    "next js": "next.js",
    "nuxtjs": "nuxt",
    "nuxt.js": "nuxt",
    "nestjs": "nest.js",
    "nest js": "nest.js",
    "angularjs": "angular",
    "angular.js": "angular",
    "sveltejs": "svelte",
    "svelte.js": "svelte",
    # ---------- Python ----------
    "python3": "python",
    # ---------- Go ----------
    "golang": "go",
    # ---------- Other languages ----------
    "cpp": "c++",
    "c plus plus": "c++",
    "csharp": "c#",
    "dotnet": "asp.net",
    "asp.net core": "asp.net",
    # ---------- Backend frameworks ----------
    "ruby on rails": "rails",
    "ror": "rails",
    "spring boot": "spring boot",
    "spring mvc": "spring boot",
    "django rest framework": "django",
    "drf": "django",
    "express.js": "express",
    "nestjs": "nest.js",
    # ---------- Mobile ----------
    "react-native": "react native",
    "jetpack": "jetpack compose",
    # ---------- Cloud ----------
    "amazon web services": "aws",
    "google cloud": "gcp",
    "google cloud platform": "gcp",
    "microsoft azure": "azure",
    # ---------- Containers / K8s ----------
    "k8s": "kubernetes",
    "kube": "kubernetes",
    "docker compose": "docker",
    "docker-compose": "docker",
    # ---------- IaC ----------
    "aws cdk": "cloudformation",
    # ---------- CI/CD ----------
    "cicd": "ci/cd",
    "ci cd": "ci/cd",
    "continuous integration": "ci/cd",
    "continuous delivery": "ci/cd",
    "continuous deployment": "ci/cd",
    "gitlab-ci": "gitlab ci",
    "circle ci": "circleci",
    "argo cd": "argocd",
    # ---------- Observability ----------
    "new-relic": "new relic",
    "open telemetry": "opentelemetry",
    # ---------- Databases ----------
    "postgres": "postgresql",
    "psql": "postgresql",
    "mongo": "mongodb",
    "dynamo": "dynamodb",
    "dynamo db": "dynamodb",
    "amazon dynamodb": "dynamodb",
    "elastic": "elasticsearch",
    "apache cassandra": "cassandra",
    "cockroach db": "cockroachdb",
    # ---------- Message queues ----------
    "apache kafka": "kafka",
    "apache pulsar": "pulsar",
    "rabbit mq": "rabbitmq",
    # ---------- Data engineering ----------
    "apache spark": "spark",
    "apache flink": "flink",
    "apache airflow": "airflow",
    "data build tool": "dbt",
    # ---------- ML / AI ----------
    "ml": "machine learning",
    "artificial intelligence": "machine learning",
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "xgb": "xgboost",
    "lgbm": "lightgbm",
    "huggingface": "hugging face",
    "wandb": "weights and biases",
    "w&b": "weights and biases",
    # ---------- API / protocols ----------
    "restful": "rest",
    "rest api": "rest",
    "rest apis": "rest",
    "protocol buffers": "protobuf",
    "protobufs": "protobuf",
    "swagger": "openapi",
    "open api": "openapi",
    "websocket": "websockets",
    "web sockets": "websockets",
    "web socket": "websockets",
    # ---------- Auth ----------
    "oauth2": "oauth",
    "oauth 2.0": "oauth",
    "openid connect": "oidc",
    "open id connect": "oidc",
    "json web token": "jwt",
    "json web tokens": "jwt",
    # ---------- Security ----------
    "pentest": "penetration testing",
    "pentesting": "penetration testing",
    "pen testing": "penetration testing",
    "pen test": "penetration testing",
    # ---------- Testing practices ----------
    "test driven development": "tdd",
    "test-driven development": "tdd",
    "behavior driven development": "bdd",
    "behaviour driven development": "bdd",
    "behavior-driven development": "bdd",
}


@dataclass
class ParsedResume:
    headline: str | None
    years_experience: int | None
    skills: list[str] = field(default_factory=list)


def _extract_text_pdf(path: Path) -> str:
    import pypdf
    reader = pypdf.PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_text_docx(path: Path) -> str:
    import docx
    doc = docx.Document(str(path))
    return "\n".join(para.text for para in doc.paragraphs)


def extract_text(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_text_pdf(path)
    elif suffix in (".docx", ".doc"):
        return _extract_text_docx(path)
    raise ValueError(f"Unsupported file type: {suffix!r}. Expected .pdf or .docx")


def extract_skills(text: str) -> list[str]:
    lower = text.lower()
    found: set[str] = set()
    for variant, canonical in SKILL_ALIASES.items():
        if re.search(r"\b" + re.escape(variant) + r"\b", lower):
            found.add(canonical)
    for skill in SKILL_KEYWORDS:
        if re.search(r"\b" + re.escape(skill) + r"\b", lower):
            found.add(skill)
    return sorted(found)


def _parse_month_year(month_str: str, year_str: str) -> tuple[int, int]:
    """Return (year, month) from matched strings."""
    return int(year_str), _MONTH_MAP.get(month_str.lower()[:3], 1)


def _duration_months(start_y: int, start_m: int, end_y: int, end_m: int) -> int:
    return max(0, (end_y - start_y) * 12 + (end_m - start_m))


def extract_years_experience(text: str) -> int | None:
    # Strategy 1: explicit "X years of experience" pattern
    matches = re.findall(r"(\d+)\+?\s*years?\s+(?:of\s+)?(?:experience|exp)", text, re.IGNORECASE)
    if matches:
        return max(int(m) for m in matches)

    # Strategy 2: sum explicit date ranges (Month Year – Month Year/Present)
    # Matches: "May 2023 – Aug 2023", "Jan 2025 - Present", "August 2024 to Current"
    _MONTHS = (
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    )
    _YEAR = r"(20\d{2}|19\d{2})"
    _SEP = r"\s*(?:–|—|-|to)\s*"
    _END = rf"(?:({_MONTHS})\s+{_YEAR}|(?:Present|Current|Now|Today))"
    pattern = rf"({_MONTHS})\s+{_YEAR}{_SEP}{_END}"

    total_months = 0
    for m in re.finditer(pattern, text, re.IGNORECASE):
        start_mon, start_yr = m.group(1), m.group(2)
        end_mon, end_yr = m.group(3), m.group(4)
        sy, sm = _parse_month_year(start_mon, start_yr)
        if end_mon and end_yr:
            ey, em = _parse_month_year(end_mon, end_yr)
        else:
            ey, em = _CURRENT_YEAR, _CURRENT_MONTH
        total_months += _duration_months(sy, sm, ey, em)

    if total_months > 0:
        # Round: < 6 months → 0, 6-17 months → 1, 18-29 → 2, etc.
        return max(0, round(total_months / 12))

    return None


def extract_headline(text: str, preferred_titles: list[str]) -> str | None:
    title_kws = [
        "engineer", "developer", "analyst", "scientist", "manager",
        "architect", "consultant", "specialist", "lead", "intern", "researcher",
    ]
    # Patterns that look like degree/education lines — skip them
    _edu_kws = [
        "b.tech", "b.e.", "btech", "b.s.", "m.s.", "m.tech", "phd", "bachelor",
        "master", "computer science", "information technology", "university", "institute",
        "college", "gpa", "cgpa",
    ]
    for line in (l.strip() for l in text.splitlines() if l.strip()):
        lower = line.lower()
        if any(kw in lower for kw in title_kws) and len(line) < 100:
            if not any(edu in lower for edu in _edu_kws):
                return line
    return preferred_titles[0] if preferred_titles else None


def parse_resume(file_path: str, preferred_titles: list[str] | None = None) -> ParsedResume:
    text = extract_text(file_path)
    return ParsedResume(
        headline=extract_headline(text, preferred_titles or []),
        years_experience=extract_years_experience(text),
        skills=extract_skills(text),
    )


# ---------------------------------------------------------------------------
# LLM-structured parsing (Stage 0 of agentic matching, see docs/03-agents-flows.md).
#
# Runs ONCE per resume upload, not per job match — cost is negligible even with
# a capable model. Extracts richer structured data than the regex extractors
# above (which stay as-is and remain the source of truth for headline/
# years_experience/skills). On any failure this returns None and the caller
# keeps the regex-only profile — LLM enrichment is best-effort, never blocking.
# ---------------------------------------------------------------------------

_RESUME_LLM_PROMPT = """You are extracting structured data from a resume for a job-matching system.
Read the resume text below and return ONLY valid JSON, no markdown fences, no explanation, in this exact structure:

{{
  "skills": ["skill1", "skill2", ...],
  "experience_bullets": ["concise accomplishment 1", "concise accomplishment 2", ...],
  "seniority": "one of: new_grad, entry, junior, mid, senior, staff, principal",
  "domain_keywords": ["keyword1", "keyword2", ...]
}}

Rules:
- "skills": every real technical skill/tool/technology actually used, lowercase, deduplicated.
- "experience_bullets": rewrite each real accomplishment from the resume as one short, factual sentence (do not invent anything not in the text). Include every distinct accomplishment across all jobs/projects, not just the most recent.
- "seniority": your best estimate of the candidate's current level based on years of experience and role titles.
- "domain_keywords": the specific problem domains/industries this person's experience is actually in (e.g. "cybersecurity", "backend", "machine learning", "distributed systems") — not generic words like "software" or "engineer".

RESUME TEXT:
{text}
"""


def parse_resume_llm(text: str) -> dict | None:
    """Structured-output LLM parse of resume text. Returns None on any failure
    (missing API key, rate limit exhausted, malformed response) — caller must
    treat this as optional enrichment, not a hard dependency."""
    from app.config import settings

    if not settings.gemini_api_key:
        logger.info("resume_parser: no gemini_api_key configured, skipping LLM parse")
        return None

    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = _RESUME_LLM_PROMPT.format(text=text[:12000])

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            data = json.loads(raw)
            # Minimal shape validation — malformed shape is treated like a failure.
            has_skills = isinstance(data.get("skills"), list)
            has_bullets = isinstance(data.get("experience_bullets"), list)
            if not has_skills or not has_bullets:
                logger.warning("resume_parser: LLM response missing expected keys, discarding")
                return None
            return data
        except Exception as exc:
            last_exc = exc
            s = str(exc)
            if "429" in s or "RESOURCE_EXHAUSTED" in s:
                if attempt == 2:
                    break
                wait = 10 * (2 ** attempt)
                logger.warning(
                    "resume_parser: Gemini rate limit, retry in %ds (attempt %d/2)",
                    wait, attempt + 1,
                )
                time.sleep(wait)
                continue
            break  # non-rate-limit error — don't retry, just fall back

    logger.warning(
        "resume_parser: LLM parse failed (%s) — falling back to regex-only profile", last_exc
    )
    return None
