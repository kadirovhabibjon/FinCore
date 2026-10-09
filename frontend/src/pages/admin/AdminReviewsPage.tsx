import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import * as api from "../../api/endpoints";
import { hasAnyRole, useAuth } from "../../auth/context";
import { ConfirmButton } from "../../components/ConfirmButton";
import { CustomerLink } from "../../components/admin/Customer";
import { useI18n } from "../../i18n";
import { reasonText } from "../../lib/reasons";
import { DateTime, Empty, ErrorAlert, Loading, Money, Notice, ShortId, StatusBadge } from "../../components/ui";

export function AdminReviewsPage() {
  const { user } = useAuth();
  const i18n = useI18n();
  const { t, tr, maybe } = i18n;
  const isAdmin = hasAnyRole(user, "ADMIN");
  const queryClient = useQueryClient();
  const [lastDecision, setLastDecision] = useState<api.AdminTransaction | null>(null);

  const reviews = useQuery({
    queryKey: ["admin", "reviews"],
    queryFn: api.adminListReviews,
    refetchInterval: 15_000,
  });
  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: api.ReviewDecision }) =>
      api.adminDecideReview(id, decision),
    onSuccess: (result) => setLastDecision(result),
    // A 409 means someone else (or the payment expiry) got there first:
    // refresh either way so the queue shows what is actually left.
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["admin", "reviews"] }),
  });

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{t("admin.reviews.title")}</h1>
          <p className="muted">{t("admin.reviews.subtitle")}</p>
        </div>
      </header>
      {lastDecision && (
        <Notice>
          {tr("admin.reviews.isNow", {
            reference: lastDecision.reference,
            status: <StatusBadge status={lastDecision.status} />,
          })}
          {lastDecision.failure_reason && ` — ${reasonText(lastDecision.failure_reason, i18n)}`}
        </Notice>
      )}
      <ErrorAlert error={reviews.error ?? decide.error} />
      {reviews.isPending ? (
        <Loading what={t("admin.reviews.loading")} />
      ) : reviews.data?.length === 0 ? (
        <Empty>{t("admin.reviews.empty")}</Empty>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t("admin.reviews.since")}</th>
              <th>{t("admin.col.reference")}</th>
              <th>{t("admin.reviews.customer")}</th>
              <th>{t("admin.reviews.destination")}</th>
              <th className="num">{t("admin.col.amount")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {reviews.data?.map((item) => (
              <tr key={item.id}>
                <td data-label={t("admin.reviews.since")}>
                  <DateTime value={item.created_at} />
                </td>
                <td data-label={t("admin.col.reference")}>
                  {item.reference}
                  <div className="muted small">{maybe(`type.${item.type}`) ?? item.type}</div>
                </td>
                <td data-label={t("admin.reviews.customer")}>
                  <CustomerLink userId={item.initiator_user_id} />
                </td>
                <td data-label={t("admin.reviews.destination")}>
                  <span className="muted small">
                    {item.type === "TRANSFER"
                      ? t("admin.reviews.wallet")
                      : t("admin.reviews.merchant")}
                  </span>{" "}
                  <ShortId id={item.counterparty_id} />
                </td>
                <td className="num" data-label={t("admin.col.amount")}>
                  <Money minor={item.amount_minor} currency={item.currency} />
                </td>
                <td className="num" data-label="">
                  {isAdmin ? (
                    <div className="actions">
                      {/* Either way money moves, or doesn't, for good. */}
                      <ConfirmButton
                        confirm={t("admin.reviews.confirmApprove")}
                        disabled={decide.isPending}
                        onConfirm={() => decide.mutate({ id: item.id, decision: "APPROVE" })}
                      >
                        {t("admin.reviews.approve")}
                      </ConfirmButton>
                      <ConfirmButton
                        confirm={t("admin.reviews.confirmReject")}
                        className="button button-small button-danger"
                        disabled={decide.isPending}
                        onConfirm={() => decide.mutate({ id: item.id, decision: "REJECT" })}
                      >
                        {t("admin.reviews.reject")}
                      </ConfirmButton>
                    </div>
                  ) : (
                    <span className="muted small">{t("admin.reviews.adminDecides")}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
