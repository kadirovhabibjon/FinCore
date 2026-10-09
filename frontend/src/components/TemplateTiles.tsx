import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import * as api from "../api/endpoints";
import { useI18n } from "../i18n";
import { templateLink, templateSummary } from "../lib/templates";

/** Saved payments as tiles; each opens the form it fills in. */
export function TemplateTiles({ templates }: { templates: api.Template[] }) {
  const i18n = useI18n();
  // For the providers' names; without it a tile still shows the code.
  const services = useQuery({
    queryKey: ["services"],
    queryFn: api.listServices,
    staleTime: 60 * 60 * 1000,
    retry: false,
  });
  return (
    <div className="service-grid">
      {templates.map((template) => (
        <Link key={template.id} to={templateLink(template)} className="card service-tile">
          <span className="recipient-avatar" aria-hidden="true">
            {template.name.slice(0, 1).toUpperCase()}
          </span>
          <span className="template-text">
            <span>{template.name}</span>
            <span className="muted small">
              {templateSummary(template, services.data ?? [], i18n)}
            </span>
          </span>
        </Link>
      ))}
    </div>
  );
}
