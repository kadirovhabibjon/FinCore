import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import * as api from "../api/endpoints";
import { ConfirmButton } from "../components/ConfirmButton";
import { Empty, ErrorAlert, Loading } from "../components/ui";
import { useI18n } from "../i18n";
import { templateLink, templateSummary } from "../lib/templates";

/** Every saved payment, with a way to remove the ones no longer needed. */
export function TemplatesPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const queryClient = useQueryClient();
  const templates = useQuery({ queryKey: ["templates"], queryFn: api.listTemplates });
  const services = useQuery({
    queryKey: ["services"],
    queryFn: api.listServices,
    staleTime: 60 * 60 * 1000,
    retry: false,
  });
  const remove = useMutation({
    mutationFn: api.deleteTemplate,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["templates"] }),
  });

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{t("tpl.title")}</h1>
          <p className="muted">{t("tpl.subtitle")}</p>
        </div>
      </header>
      <ErrorAlert error={templates.error ?? remove.error} />
      {templates.isPending ? (
        <Loading what={t("tpl.loading")} />
      ) : templates.data?.length === 0 ? (
        <Empty>{t("tpl.empty")}</Empty>
      ) : (
        <ul className="list">
          {templates.data?.map((template) => (
            <li key={template.id} className="card">
              <div className="list-row">
                <div>
                  <strong>{template.name}</strong>
                  <div className="muted small">
                    {templateSummary(template, services.data ?? [], i18n)}
                  </div>
                </div>
                <div className="actions">
                  <Link to={templateLink(template)} className="button button-small">
                    {t("tpl.use")}
                  </Link>
                  <ConfirmButton
                    confirm={t("tpl.confirmDelete")}
                    className="button button-small button-ghost"
                    disabled={remove.isPending}
                    onConfirm={() => remove.mutate(template.id)}
                  >
                    {t("tpl.delete")}
                  </ConfirmButton>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
