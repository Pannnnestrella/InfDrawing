import { useEffect, useState } from "react";

import type { ChatMode } from "@/agent-panel/types";
import {
  featureReason,
  fetchCapabilities,
  isModeEnabled,
  type CapabilitiesResponse,
} from "@/lib/capabilities";

function modeFeatureKey(mode: ChatMode) {
  if (mode === "txt2img") return "txt2img" as const;
  if (mode === "inpaint") return "inpaint" as const;
  if (mode === "decompose") return "decompose" as const;
  return "text_edit" as const;
}

export function useCapabilities(mode: ChatMode) {
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);

  useEffect(() => {
    void fetchCapabilities()
      .then(setCapabilities)
      .catch(() => setCapabilities(null));
  }, []);

  const modeEnabled = isModeEnabled(capabilities, mode);
  const modeDisabledReason = featureReason(capabilities, modeFeatureKey(mode));

  return { capabilities, modeEnabled, modeDisabledReason };
}
