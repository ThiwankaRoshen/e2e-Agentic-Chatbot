import { v4 as uuidv4 } from "uuid";
import { type Message, type ToolMessageCreate } from "@/lib/types";

export const DO_NOT_RENDER_ID_PREFIX = "do-not-render-";

export function ensureToolCallsHaveResponses(messages: Message[]): Message[] {
  const newMessages: ToolMessageCreate[] = [];

  messages.forEach((message, index) => {
    if (message.type !== "ai") return;
    const aiMsg = message as import("@/lib/types").AIMessageType;
    if (!aiMsg.tool_calls?.length) return;

    const followingMessage = messages[index + 1];
    if (followingMessage && followingMessage.type === "tool") return;

    newMessages.push(
      ...(aiMsg.tool_calls?.map((tc) => ({
        type: "tool" as const,
        tool_call_id: tc.id ?? "",
        id: `${DO_NOT_RENDER_ID_PREFIX}${uuidv4()}`,
        name: tc.name,
        content: "Successfully handled tool call.",
      })) ?? []),
    );
  });

  return newMessages as unknown as Message[];
}
