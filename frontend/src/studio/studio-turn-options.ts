export type PromptStyleOption = "preserve" | "target_only";
export type ImageProviderOption = "dashscope" | "openai";

export interface ImageModelOption {
  provider: ImageProviderOption;
  model: string;
  label: string;
}

const PROMPT_KEY = "infd.cedit.prompt-style";
const IMAGE_KEY = "infd.cedit.image-provider";

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

export function promptStyleLabel(style: PromptStyleOption): string {
  return PROMPT_LABELS[style];
}

export function imageProviderLabel(provider: ImageProviderOption): string {
  return PROVIDER_LABELS[provider];
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
          label: `${PROVIDER_LABELS[provider]} ${model}`,
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
}

export function loadImageProvider(
  options: ImageModelOption[],
  fallback: ImageProviderOption = "dashscope",
): ImageProviderOption {
  const value = storage()?.getItem(IMAGE_KEY);
  if (value === "dashscope" || value === "openai") {
    if (options.some((option) => option.provider === value)) return value;
  }
  if (options.some((option) => option.provider === fallback)) return fallback;
  return options[0]?.provider ?? fallback;
}

export function saveImageProvider(provider: ImageProviderOption): void {
  storage()?.setItem(IMAGE_KEY, provider);
}
