import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import * as api from "../api/endpoints";
import { DateTime, Empty, ErrorAlert, Loading, StatusBadge } from "../components/ui";
import { useI18n } from "../i18n";

export function MerchantsPage() {
  const queryClient = useQueryClient();
  const merchants = useQuery({ queryKey: ["merchants"], queryFn: api.listMerchants });
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: api.createMerchant,
    onSuccess: () => {
      setName("");
      void queryClient.invalidateQueries({ queryKey: ["merchants"] });
    },
  });

  const { t } = useI18n();

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    create.mutate(name.trim());
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{t("merchants.title")}</h1>
          <p className="muted">{t("merchants.subtitle")}</p>
        </div>
        <form className="inline-form" onSubmit={onSubmit}>
          <input
            aria-label={t("merchants.name")}
            placeholder={t("merchants.namePlaceholder")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={255}
          />
          <button type="submit" className="button" disabled={create.isPending}>
            {t("merchants.create")}
          </button>
        </form>
      </header>
      <ErrorAlert error={create.error ?? merchants.error} />
      {merchants.isPending ? (
        <Loading what={t("merchants.loading")} />
      ) : merchants.data?.length === 0 ? (
        <Empty>{t("merchants.empty")}</Empty>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t("merchants.colName")}</th>
              <th>{t("merchants.colStatus")}</th>
              <th>{t("merchants.colCreated")}</th>
            </tr>
          </thead>
          <tbody>
            {merchants.data?.map((merchant) => (
              <tr key={merchant.id}>
                <td data-label={t("merchants.colName")}>
                  <Link to={`/merchants/${merchant.id}`}>{merchant.name}</Link>
                </td>
                <td data-label={t("merchants.colStatus")}>
                  <StatusBadge status={merchant.status} />
                </td>
                <td data-label={t("merchants.colCreated")}>
                  <DateTime value={merchant.created_at} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
