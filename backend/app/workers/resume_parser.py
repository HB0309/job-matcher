import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

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
