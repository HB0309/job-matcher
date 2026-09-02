from app.workers.connectors.base import BaseConnector
from app.workers.connectors.linkedin import LinkedInConnector
from app.workers.connectors.remoteok import RemoteOKConnector
from app.workers.connectors.themuse import TheMuseConnector
from app.workers.connectors.adzuna import AdzunaConnector  # requires ADZUNA_APP_ID + ADZUNA_APP_KEY in .env
from app.workers.connectors.jobright import JobRightConnector
from app.workers.connectors.remotive import RemotiveConnector
from app.workers.connectors.dice import DiceConnector  # requires playwright + chromium

_REGISTRY: dict[str, BaseConnector] = {
    "linkedin": LinkedInConnector(),
    "remoteok": RemoteOKConnector(),
    "themuse": TheMuseConnector(),
    "adzuna": AdzunaConnector(),
    "jobright": JobRightConnector(),
    "remotive": RemotiveConnector(),
    "dice": DiceConnector(),
}


def get_connector(name: str) -> BaseConnector:
    connector = _REGISTRY.get(name)
    if connector is None:
        raise ValueError(f"Unknown connector: {name!r}. Registered: {list(_REGISTRY)}")
    return connector


def list_connectors() -> list[str]:
    return list(_REGISTRY)
