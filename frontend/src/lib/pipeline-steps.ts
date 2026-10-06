/** Human-readable labels for backend pipeline `step` events (single source). */
export const STEP_LABELS: Record<string, string> = {
  generating: "生成中…",
  segmenting: "分割主体…",
  extracting: "提取前景…",
  inpainting: "补全背景…",
  masking: "准备文字区域…",
  cloud_submit: "提交云端任务…",
  cloud_poll: "等待云端结果…",
  cloud_download: "下载云端结果…",
};
