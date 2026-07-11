import { useCallback } from "react";

import { runPipeline, type PipelineResult } from "@/lib/run-pipeline";

import type { FlowCallbacks } from "./flow-types";

export interface FlowSpec<Input> {
  submittedStatus: string;
  runningStatus: string;
  stepLabels?: Record<string, string>;
  /** Gather inputs and POST; throw Error(message) for user-facing validation failures. */
  submit: (prompt: string, input: Input) => Promise<{ task_id: string }>;
  /** Handle the terminal result; throw to surface an error message. */
  complete: (
    result: PipelineResult,
    input: Input,
    callbacks: FlowCallbacks,
  ) => Promise<void>;
}

/** Shared chat-flow skeleton: submit → track events → complete, owning busy state. */
export function useGenerateFlow<Input = void>(
  callbacks: FlowCallbacks,
  spec: FlowSpec<Input>,
) {
  const execute = useCallback(
    async (prompt: string, input: Input) => {
      await runPipeline(
        {
          submittedStatus: spec.submittedStatus,
          runningStatus: spec.runningStatus,
          stepLabels: spec.stepLabels,
          submit: () => spec.submit(prompt, input),
          complete: (result) => spec.complete(result, input, callbacks),
        },
        {
          onStatus: callbacks.appendStatus,
          onError: callbacks.appendError,
          onReconnect: callbacks.notifyReconnect,
          onSettled: () => callbacks.setBusy(false),
        },
      );
    },
    [callbacks, spec],
  );

  return { execute };
}
