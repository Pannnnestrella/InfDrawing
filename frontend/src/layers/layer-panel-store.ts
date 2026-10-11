/** Open/close the floating layers panel (mirrors library-panel-store). */

type Listener = () => void;

const panelListeners = new Set<Listener>();
let panelOpen = false;

function notify(listeners: Set<Listener>): void {
  listeners.forEach((fn) => fn());
}

export function subscribeLayerPanel(listener: Listener): () => void {
  panelListeners.add(listener);
  return () => {
    panelListeners.delete(listener);
  };
}

export function isLayerPanelOpen(): boolean {
  return panelOpen;
}

export function setLayerPanelOpen(open: boolean): void {
  if (panelOpen === open) return;
  panelOpen = open;
  notify(panelListeners);
}

export function openLayerPanel(): void {
  setLayerPanelOpen(true);
}
