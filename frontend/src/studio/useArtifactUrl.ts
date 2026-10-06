"use client";

import { useEffect, useState } from "react";

import { fetchArtifactBlobUrl } from "@/lib/controlled-edit-api";

const cache = new Map<string, Promise<string>>();

function loadArtifact(artifactId: string): Promise<string> {
  let pending = cache.get(artifactId);
  if (!pending) {
    pending = fetchArtifactBlobUrl(artifactId);
    cache.set(artifactId, pending);
    pending.catch(() => cache.delete(artifactId));
  }
  return pending;
}

/** Resolve an immutable artifact id to a cached blob URL (null while loading). */
export function useArtifactUrl(artifactId: string | null): string | null {
  const [loaded, setLoaded] = useState<{ id: string; url: string } | null>(null);

  useEffect(() => {
    if (!artifactId) return;
    let alive = true;
    loadArtifact(artifactId)
      .then((url) => {
        if (alive) setLoaded({ id: artifactId, url });
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [artifactId]);

  return artifactId && loaded?.id === artifactId ? loaded.url : null;
}
