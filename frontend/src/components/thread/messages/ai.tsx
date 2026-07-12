import { parsePartialJson } from "@langchain/core/output_parsers";
import { useStreamContext } from "@/providers/Stream";
import { type AIMessageType as AIMessage, type Checkpoint, type Message } from "@/lib/types";
import { getContentString } from "../utils";
import { BranchSwitcher, CommandBar } from "./shared";
import { MarkdownText } from "../markdown-text";
import { cn } from "@/lib/utils";
import { ToolCalls, ToolResult } from "./tool-calls";
import { Fragment } from "react/jsx-runtime";
import { isAgentInboxInterruptSchema } from "@/lib/agent-inbox-interrupt";
import { ThreadView } from "../agent-inbox";
import { GenericInterruptView } from "./generic-interrupt";

// Minimal type for Anthropic streamed tool content blocks
type MessageContentComplex = Record<string, unknown>;

function parseAnthropicStreamedToolCalls(
  content: MessageContentComplex[],
): AIMessage["tool_calls"] {
  const toolCallContents = content.filter((c) => c.type === "tool_use" && c.id);
  return toolCallContents.map((tc) => {
    const toolCall = tc as Record<string, any>;
    let json: Record<string, any> = {};
    if (toolCall?.input) {
      try { json = parsePartialJson(toolCall.input) ?? {}; } catch { /* pass */ }
    }
    return { name: toolCall.name ?? "", id: toolCall.id ?? "", args: json, type: "tool_call" };
  });
}

interface InterruptProps {
  interrupt?: unknown;
  isLastMessage: boolean;
  hasNoAIOrToolMessages: boolean;
}

function Interrupt({ interrupt, isLastMessage, hasNoAIOrToolMessages }: InterruptProps) {
  const fallbackValue = Array.isArray(interrupt)
    ? (interrupt as Record<string, any>[])
    : (((interrupt as { value?: unknown } | undefined)?.value ?? interrupt) as Record<string, any>);

  return (
    <>
      {isAgentInboxInterruptSchema(interrupt) && (isLastMessage || hasNoAIOrToolMessages) && (
        <ThreadView interrupt={interrupt} />
      )}
      {interrupt && !isAgentInboxInterruptSchema(interrupt) && (isLastMessage || hasNoAIOrToolMessages) ? (
        <GenericInterruptView interrupt={fallbackValue} />
      ) : null}
    </>
  );
}

export function AssistantMessage({
  message,
  isLoading,
  hideToolCalls,
  handleRegenerate,
}: {
  message: Message | undefined;
  isLoading: boolean;
  hideToolCalls: boolean;
  handleRegenerate: (parentCheckpoint: Checkpoint | null | undefined) => void;
}) {
  const content = message?.content ?? [];
  const contentString = getContentString(content);
  const thread = useStreamContext();

  const lastMsgId = thread.messages[thread.messages.length - 1]?.id;
  const lastAiMessage = [...thread.messages].reverse().find((m) => m.type === "ai");
  const isLastMessage =
    lastMsgId === message?.id ||
    (!!thread.interrupt && lastAiMessage?.id === message?.id);
  const hasNoAIOrToolMessages = !thread.messages.find((m) => m.type === "ai" || m.type === "tool");
  const meta = message ? thread.getMessagesMetadata(message) : undefined;
  const threadInterrupt = thread.interrupt;
  const parentCheckpoint = meta?.firstSeenState?.parent_checkpoint;

  const anthropicStreamedToolCalls = Array.isArray(content)
    ? parseAnthropicStreamedToolCalls(content as MessageContentComplex[])
    : undefined;

  const hasToolCalls =
    message && "tool_calls" in message && message.tool_calls && message.tool_calls.length > 0;
  const toolCallsHaveContents =
    hasToolCalls && message.tool_calls?.some((tc) => tc.args && Object.keys(tc.args).length > 0);
  const hasAnthropicToolCalls = !!anthropicStreamedToolCalls?.length;
  const isToolResult = message?.type === "tool";

  if (isToolResult && hideToolCalls) return null;

  return (
    <div className="group mr-auto flex w-full items-start gap-2">
      <div className="flex w-full flex-col gap-2">
        {isToolResult ? (
          <>
            <ToolResult message={message} />
            <Interrupt
              interrupt={threadInterrupt}
              isLastMessage={isLastMessage}
              hasNoAIOrToolMessages={hasNoAIOrToolMessages}
            />
          </>
        ) : (
          <>
            {contentString.length > 0 && (
              <div className="py-1">
                <MarkdownText>{contentString}</MarkdownText>
              </div>
            )}

            {!hideToolCalls && (
              <Fragment>
                {(hasToolCalls && toolCallsHaveContents && (
                  <ToolCalls toolCalls={message.tool_calls} />
                )) ||
                  (hasAnthropicToolCalls && (
                    <ToolCalls toolCalls={anthropicStreamedToolCalls} />
                  )) ||
                  (hasToolCalls && <ToolCalls toolCalls={message.tool_calls} />)}
              </Fragment>
            )}

            <Interrupt
              interrupt={threadInterrupt}
              isLastMessage={isLastMessage}
              hasNoAIOrToolMessages={hasNoAIOrToolMessages}
            />
            <div
              className={cn(
                "mr-auto flex items-center gap-2 transition-opacity",
                "opacity-0 group-focus-within:opacity-100 group-hover:opacity-100",
              )}
            >
              <BranchSwitcher
                branch={meta?.branch}
                branchOptions={meta?.branchOptions}
                onSelect={(branch) => thread.setBranch(branch)}
                isLoading={isLoading}
              />
              <CommandBar
                content={contentString}
                isLoading={isLoading}
                isAiMessage={true}
                handleRegenerate={() => handleRegenerate(parentCheckpoint)}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export function AssistantMessageLoading() {
  return (
    <div className="mr-auto flex items-start gap-2">
      <div className="bg-muted flex h-8 items-center gap-1 rounded-2xl px-4 py-2">
        <div className="bg-foreground/50 h-1.5 w-1.5 animate-[pulse_1.5s_ease-in-out_infinite] rounded-full" />
        <div className="bg-foreground/50 h-1.5 w-1.5 animate-[pulse_1.5s_ease-in-out_0.5s_infinite] rounded-full" />
        <div className="bg-foreground/50 h-1.5 w-1.5 animate-[pulse_1.5s_ease-in-out_1s_infinite] rounded-full" />
      </div>
    </div>
  );
}
