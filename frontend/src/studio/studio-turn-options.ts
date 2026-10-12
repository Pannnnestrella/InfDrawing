export type PromptStyleOption = "preserve" | "target_only";
export type ImageProviderOption = "dashscope" | "openai";

export interface ImageModelOption {
  provider: ImageProviderOption;
  model: string;
  label: string;
  /** Stable select value: ``provider|model``. */
  key: string;
}

const PROMPT_KEY = "infd.cedit.prompt-style";
const IMAGE_KEY = "infd.cedit.image-option";
const LEGACY_IMAGE_KEY = "infd.cedit.image-provider";
const CHANGE_EVENT = "infd:cedit-options-change";

const PROMPT_LABELS: Record<PromptStyleOption, string> = {
  preserve: "完整约束",
  target_only: "仅描述目标",
};

const PROVIDER_LABELS: Record<ImageProviderOption, string> = {
  dashscope: "通义",
  openai: "OpenAI",
};

function storage(): Storage | null {
  return typeof window === "undefined" ? null : window.sessionStorage;
}

function notifyChange(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function optionLabel(provider: ImageProviderOption, model: string): string {
  if (provider === "dashscope" && model.startsWith("qwen-image-2.1")) {
    return `通义 ${model}（整图）`;
  }
  if (provider === "dashscope") {
    return `通义 ${model}`;
  }
  return `OpenAI ${model}`;
}

/** Subscribe to prompt_style / image option session preference changes. */
export function subscribeCeditOptions(listener: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener(CHANGE_EVENT, listener);
  return () => window.removeEventListener(CHANGE_EVENT, listener);
}

export function promptStyleLabel(style: PromptStyleOption): string {
  return PROMPT_LABELS[style];
}

export function imageProviderLabel(provider: ImageProviderOption): string {
  return PROVIDER_LABELS[provider];
}

export function imageOptionKey(provider: ImageProviderOption, model: string): string {
  return `${provider}|${model}`;
}

export function parseImageOptions(raw: string | undefined): ImageModelOption[] {
  if (!raw?.trim()) return [];
  return raw
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean)
    .flatMap((part) => {
      const [provider, model] = part.split("|");
      if (provider !== "dashscope" && provider !== "openai") return [];
      if (!model) return [];
      return [
        {
          provider,
          model,
          key: imageOptionKey(provider, model),
          label: optionLabel(provider, model),
        },
      ];
    });
}

export function loadPromptStyle(fallback: PromptStyleOption = "preserve"): PromptStyleOption {
  const value = storage()?.getItem(PROMPT_KEY);
  return value === "target_only" || value === "preserve" ? value : fallback;
}

export function savePromptStyle(style: PromptStyleOption): void {
  storage()?.setItem(PROMPT_KEY, style);
  notifyChange();
}

export function loadImageOption(
  options: ImageModelOption[],
  fallbackProvider: ImageProviderOption = "dashscope",
): ImageModelOption | null {
  if (!options.length) return null;
  const stored = storage()?.getItem(IMAGE_KEY);
  if (stored) {
    const match = options.find((option) => option.key === stored);
    if (match) return match;
  }
  const legacy = storage()?.getItem(LEGACY_IMAGE_KEY);
  if (legacy === "dashscope" || legacy === "openai") {
    const match = options.find((option) => option.provider === legacy);
    if (match) return match;
  }
  return (
    options.find((option) => option.provider === fallbackProvider) ?? options[0] ?? null
  );
}

/** @deprecated Prefer {@link loadImageOption}; kept for Settings hydration. */
export function loadImageProvider(
  options: ImageModelOption[],
  fallback: ImageProviderOption = "dashscope",
): ImageProviderOption {
  return loadImageOption(options, fallback)?.provider ?? fallback;
}

export function saveImageOption(option: ImageModelOption): void {
  storage()?.setItem(IMAGE_KEY, option.key);
  storage()?.setItem(LEGACY_IMAGE_KEY, option.provider);
  notifyChange();
}

export function saveImageProvider(provider: ImageProviderOption): void {
  storage()?.setItem(LEGACY_IMAGE_KEY, provider);
  notifyChange();
}
