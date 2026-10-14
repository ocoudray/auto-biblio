"""Site configuration (`config/site.yaml`): where the knowledge-base site is published."""

from pydantic import BaseModel, ConfigDict, field_validator


class SiteConfig(BaseModel):
    """Address and title of the published site; every field is optional."""

    # Unknown keys are rejected so that a typo fails loudly instead of keeping the default.
    model_config = ConfigDict(frozen=True, extra="forbid")

    site_url: str | None = None
    """Public address of the site; the digest links to it when set."""
    title: str = "Veille IA"
    """Title shown on every page."""

    @field_validator("site_url")
    @classmethod
    def _https_with_trailing_slash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith("https://"):
            msg = "site_url must start with https://"
            raise ValueError(msg)
        return value if value.endswith("/") else f"{value}/"
