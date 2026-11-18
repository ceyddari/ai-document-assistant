const ICONS = {
  plus: "M12 5v14M5 12h14",
  upload: "M12 15V4m0 0L8 8m4-4 4 4M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3",
  send: "M12 19V5m0 0-6 6m6-6 6 6",
  stop: "M8 8h8v8H8z",
  panelLeft: "M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM9.5 4v16",
  panelRight: "M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM14.5 4v16",
  logout: "M14 12H4m0 0 3.5-3.5M4 12l3.5 3.5M12 4h6a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6",
  file: "M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM14 3v5h5M9.5 13h5M9.5 16.5h5",
  retry: "M20 11a8 8 0 0 0-14.3-4.9L4 8m0-4v4h4M4 13a8 8 0 0 0 14.3 4.9L20 16m0 4v-4h-4",
  close: "M6 6l12 12M18 6 6 18",
  chevron: "M9 6l6 6-6 6",
  folder: "M3.5 7a1.5 1.5 0 0 1 1.5-1.5h4l2 2h8a1.5 1.5 0 0 1 1.5 1.5v8.5a1.5 1.5 0 0 1-1.5 1.5H5a1.5 1.5 0 0 1-1.5-1.5z",
  check: "M5 12.5 10 17 19 7",
  home: "M4 11.5 12 5l8 6.5M6.5 10v9h11v-9M10 19v-5h4v5",
  arrowUpRight: "M7 7h10v10M7 17 17 7",
  arrowRight: "M5 12h14m0 0-6-6m6 6-6 6",
  chat: "M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-8l-4.5 3.5V16H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z",
  trash: "M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 12.5h9l1-12.5M10.2 11v5M13.8 11v5",
  pencil: "M4 20h4.2L19 9.2 14.8 5 4 15.8zM12.8 7l4.2 4.2",
  external: "M14 4h6v6M20 4l-8.5 8.5M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5",
  thumbUp: "M7.5 11v9H4.5v-9zm0 0 3.8-6.6a1.9 1.9 0 0 1 3.5 1.3L14 10h4.6a1.9 1.9 0 0 1 1.9 2.3l-1.3 6.1A2 2 0 0 1 17.2 20H7.5",
  thumbDown: "M7.5 13V4H4.5v9zm0 0 3.8 6.6a1.9 1.9 0 0 0 3.5-1.3L14 14h4.6a1.9 1.9 0 0 0 1.9-2.3l-1.3-6.1A2 2 0 0 0 17.2 4H7.5",
} as const;

export type IconName = keyof typeof ICONS;

export function Icon({ name }: { name: IconName }) {
  return <svg className="icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[name]} /></svg>;
}
