import React, {
  createContext,
  useContext,
  useEffect,
  ReactNode,
  useState,
  useCallback,
  useRef,
} from "react";
import {
  type Message,
  type Interrupt,
  type UIMessage,
  type StreamContextValue,
} from "@/lib/types";
// END sentinel — matches @langchain/langgraph END value
const END = "__end__";
import { parseSSE } from "@/lib/sse-parser";
import { useThreads } from "./Thread";
import { type HITLRequest } from "@/components/thread/agent-inbox/types";

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Apply a streaming token chunk to the message list.
 *
 * The backend emits "messages" SSE events as [message_dict, metadata] tuples
 * where message_dict carries the real LangGraph message id. We use that id
 * as a stable key so that consecutive token chunks for the same AI message
 * accumulate into the same bubble, and a new bubble is created for each
 * distinct AI message id.
 */
function applyMessageChunk(
  messages: Message[],
  chunk: { id: string; type: string; content: string; tool_calls?: unknown[] },
): Message[] {
  const chunkId = chunk.id || "__streaming__";
  const existingIdx = messages.findIndex((m) => m.id === chunkId);

  if (existingIdx >= 0) {
    // Append token to existing streaming bubble
    const updated = [...messages];
    updated[existingIdx] = {
      ...updated[existingIdx],
      content: (updated[existingIdx].content as string) + chunk.content,
    };
    return updated;
  }

  // New streaming bubble — append to the list
  return [
    ...messages,
    { id: chunkId, type: "ai", content: chunk.content } as Message,
  ];
}

// ─────────────────────────────────────────────────────────────────────────────
// Context
// ─────────────────────────────────────────────────────────────────────────────

export const StreamContext = createContext<StreamContextValue | undefined>(
  undefined,
);

// ─────────────────────────────────────────────────────────────────────────────
// Core hook
// ─────────────────────────────────────────────────────────────────────────────

function useSSEStream(
  apiBase: string,
  setActiveThreadId: (id: string | null) => void,
  resetSignal: number,
): StreamContextValue {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [interrupt, setInterrupt] = useState<
    Interrupt<HITLRequest> | undefined
  >(undefined);
  const [error, setError] = useState<Error | undefined>(undefined);

  const abortRef = useRef<AbortController | null>(null);
  const threadIdRef = useRef<string | null>(null);

  const { getThreads, setThreads } = useThreads();

  // Reset all state when resetSignal increments (new thread)
  useEffect(() => {
    abortRef.current?.abort();
    threadIdRef.current = null;
    setMessages([]);
    setIsLoading(false);
    setInterrupt(undefined);
    setError(undefined);
  }, [resetSignal]);

  const submit = useCallback(
    (
      input:
        | { messages?: Message[]; context?: Record<string, unknown> }
        | undefined,
      options?: {
        command?: {
          resume?: { decisions: unknown[] };
          goto?: string;
        };
        [key: string]: unknown;
      },
    ) => {
      // Branch 1: Resume after interrupt
      if (options?.command?.resume) {
        const threadId = threadIdRef.current;
        if (!threadId) {
          setError(new Error("Cannot resume: no active thread"));
          return;
        }
        fetch(`${apiBase}/threads/${threadId}/runs/resume`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decisions: options.command.resume.decisions }),
        })
          .then((res) => {
            if (!res.ok) throw new Error(`Resume failed: ${res.status}`);
            setInterrupt(undefined);
            setIsLoading(true);
          })
          .catch((err) => {
            setIsLoading(false);
            setError(err instanceof Error ? err : new Error(String(err)));
          });
        return;
      }

      // Branch 2: goto END
      if (options?.command?.goto === END) {
        setInterrupt(undefined);
        setIsLoading(false);
        return;
      }

      // Branch 3: Normal submit
      setIsLoading(true);
      setError(undefined);

      const ctrl = new AbortController();
      abortRef.current = ctrl;

      const threadIdParam = threadIdRef.current ?? "new";
      const msgs: Message[] = input?.messages ?? [];

      // Optimistically render human messages immediately so the UI feels
      // responsive before the first SSE event arrives.
      const humanMsgs = msgs.filter((m) => m.type === "human");
      if (humanMsgs.length > 0) {
        setMessages((prev) => {
          const existingIds = new Set(prev.map((m) => m.id));
          const toAdd = humanMsgs.filter(
            (m) => !m.id || !existingIds.has(m.id),
          );
          return toAdd.length ? [...prev, ...toAdd] : prev;
        });
      }

      const extractContent = (content: unknown): string => {
        if (typeof content === "string") return content;
        if (Array.isArray(content)) {
          const hasNonText = content.some(
            (c: { type?: string }) => c.type !== "text",
          );
          if (!hasNonText)
            return content.map((c: { text?: string }) => c.text ?? "").join("\n");
        }
        return JSON.stringify(content);
      };

      const body = {
        messages: msgs.map((m) => ({
          type: m.type,
          content: extractContent(m.content),
        })),
      };

      (async () => {
        try {
          const res = await fetch(
            `${apiBase}/threads/${threadIdParam}/runs/stream`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
              signal: ctrl.signal,
            },
          );

          if (!res.ok) throw new Error(`Stream failed: ${res.status}`);

          const reader = res.body!.getReader();

          for await (const { event, data } of parseSSE(reader)) {
            if (event === "thread_id") {
              // Backend resolved "new" → a real UUID
              const tid = (data as { thread_id: string }).thread_id;
              threadIdRef.current = tid;
              setActiveThreadId(tid);
              getThreads().then(setThreads).catch(console.error);
            } else if (event === "messages") {
              // Token-streaming event: [message_dict, metadata]
              // Drive the per-message streaming bubble using the real message id.
              const [msgChunk] = data as [
                {
                  id: string;
                  type: string;
                  content: string;
                  tool_calls?: unknown[];
                },
                unknown,
              ];
              if (msgChunk?.content) {
                setMessages((prev) => applyMessageChunk(prev, msgChunk));
              }
            } else if (event === "values") {
              // Full authoritative state snapshot after every graph step.
              // Includes ALL messages: human + AI + tool. Replace state directly.
              // This eliminates all merge/disappear bugs because the backend
              // always sends the complete picture.
              const valuesData = data as { messages?: Message[] };
              if (valuesData?.messages) {
                setMessages(valuesData.messages);
              }
            } else if (event === "interrupt") {
              setInterrupt(data as Interrupt<HITLRequest>);
              setIsLoading(false);
            } else if (event === "done") {
              setInterrupt(undefined);
              setIsLoading(false);
            } else if (event === "error") {
              setError(
                new Error(
                  (data as { message: string }).message ?? "Unknown error",
                ),
              );
              setIsLoading(false);
            }
          }
          setIsLoading(false);
        } catch (err) {
          if ((err as Error)?.name === "AbortError") return;
          setError(err instanceof Error ? err : new Error(String(err)));
          setIsLoading(false);
        }
      })();
    },
    [apiBase, getThreads, setActiveThreadId, setThreads],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setIsLoading(false);
  }, []);

  const getMessagesMetadata = useCallback(
    (_message: Message) => ({
      branch: undefined,
      branchOptions: undefined,
      firstSeenState: { parent_checkpoint: undefined },
    }),
    [],
  );

  const setBranch = useCallback((_branch: string) => {
    // no-op
  }, []);

  const loadThread = useCallback(
    async (threadId: string): Promise<void> => {
      threadIdRef.current = threadId;
      setActiveThreadId(threadId);
      setIsLoading(true);
      setError(undefined);

      try {
        const res = await fetch(`${apiBase}/threads/${threadId}/state`);
        if (!res.ok) throw new Error(`Failed to load thread: ${res.status}`);
        const data: { thread_id: string; messages: Message[] } =
          await res.json();
        setMessages(data.messages ?? []);
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)));
      } finally {
        setIsLoading(false);
      }
    },
    [apiBase, setActiveThreadId],
  );

  const values: { messages: Message[]; ui: UIMessage[] } = {
    messages,
    ui: [],
  };

  return {
    messages,
    isLoading,
    interrupt,
    error,
    values,
    submit,
    stop,
    getMessagesMetadata,
    setBranch,
    loadThread,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Provider
// ─────────────────────────────────────────────────────────────────────────────

interface StreamProviderProps {
  children: ReactNode;
  activeThreadId: string | null;
  setActiveThreadId: (id: string | null) => void;
  resetSignal: number;
}

export const StreamProvider: React.FC<StreamProviderProps> = ({
  children,
  activeThreadId: _activeThreadId,
  setActiveThreadId,
  resetSignal,
}) => {
  const apiBase = import.meta.env.VITE_FASTAPI_URL ?? "http://localhost:8000";
  const streamValue = useSSEStream(apiBase, setActiveThreadId, resetSignal);

  return (
    <StreamContext.Provider value={streamValue}>
      {children}
    </StreamContext.Provider>
  );
};

export const useStreamContext = (): StreamContextValue => {
  const context = useContext(StreamContext);
  if (context === undefined) {
    throw new Error("useStreamContext must be used within a StreamProvider");
  }
  return context;
};

export default StreamContext;
