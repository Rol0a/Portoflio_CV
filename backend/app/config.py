from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://portfolio:changeme@localhost:5432/portfolio"
    cors_allowed_origins: str = "http://localhost:5173"
    session_secret_key: str = "dev-secret-change-me"
    session_cookie_secure: bool = True

    # Which peer addresses may set X-Forwarded-For — i.e. where the reverse
    # proxy sits. Comma-separated IPs and/or CIDR ranges. Defaults to
    # loopback only, matching uvicorn's own default: in dev the browser
    # reaches the backend directly, so nothing should be trusted to rewrite
    # the client IP. In production this must name the Caddy container's
    # network (see .env.example and app/middleware/proxy.py).
    #
    # Never set this to "*" on a public deployment: it lets any client spoof
    # its own IP via a request header, which defeats the login rate limiting
    # this value exists to protect. Startup logs a warning if it is.
    trusted_proxy_ips: str = "127.0.0.1"

    # Data-retention sweep (app/services/retention_service.py). Runs inside the
    # API process rather than as a separate container or host cron job — this
    # deployment runs exactly one backend replica, so there is no coordination
    # problem to solve, and keeping it in-process means retention cannot be
    # forgotten when the stack moves hosts. Disable it here and run
    # `python -m scripts.purge_retention` from cron instead if that changes.
    retention_purge_enabled: bool = True
    retention_purge_interval_hours: int = 24

    # Contact form relay (app/services/contact_service.py). The destination is
    # the site owner's private address: it is served to nobody, appears in no
    # API response, and must never be hardcoded in the frontend — anything in
    # the bundle is public and gets scraped. Empty disables the form, which
    # then reports itself as unavailable rather than silently discarding mail.
    contact_to_email: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_use_tls: bool = True  # implicit TLS (SMTPS) on 465; False = STARTTLS on 587
    smtp_username: str = ""
    smtp_password: str = ""  # Gmail: an App Password, never the account password
    smtp_from: str = ""  # defaults to smtp_username

    admin_username: str = "admin"
    admin_password: str = "changeme"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def trusted_proxies(self) -> list[str]:
        return [host.strip() for host in self.trusted_proxy_ips.split(",") if host.strip()]

    @property
    def contact_email_configured(self) -> bool:
        return bool(self.contact_to_email and self.smtp_host and self.smtp_username)


settings = Settings()
