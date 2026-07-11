import { useEffect, useState } from "react";

import type { ChatMode } from "@/agent-panel/types";
import {
  featureReason,
  fetchCapabilities,
  isModeEnabled,
  type CapabilitiesResponse,
} from "@/lib/capabilities";

export function useCapabilities(mode: ChatMode) {
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);

  useEffect(() => {
    void fetchCapabilities()
      .then(setCapabilities)
      .catch(() => setCapabilities(null));
  }, []);

  const modeEnabled = isModeEnabled(capabilities, mode);
  const modeDisabledReason = featureReason(capabilities, mode);

  return { capabilities, modeEnabled, modeDisabledReason };
}
