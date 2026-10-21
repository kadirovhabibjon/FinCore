import { useI18n } from "../i18n";

/** Grey shapes where content is about to be: the page keeps its layout
 * while it loads instead of jumping when the data arrives. Hidden from
 * screen readers, which hear the one "Loading…" status instead. */
export function Skeleton({ width, height = "1rem" }: { width?: string; height?: string }) {
  return <span className="skeleton" aria-hidden="true" style={{ width, height }} />;
}

/** A row of card-shaped placeholders, for lists of cards. */
export function SkeletonCards({ count = 2, height = "8.5rem" }: { count?: number; height?: string }) {
  const { t } = useI18n();
  return (
    <div className="grid" role="status" aria-label={t("common.loading")}>
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="card skeleton-card" style={{ minHeight: height }}>
          <Skeleton width="45%" />
          <Skeleton width="70%" height="0.85rem" />
          <Skeleton width="55%" height="1.6rem" />
        </div>
      ))}
    </div>
  );
}

/** A page-sized placeholder: shown while a page's own code loads. */
export function PageSkeleton() {
  const { t } = useI18n();
  return (
    <section className="page page-skeleton" role="status" aria-label={t("common.loading")}>
      <Skeleton width="14rem" height="1.8rem" />
      <Skeleton width="20rem" height="0.95rem" />
      <div className="card skeleton-card">
        <Skeleton width="40%" />
        <Skeleton width="85%" />
        <Skeleton width="65%" />
      </div>
    </section>
  );
}
