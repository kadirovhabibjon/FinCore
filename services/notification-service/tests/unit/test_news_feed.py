"""Reading other sites' RSS: whatever a feed contains ends up as plain
text and an ordinary link, or not at all."""

from datetime import UTC, datetime

import pytest

from app.core.config import settings
from app.services.news import Article, _keywords, is_relevant, parse_feed

# The central bank's feed puts a default namespace on <rss>.
_NAMESPACED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns="http://backend.userland.com/rss2" xmlns:yandex="http://news.yandex.ru">
<channel><title>Yangiliklar</title>
<item>
  <title>Avgust oyi inflyatsiya ko'rsatkichlari</title>
  <link>https://cbu.uz/uz/press_center/news/4591013/</link>
  <description></description>
  <yandex:full-text></yandex:full-text>
  <pubDate>Thu, 24 Sep 2026 18:39:49 +0500</pubDate>
</item>
</channel></rss>"""

_WITH_MARKUP = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
<item>
  <title>Bank &amp;amp; kredit: yangi stavkalar</title>
  <description><![CDATA[<p>Foiz&nbsp;stavkasi <b>14%</b> bo'ldi.</p>
     <script>alert(1)</script><img src=x onerror=alert(2)>]]></description>
  <link> https://www.spot.uz/oz/2026/10/05/rates/ </link>
  <guid>rates-1</guid>
  <pubDate>Mon, 5 Oct 2026 11:07:00 GMT</pubDate>
</item>
<item><title>No link</title><description>x</description></item>
<item><title>Script link</title><link>javascript:alert(1)</link></item>
<item><title></title><link>https://www.spot.uz/empty/</link></item>
</channel></rss>"""


def test_reads_a_namespaced_feed_and_an_item_without_a_summary() -> None:
    [article] = parse_feed(_NAMESPACED, source="cbu.uz")

    assert article == Article(
        source="cbu.uz",
        guid="https://cbu.uz/uz/press_center/news/4591013/",  # no <guid>: the link
        title="Avgust oyi inflyatsiya ko'rsatkichlari",
        summary="",
        url="https://cbu.uz/uz/press_center/news/4591013/",
        published_at=datetime(2026, 9, 24, 13, 39, 49, tzinfo=UTC),
    )


def test_markup_becomes_plain_text_and_unusable_items_are_dropped() -> None:
    [article] = parse_feed(_WITH_MARKUP, source="spot.uz")

    assert article.title == "Bank & kredit: yangi stavkalar"
    assert article.summary == "Foiz stavkasi 14% bo'ldi. alert(1)"
    assert "<" not in article.summary and ">" not in article.summary
    assert article.url == "https://www.spot.uz/oz/2026/10/05/rates/"
    assert article.guid == "rates-1"


def test_long_text_is_cut_and_a_future_or_missing_date_is_not_trusted() -> None:
    feed = f"""<rss><channel>
    <item><title>{"a" * 400}</title><link>https://x.uz/1</link>
      <pubDate>Mon, 5 Oct 2099 11:07:00 GMT</pubDate></item>
    <item><title>No date</title><link>https://x.uz/2</link><pubDate>yesterday</pubDate></item>
    </channel></rss>""".encode()

    long_title, no_date = parse_feed(feed, source="x.uz")

    assert len(long_title.title) == 300 and long_title.title.endswith("…")
    now = datetime.now(UTC)
    assert long_title.published_at <= now
    assert no_date.published_at <= now


@pytest.mark.parametrize(
    "document",
    [
        b"<html><body>404</body>",
        b"not xml at all",
        # Entity expansion ("billion laughs") and external entities are refused.
        b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]>'
        b"<rss><channel><item><title>&b;</title><link>https://x.uz/</link></item></channel></rss>",
        b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        b"<rss><channel><item><title>&x;</title><link>https://x.uz/</link></item></channel></rss>",
    ],
    ids=["broken html", "not xml", "entity expansion", "external entity"],
)
def test_anything_that_is_not_a_plain_feed_is_rejected(document: bytes) -> None:
    with pytest.raises(ValueError):
        parse_feed(document, source="x.uz")


def test_relevance_matches_whole_words_and_word_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    def article(title: str, summary: str = "") -> Article:
        return Article("spot.uz", title, title, summary, "https://x.uz/", datetime.now(UTC))

    monkeypatch.setattr(settings, "news_keywords", "bank*, kredit*, to'lov tizim*, tax, bond")
    keywords = _keywords()

    # Uzbek adds endings to a word: a * keyword matches its start.
    assert is_relevant(article("Markaziy BANKNING qarori"), keywords)
    assert is_relevant(article("Yangi qaror", "Ipoteka kreditlari arzonlashadi"), keywords)
    # The same word, typed with any of the apostrophes in use.
    assert is_relevant(article("Yangi to‘lov tizimi ishga tushdi"), keywords)
    assert is_relevant(article("Yangi toʻlov tizimi ishga tushdi"), keywords)
    assert is_relevant(article("New tax rules announced"), keywords)

    # A plain keyword is a whole word: "tax" is not "taxminan" (roughly).
    assert not is_relevant(article("Marsdagi muz taxminan toza chiqdi"), keywords)
    assert not is_relevant(article("Vagabond travellers"), keywords)
    assert not is_relevant(article("Germaniyada shamol turbinasi qurildi"), keywords)

    monkeypatch.setattr(settings, "news_keywords", " , ")
    assert not is_relevant(article("Bank"), _keywords())
