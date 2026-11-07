type IconName =
  | "check"
  | "warning"
  | "alert"
  | "sensor"
  | "search"
  | "clock"
  | "trend"
  | "refresh"
  | "back"
  | "help"
  | "euro"
  | "shield"
  | "download"
  | "upload";

interface Props {
  name: IconName;
  size?: number;
  className?: string;
}

const PATHS: Record<IconName, string> = {
  check: "M20 6 9 17l-5-5",
  warning: "M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z",
  alert: "M12 8v4m0 4h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  sensor: "M12 12m-2 0a2 2 0 1 0 4 0 2 2 0 1 0-4 0M16.2 7.8a6 6 0 0 1 0 8.4M7.8 16.2a6 6 0 0 1 0-8.4M19.1 4.9a10 10 0 0 1 0 14.2M4.9 19.1a10 10 0 0 1 0-14.2",
  search: "m21 21-4.3-4.3M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Z",
  clock: "M12 6v6l4 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  trend: "M22 7 13.5 15.5 8.5 10.5 2 17M16 7h6v6",
  refresh: "M21 12a9 9 0 0 1-15.5 6.2L3 16m0 5v-5h5M3 12a9 9 0 0 1 15.5-6.2L21 8m0-5v5h-5",
  back: "M19 12H5m7 7-7-7 7-7",
  help: "M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3m.1 4h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  euro: "M4 10h12M4 14h9m6-8.5A7.5 7.5 0 1 0 19 18.5",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z",
  download: "M12 3v12m0 0 4-4m-4 4-4-4M5 21h14",
  upload: "M12 15V3m0 0 4 4m-4-4-4 4M5 21h14",
};

export function Icon({ name, size = 18, className }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
