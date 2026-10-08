import { useEffect, useRef, useState } from "react";

/** How wide a chart has to draw itself, so its text stays one size on
 * a phone and on a desktop instead of scaling with the picture. */
export function useWidth(fallback: number) {
  const element = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const node = element.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry && entry.contentRect.width > 0) setWidth(entry.contentRect.width);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [element, width] as const;
}
