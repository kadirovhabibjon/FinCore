import { useEffect, useRef, useState } from "react";
import { useI18n, type MessageKey } from "../i18n";

type Problem = "unsupported" | "denied" | "failed";

const MESSAGES: Record<Problem, MessageKey> = {
  unsupported: "qr.unsupported",
  denied: "qr.denied",
  failed: "qr.failed",
};

/** Reads a QR code with the device camera and hands its text to
 * `onRead`; the caller decides whether it means anything. The video
 * never leaves the page: frames are decoded here, in the browser. */
export function QrScanner({
  onRead,
  onClose,
}: {
  onRead: (text: string) => void;
  onClose: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const { t } = useI18n();
  const [problem, setProblem] = useState<Problem | null>(null);
  // The latest callback without restarting the camera when it changes.
  const read = useRef(onRead);
  useEffect(() => {
    read.current = onRead;
  }, [onRead]);

  useEffect(() => {
    let stream: MediaStream | null = null;
    let frame = 0;
    let stopped = false;

    async function start() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setProblem("unsupported");
        return;
      }
      try {
        const [{ default: jsQR }, media] = await Promise.all([
          import("jsqr"),
          navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: "environment" } },
            audio: false,
          }),
        ]);
        stream = media;
        const element = video.current;
        if (stopped || !element) return;
        element.srcObject = media;
        await element.play();

        const canvas = document.createElement("canvas");
        const context = canvas.getContext("2d", { willReadFrequently: true });
        const scan = () => {
          if (stopped) return;
          if (context && element.videoWidth > 0) {
            canvas.width = element.videoWidth;
            canvas.height = element.videoHeight;
            context.drawImage(element, 0, 0, canvas.width, canvas.height);
            const image = context.getImageData(0, 0, canvas.width, canvas.height);
            const code = jsQR(image.data, image.width, image.height, {
              inversionAttempts: "dontInvert",
            });
            if (code?.data) read.current(code.data);
          }
          frame = requestAnimationFrame(scan);
        };
        frame = requestAnimationFrame(scan);
      } catch (error) {
        if (stopped) return;
        const name = error instanceof DOMException ? error.name : "";
        setProblem(name === "NotAllowedError" || name === "SecurityError" ? "denied" : "failed");
      }
    }

    void start();
    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  return (
    <div className="qr-scanner" role="dialog" aria-label={t("qr.scanTitle")}>
      {problem ? (
        <p className="field-error" role="alert">
          {t(MESSAGES[problem])}
        </p>
      ) : (
        <>
          <video ref={video} playsInline muted aria-label={t("qr.camera")} />
          <p className="muted small">{t("qr.point")}</p>
        </>
      )}
      <button type="button" className="button button-small button-ghost" onClick={onClose}>
        {t("qr.close")}
      </button>
    </div>
  );
}
