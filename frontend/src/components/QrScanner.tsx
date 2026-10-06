import { useEffect, useRef, useState } from "react";

type Problem = "unsupported" | "denied" | "failed";

const MESSAGES: Record<Problem, string> = {
  unsupported: "This browser can\u2019t use the camera here. Type the card number instead.",
  denied: "Camera access was refused. Allow it for this site, or type the card number instead.",
  failed: "The camera couldn\u2019t be started. Type the card number instead.",
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
    <div className="qr-scanner" role="dialog" aria-label="Scan a QR code">
      {problem ? (
        <p className="field-error" role="alert">
          {MESSAGES[problem]}
        </p>
      ) : (
        <>
          <video ref={video} playsInline muted aria-label="Camera" />
          <p className="muted small">Point the camera at a FinCore QR code.</p>
        </>
      )}
      <button type="button" className="button button-small button-ghost" onClick={onClose}>
        Close camera
      </button>
    </div>
  );
}
