/** Shared execution path for generation pipelines.
 *
 * Both the sidebar chat flows and the canvas overlays run through
 * `runPipeline`: submit → track task events → handle the terminal result.
 * Callers only differ in how they surface status/error text.
 */

import type { DecomposeLayer, TextEditOverlay } from "./api-types";
import { exportSelectedImageFile, pasteLayersToCanvas } from "./canvas-bridge";
import { submitDecompose } from "./api";
import { runGenerateTask } from "./generate-task";
import { STEP_LABELS } from "./pipeline-steps";

export interface PipelineResult {
  imageUrl: string;
  layers?: DecomposeLayer[];
  overlay?: TextEditOverlay;
}

export interface PipelineSpec {
  /** Status line shown right after the task is accepted. */
  submittedStatus: string;
  /** Fallback status while running when the step has no label. */
  runningStatus: string;
  /** Per-pipeline overrides merged over the shared STEP_LABELS. */
  stepLabels?: Record<string, string>;
  /** Gather inputs and POST; throw Error(message) to abort with a user-facing message. */
  submit: () => Promise<{ task_id: string }>;
  /** Handle the terminal result (e.g. paste to canvas); throw to surface an error. */
  complete: (result: PipelineResult) => Promise<void>;
}

export interface PipelineHandlers {
  onStatus: (text: string) => void;
  onError: (message: string) => void;
  onReconnect?: (attempt: number) => void;
  /** Called exactly once when the pipeline settles (success or failure). */
  onSettled?: () => void;
}

export async function runPipeline(
  spec: PipelineSpec,
  handlers: PipelineHandlers,
): Promise<void> {
  const { onStatus, onError, onReconnect, onSettled } = handlers;

  let taskId: string;
  try {
    const { task_id } = await spec.submit();
    taskId = task_id;
  } catch (err) {
    onError(err instanceof Error ? err.message : "任务提交失败");
    onSettled?.();
    return;
  }

  onStatus(spec.submittedStatus);
  const labels = { ...STEP_LABELS, ...spec.stepLabels };

  runGenerateTask(taskId, {
    onProgress: (step) => onStatus((step && labels[step]) || spec.runningStatus),
    onReconnect,
    onComplete: async (imageUrl, layers, overlay) => {
      try {
        await spec.complete({ imageUrl, layers, overlay });
      } catch (err) {
        onError(err instanceof Error ? err.message : "结果处理失败");
      }
      onSettled?.();
    },
    onError: (message) => {
      onError(message);
      onSettled?.();
    },
  });
}

/** Export the selected canvas image and submit a decompose task. */
export async function submitDecomposeFromSelection(backgroundPrompt?: string) {
  const imageFile = await exportSelectedImageFile();
  if (!imageFile) {
    throw new Error("请先在画布上选中一张图片");
  }
  return submitDecompose(imageFile, backgroundPrompt);
}

/** Paste decompose layers at the anchor; returns the layer count. */
export async function pasteDecomposeResult(
  result: PipelineResult,
  anchor: { pageX: number; pageY: number },
): Promise<number> {
  if (!result.layers?.length) {
    throw new Error("未收到图层数据");
  }
  const pasted = await pasteLayersToCanvas(result.layers, anchor);
  if (!pasted) {
    throw new Error("拆解成功，但回贴画布失败");
  }
  return result.layers.length;
}
