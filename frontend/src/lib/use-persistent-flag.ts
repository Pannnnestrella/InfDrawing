import { useCallback, useSyncExternalStore } from "react";

const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((fn) => fn());
}

function subscribe(callback: () => void): () => void {
  listeners.add(callback);
  return () => {
    listeners.delete(callback);
  };
}

/** localStorage-backed boolean that hydrates safely (server renders the default). */
export function usePersistentFlag(key: string, defaultValue: boolean) {
  const getSnapshot = useCallback(() => {
    const stored = window.localStorage.getItem(key);
    return stored === null ? defaultValue : stored === "1";
  }, [key, defaultValue]);

  const value = useSyncExternalStore(subscribe, getSnapshot, () => defaultValue);

  const setValue = useCallback(
    (next: boolean) => {
      window.localStorage.setItem(key, next ? "1" : "0");
      emit();
    },
    [key],
  );

  return [value, setValue] as const;
}
