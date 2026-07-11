import { type Message, type Interrupt } from "@langchain/langgraph-sdk";
import { type UIMessage } from "@langchain/langgraph-sdk/react-ui";
import { type HITLRequest } from "@/components/thread/agent-inbox/types";

export interface ThreadSummary {
  thread_id: string;
  created_at: string;
  first_message: string;
}

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
  firstSeenState: { parent_checkpoint: undefined; values?: any };
}

export interface StreamContextValue {
  messages: Message[];
  isLoading: boolean;
  interrupt: Interrupt<HITLRequest> | Interrupt<HITLRequest>[] | undefined;
  values: {
    messages: Message[];
    ui: UIMessage[];
  };
  submit: (
    input:
      | { messages?: Message[]; context?: Record<string, unknown> }
      | undefined,
    options?: SubmitOptions,
  ) => void;
  stop: () => void;
  getMessagesMetadata: (message: Message) => MessagesMetadata | undefined;
  error: Error | undefined;
  setBranch: (branch: string) => void;
}
