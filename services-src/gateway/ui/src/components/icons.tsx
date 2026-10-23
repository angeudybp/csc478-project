// Small stroke icons, drawn inline so the UI needs no icon package or network access.
import type { SVGProps } from "react";

const base = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export function DownloadIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19h14" />
    </svg>
  );
}

export function UploadIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <path d="M12 16V5m0 0L7.5 9.5M12 5l4.5 4.5M5 19h14" />
    </svg>
  );
}

/** Camera aperture: the app's mark. */
export function ApertureIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M14.3 3.3 9 12.5M20.6 9.4h-10.6M17.6 18.7 12.3 9.5M9.7 20.7 15 11.5M3.4 14.6H14M6.4 5.3l5.3 9.2" />
    </svg>
  );
}
