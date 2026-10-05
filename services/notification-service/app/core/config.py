from fincore_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "notification-service"

    # postgresql+asyncpg://user:password@host:port/notification_db
    database_url: str

    kafka_bootstrap_servers: str = "localhost:9094"
    transfers_topic: str = "transfers"
    # A distinct group id per logical consumer — Kafka tracks committed
    # offsets per (group_id, topic, partition), so this is what lets a
    # restarted notification-service resume where it left off instead of
    # replaying the whole topic.
    consumer_group_id: str = "notification-service"

    # Retry / DLT (spec Section 16). retry_topic gets its own consumer
    # group id derived from consumer_group_id, not a separate setting —
    # see app/core/kafka.py.
    retry_topic: str = "transfers-retry"
    dlt_topic: str = "transfers-dlt"
    max_retry_attempts: int = 3
    retry_base_delay_seconds: float = 2.0

    # For verifying customers' bearer tokens on the public notifications
    # API (the bell in the web app). Defaults rather than required, so a
    # .env written when this service had no public API still boots;
    # docker-compose.yml sets the in-network address.
    identity_service_jwks_url: str = "http://localhost:8091/.well-known/jwks.json"
    jwt_issuer: str = "fincore-identity-service"

    # Banking, finance and economy news for the bell's News tab, read from public
    # RSS feeds (comma-separated URLs). Feeds in `news_feeds` are taken
    # whole (the central bank's press releases are all relevant); feeds
    # in `news_filtered_feeds` are general business news, kept only when
    # the title or summary mentions one of `news_keywords`.
    news_feeds: str = "https://cbu.uz/uz/press_center/news/rss/"
    news_filtered_feeds: str = (
        "https://www.spot.uz/oz/rss/,https://kun.uz/news/rss,https://uzdaily.uz/en/rss"
    )
    # Words (Uzbek and English) that make an article banking, finance or
    # economy news. A word matches whole; with a trailing * it matches as
    # the start of a word, which Uzbek needs ("bank*" finds "banklarning")
    # and short English words must not have ("tax" is not "taxminan").
    # Nothing as common as "so'm" or "dollar": those appear in any story
    # with a price in it.
    news_keywords: str = (
        "bank*,kredit*,ipoteka*,depozit*,omonat*,qarz*,valyuta*,inflyatsiya*,stavka*,"
        "to'lov tizim*,pul o'tkazma*,fintex*,fintech*,obligatsiya*,birja*,soliq*,"
        "byudjet*,moliya*,iqtisod*,investitsiya*,sug'urta*,pensiya*,uzcard,humo,payme,"
        "loan,loans,lending,credit,credits,deposit,deposits,inflation,currency,"
        "exchange rate,fitch,moody's,tax,taxes,budget,investment,investments,"
        "finance,financial,insurance,bond,bonds,pension,pensions"
    )
    # 0 switches the poller off (the tests, and anyone offline).
    news_poll_interval_seconds: float = 900.0
    news_fetch_timeout_seconds: float = 10.0
    # How much is kept; older items are dropped as new ones arrive.
    news_max_items: int = 200

    # Shared secret for /internal/* endpoints (Section 19) — the manual
    # dead-letter replay API (app/api/internal/dead_letters.py).
    internal_service_token: str


settings = Settings()  # type: ignore[call-arg]
