import { useMutation } from "@tanstack/react-query";

import { saveDownload, type Download } from "../api/client";
import { ErrorAlert } from "./ui";
import { useI18n } from "../i18n";

/** Fetches a file with the customer's session and saves it. A button,
 * not a link: the file needs the bearer token, which a link can't send. */
export function DownloadButton({
  label,
  fetchFile,
  className = "button button-ghost",
}: {
  label: string;
  fetchFile: () => Promise<Download>;
  className?: string;
}) {
  const { t } = useI18n();
  const download = useMutation({ mutationFn: fetchFile, onSuccess: saveDownload });
  return (
    <>
      <button
        type="button"
        className={className}
        disabled={download.isPending}
        onClick={() => download.mutate()}
      >
        {download.isPending ? t("download.preparing") : label}
      </button>
      <ErrorAlert error={download.error} />
    </>
  );
}
