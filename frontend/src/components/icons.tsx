import type { ReactNode } from "react";

/** The site's icons: one line-drawn set on a 24px grid, drawn in the
 * current text colour. Inline SVG rather than an icon font or a library:
 * nothing to download, nothing for the CSP to allow. Always decorative —
 * the text next to an icon says what it means. */
function Svg({ children, size = 22, className }: { children: ReactNode; size?: number; className?: string }) {
  return (
    <svg
      className={className ?? "icon"}
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

type IconProps = { size?: number; className?: string };

export const WalletIcon = (props: IconProps) => (
  <Svg {...props}>
    <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H18a2 2 0 0 1 2 2v1" />
    <path d="M3 7.5V17a3 3 0 0 0 3 3h13a2 2 0 0 0 2-2V10a2 2 0 0 0-2-2H5.5A2.5 2.5 0 0 1 3 7.5Z" />
    <circle cx="16.5" cy="14" r="1.2" fill="currentColor" stroke="none" />
  </Svg>
);

export const SendIcon = (props: IconProps) => (
  <Svg {...props}>
    <path d="M21 3 10.5 13.5" />
    <path d="M21 3 14.5 21l-4-7.5L3 9.5 21 3Z" />
  </Svg>
);

export const PayIcon = (props: IconProps) => (
  <Svg {...props}>
    <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
    <path d="M2.5 10h19M6.5 15h4" />
  </Svg>
);

export const HistoryIcon = (props: IconProps) => (
  <Svg {...props}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3.5 2" />
  </Svg>
);

export const ShopIcon = (props: IconProps) => (
  <Svg {...props}>
    <path d="M4 9.5 5.2 4h13.6L20 9.5" />
    <path d="M4 9.5a2.7 2.7 0 0 0 5.3 0 2.7 2.7 0 0 0 5.4 0 2.7 2.7 0 0 0 5.3 0" />
    <path d="M5.5 12.5V20h13v-7.5M10 20v-4.5h4V20" />
  </Svg>
);

export const GoalIcon = (props: IconProps) => (
  <Svg {...props}>
    <circle cx="12" cy="12" r="9" />
    <circle cx="12" cy="12" r="5" />
    <circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none" />
  </Svg>
);

export const RequestIcon = (props: IconProps) => (
  <Svg {...props}>
    <path d="M17 7 7 17M7 9v8h8" />
    <path d="M4 21h16" />
  </Svg>
);

export const ExchangeIcon = (props: IconProps) => (
  <Svg {...props}>
    <path d="M4 8h13l-3.5-3.5M20 16H7l3.5 3.5" />
  </Svg>
);

export const PhoneIcon = (props: IconProps) => (
  <Svg {...props}>
    <rect x="6.5" y="2.5" width="11" height="19" rx="2.5" />
    <path d="M10.5 18h3" />
  </Svg>
);

export const GlobeIcon = (props: IconProps) => (
  <Svg {...props}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3Z" />
  </Svg>
);

export const BoltIcon = (props: IconProps) => (
  <Svg {...props}>
    <path d="M13 2.5 4.5 13.5H12l-1 8 8.5-11H12l1-8Z" />
  </Svg>
);

export const TvIcon = (props: IconProps) => (
  <Svg {...props}>
    <rect x="2.5" y="5" width="19" height="13" rx="2" />
    <path d="M8 21h8M9 2.5l3 2.5 3-2.5" />
  </Svg>
);

export const SignOutIcon = (props: IconProps) => (
  <Svg {...props}>
    <path d="M9 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3" />
    <path d="M15 8l4 4-4 4M19 12H9" />
  </Svg>
);

export const ChatIcon = (props: IconProps) => (
  <Svg {...props}>
    <path d="M20 11.5a7.5 7.5 0 0 1-11 6.6L4 19.5l1.4-4.6A7.5 7.5 0 1 1 20 11.5Z" />
    <path d="M8.5 11.5h.01M12 11.5h.01M15.5 11.5h.01" strokeWidth="2.6" />
  </Svg>
);
