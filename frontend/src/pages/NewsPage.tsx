import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";

import * as api from "../api/endpoints";
import { DateTime, Empty, ErrorAlert, Loading } from "../components/ui";

const PAGE_SIZE = 50;

/** Every article currently kept, newest first. Being here counts as
 * having seen them, so the bell's news badge clears. */
export function NewsPage() {
  const queryClient = useQueryClient();
  const news = useQuery({ queryKey: ["news", "all"], queryFn: () => api.listNews(PAGE_SIZE) });
  const { mutate: markRead } = useMutation({
    mutationFn: api.markNewsRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["news"], exact: true }),
  });
  const hasUnread = (news.data?.unread_count ?? 0) > 0;
  useEffect(() => {
    if (hasUnread) markRead();
  }, [hasUnread, markRead]);

  return (
    <section className="page narrow-wide">
      <header className="page-header">
        <div>
          <h1>Banking &amp; finance news</h1>
          <p className="muted">
            Banking, finance and economy headlines from public news feeds, newest first. FinCore
            doesn&apos;t write or check them.
          </p>
        </div>
      </header>
      <ErrorAlert error={news.error} />
      {news.isPending ? (
        <Loading what="Loading news" />
      ) : news.data?.items.length === 0 ? (
        <Empty>No banking news yet. Check back later.</Empty>
      ) : (
        <ul className="list">
          {news.data?.items.map((item) => (
            <li key={item.id}>
              <Link to={`/news/${item.id}`} className="card news-card">
                <strong>{item.title}</strong>
                {item.summary && <span className="news-summary">{item.summary}</span>}
                <span className="muted small">
                  {item.source} · <DateTime value={item.published_at} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** One article as its feed describes it. The full text is the
 * publisher's: it opens on their site, in a new tab. */
export function NewsItemPage() {
  const { newsId = "" } = useParams();
  const item = useQuery({
    queryKey: ["news", "item", newsId],
    queryFn: () => api.getNewsItem(newsId),
  });

  if (item.isPending) return <Loading what="Loading article" />;
  if (item.error) return <ErrorAlert error={item.error} />;
  const article = item.data;

  return (
    <article className="page narrow-wide">
      <p className="small">
        <Link to="/news">← All news</Link>
      </p>
      <h1>{article.title}</h1>
      <p className="muted">
        {article.source} · <DateTime value={article.published_at} />
      </p>
      <div className="card news-body">
        {article.summary ? (
          <p>{article.summary}</p>
        ) : (
          <p className="muted">The publisher gives no summary for this article.</p>
        )}
        <a className="button" href={article.url} target="_blank" rel="noopener noreferrer">
          Read the full article on {article.source} ↗
        </a>
      </div>
      <p className="muted small">
        From {article.source}&apos;s public news feed. FinCore shows the publisher&apos;s
        headline and summary as they are; the article itself is on their site.
      </p>
    </article>
  );
}
