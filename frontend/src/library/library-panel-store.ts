/** Open/close the floating asset library panel and broadcast data refreshes. */

type Listener = () => void;

const panelListeners = new Set<Listener>();
const dataListeners = new Set<Listener>();
let panelOpen = false;
let dataRevision = 0;

function notify(listeners: Set<Listener>): void {
  listeners.forEach((fn) => fn());
}

export function subscribeLibraryPanel(listener: Listener): () => void {
  panelListeners.add(listener);
  return () => {
    panelListeners.delete(listener);
  };
}

/** Subscribe to ingest/delete/etc. so an already-open panel reloads. */
export function subscribeLibraryData(listener: Listener): () => void {
  dataListeners.add(listener);
  return () => {
    dataListeners.delete(listener);
  };
}

export function isLibraryPanelOpen(): boolean {
  return panelOpen;
}

export function getLibraryDataRevision(): number {
  return dataRevision;
}

export function setLibraryPanelOpen(open: boolean): void {
  if (panelOpen === open) return;
  panelOpen = open;
  notify(panelListeners);
}

export function openLibraryPanel(): void {
  setLibraryPanelOpen(true);
}

/** Bump after the library contents change so open panels refresh. */
export function notifyLibraryDataChanged(): void {
  dataRevision += 1;
  notify(dataListeners);
}
