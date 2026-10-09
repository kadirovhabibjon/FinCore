import type { Service, Template } from "../api/endpoints";
import type { I18n } from "../i18n";
import { formatMinor, minorToInput } from "./money";

/** Where a template leads: the form it fills in. Nothing is paid by
 * opening it - the customer presses the button on that form. */
export function templateLink(template: Template): string {
  const params = new URLSearchParams();
  if (template.kind === "SERVICE") {
    params.set("service", template.service_code ?? "");
    params.set("account", template.service_account ?? "");
  } else {
    params.set("to", template.card_number ?? "");
  }
  if (template.amount_minor != null) {
    // A decimal string, as the forms take it; built from the integer.
    params.set("amount", minorToInput(template.amount_minor, template.currency));
  }
  return `${template.kind === "SERVICE" ? "/pay" : "/transfer"}?${params.toString()}`;
}

/** The line under a template's name: what it pays and how much. */
export function templateSummary(template: Template, services: Service[], i18n: I18n): string {
  const { t, maybe } = i18n;
  let what: string;
  if (template.kind === "SERVICE") {
    const service = services.find((item) => item.code === template.service_code);
    const provider =
      maybe(`provider.${template.service_code}`) ?? service?.name ?? template.service_code ?? "";
    what = `${provider} · ${template.service_account ?? ""}`;
  } else {
    what = t("tpl.transferTo", {
      name: template.recipient_name ?? "",
      last4: (template.card_number ?? "").slice(-4),
    });
  }
  const amount =
    template.amount_minor != null
      ? formatMinor(template.amount_minor, template.currency)
      : t("tpl.anyAmount");
  return `${what} · ${amount}`;
}
