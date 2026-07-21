from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://localhost/job_matcher"
    cors_origins: str = "http://localhost:3000,http://localhost:4000"
    upload_dir: str = "./uploads"
    linkedin_email: str = ""
    linkedin_password: str = ""
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""

    # Apply Extension – drafting provider
    drafting_provider: str = "deterministic"  # "deterministic" | "huggingface"
    hf_api_token: str = ""
    hf_model: str = "Qwen/Qwen2.5-7B-Instruct"
    hf_provider: str = "together"

    # Resume tailoring
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # Auto-apply credentials
    apply_email: str = ""
    apply_password: str = ""

    # Auto-apply contact info (used to fill job application forms)
    apply_first_name: str = ""
    apply_last_name: str = ""
    apply_phone: str = ""
    apply_address_line1: str = ""
    apply_city: str = ""
    apply_state: str = ""
    apply_postal_code: str = ""
    apply_country: str = "United States of America"
    apply_heard_about: str = "LinkedIn"  # "How did you hear about us?"
    apply_linkedin_url: str = ""

    # Education — used for dropdown questions AND Workday section filling
    apply_highest_degree: str = "Master of Science"
    apply_school: str = "Johns Hopkins University"         # most recent
    apply_major: str = "Security Informatics"              # most recent

    # Education entry 1 — Masters (most recent; used for Workday education section)
    apply_edu1_school: str = "Johns Hopkins University"
    apply_edu1_degree: str = "Master of Science"
    apply_edu1_major: str = "Security Informatics"
    apply_edu1_start_month: str = "5"
    apply_edu1_start_year: str = "2024"
    apply_edu1_end_month: str = "12"
    apply_edu1_end_year: str = "2025"

    # Education entry 2 — Bachelors
    apply_edu2_school: str = "Vellore Institute of Technology"
    apply_edu2_degree: str = "Bachelor of Technology"
    apply_edu2_major: str = "Computer Science and Engineering"
    apply_edu2_start_month: str = "9"
    apply_edu2_start_year: str = "2020"
    apply_edu2_end_month: str = "5"
    apply_edu2_end_year: str = "2024"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
