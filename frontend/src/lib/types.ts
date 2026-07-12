import { type HITLRequest } from "@/components/thread/agent-inbox/types";

// ─── LangGraph message types (defined locally — no SDK runtime dependency) ───

export interface MessageContentText {
  type: "text";
  text: string;
}

export interface MessageContentImageUrl {
  type: "image_url";
  image_url: { url: string };
}

export type MessageContent = string | (MessageContentText | Record<string, unknown>)[];

export interface ToolCall {
  id?: string;
  name: string;
  args: Record<string, unknown>;
  type?: "tool_call";
}

export interface BaseMessage {
  id?: string;
  type: string;
  content: MessageContent;
}

export interface HumanMessageType extends BaseMessage {
  type: "human";
}

export interface AIMessageType extends BaseMessage {
  type: "ai";
  tool_calls?: ToolCall[];
}

export interface ToolMessageType extends BaseMessage {
  type: "tool";
  tool_call_id: string;
  name?: string;
}

export type Message = HumanMessageType | AIMessageType | ToolMessageType | BaseMessage;

export interface ToolMessageCreate {
  type: "tool";
  tool_call_id: string;
  id: string;
  name: string;
  content: string;
}

// Checkpoint (used as no-op in this backend)
export type Checkpoint = unknown;

// UIMessage (used as no-op — no LangGraph cloud generative UI)
export interface UIMessage {
  id: string;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

// Interrupt shape from FastAPI SSE stream
export interface Interrupt<T = unknown> {
  id?: string;
  value: T;
}

// ─── Thread summary from GET /threads ────────────────────────────────────────

export interface ThreadSummary {
  thread_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

// ─── Artifact from GET /threads/{id}/artifacts ────────────────────────────────

export type ArtifactStatus = "uploaded" | "indexing" | "indexed" | "failed";

export interface Artifact {
  id: string;
  thread_id: string;
  filename: string;
  mime_type: string;
  status: ArtifactStatus;
  error_message: string | null;
  created_at: string;
}

// ─── Decision types ───────────────────────────────────────────────────────────

export interface Decision {
  type: "approve" | "reject" | "edit";
  message?: string;
  edited_action?: {
    name: string;
    args: Record<string, unknown>;
  };
}

export interface SubmitOptions {
  command?: {
    resume?: { decisions: Decision[] };
    goto?: string;
  };
  [key: string]: unknown;
}

export interface MessagesMetadata {
  branch: undefined;
  branchOptions: undefined;
  firstSeenState: { parent_checkpoint: undefined; values?: unknown };
}

// ─── Stream context ───────────────────────────────────────────────────────────

export interface StreamContextValue {
  messages: Message[];
  isLoading: boolean;
  interrupt: Interrupt<HITLRequest> | Interrupt<HITLRequest>[] | undefined;
  values: {
    messages: Message[];
    ui: UIMessage[];
  };
  submit: (
    input: { messages?: Message[]; context?: Record<string, unknown> } | undefined,
    options?: SubmitOptions,
  ) => void;
  stop: () => void;
  getMessagesMetadata: (message: Message) => MessagesMetadata | undefined;
  error: Error | undefined;
  setBranch: (branch: string) => void;
  loadThread: (threadId: string) => Promise<void>;
}
