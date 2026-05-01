from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""

    polymarket_private_key: str = ""
    polymarket_api_key: str = ""
    polymarket_api_secret: str = ""
    polymarket_api_passphrase: str = ""

    trading_mode: str = "paper"
    paper_bankroll: float = 1000.0

    kelly_fraction: float = 0.25
    max_position_pct: float = 0.10
    max_portfolio_exposure: float = 0.80
    min_edge: float = 0.03

    screener_model: str = "claude-haiku-4-5-20251001"
    decider_model: str = "claude-opus-4-7"

    rss_feeds: str = ""

    log_level: str = "INFO"

    @property
    def rss_feed_list(self) -> list[str]:
        return [u.strip() for u in self.rss_feeds.split(",") if u.strip()]


settings = Settings()
