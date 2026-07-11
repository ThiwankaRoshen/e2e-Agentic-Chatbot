import React, {
  createContext,
  useContext,
  ReactNode,
  useState,
  useCallback,
  useRef,
} from "react";
import { type Message, type Interrupt } from "@langchain/langgraph-sdk";
import { type UIMessage } from "@langchain/langgraph-sdk/react-ui";
import { END } from "@langchain/langgraph/web";
import { useQueryState } from "nuqs";
import { parseSSE } from "@/lib/sse-parser";
import { useThreads } from "./Thread";
import { type HITLRequest } from "@/components/thread/agent-inbox/types";
import { type StreamContextValue } from "@/lib/types";

// ────────────────────────────────────────────────────────────────────────────
// Helper functions
// ────────────────────────────────────────────────────────────────────────────

/**
 * Append a streaming token to the last AI message, or create a new one if the
 * last message isn't an AI message.
 */
function appendToken(messages: Message[], content: string): Message[] {
  if (messages.length > 0 && messages[messages.length - 1].type === "ai") {
    const last = messages[messages.length - 1];
    const updated = {
      ...last,
      content: (last.content as string) + content,
    };
    return [...messages.slice(0, -1), updated];
  }
  // Start a new streaming AI message (no real id yet — replaced by "message" event)
  return [...messages, { id: "__streaming__", type: "ai", content } as Message];
}

/**
 * Replace an existing message by id, or append it.  Also removes the
 * `__streaming__` placeholder that may have been created by `appendToken`.
 */
function upsertMessage(messages: Message[], msg: Message): Message[] {
  const withoutStreaming = messages.filter((m) => m.id !== "__streaming__");
  const idx = withoutStreaming.findIndex((m) => m.id === msg.id);
  if (idx >= 0) {
    const updated = [...withoutStreaming];
    updated[idx] = msg;
    return updated;
  }
  return [...withoutStreaming, msg];
}

// ────────────────────────────────────────────────────────────────────────────
// Context
// ────────────────────────────────────────────────────────────────────────────

export const StreamContext = createContext<StreamContextValue | undefined>(
  undefined,
);

// ────────────────────────────────────────────────────────────────────────────
// Core hook
// ────────────────────────────────────────────────────────────────────────────

function useSSEStream(apiBase: string): StreamContextValue {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [interrupt, setInterrupt] = useState<
    Interrupt<HITLRequest> | undefined
  >(undefined);
  const [error, setError] = useState<Error | undefined>(undefined);

  const abortRef = useRef<AbortController | null>(null);
  const threadIdRef = useRef<string | null>(null);

  const [, setThreadId] = useQueryState("threadId");
  const { getThreads, setThreads } = useThreads();

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
      // ── Branch 1: Resume after interrupt ──────────────────────────────────
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
            if (!res.ok) {
              throw new Error(`Resume request failed: ${res.status}`);
            }
            setInterrupt(undefined);
            setIsLoading(true);
          })
          .catch((err) => {
            setIsLoading(false);
            setError(err instanceof Error ? err : new Error(String(err)));
          });
        return;
      }

      // ── Branch 2: goto END (mark as resolved) ─────────────────────────────
      if (options?.command?.goto === END) {
        setInterrupt(undefined);
        setIsLoading(false);
        return;
      }

      // ── Branch 3: Normal message submit ───────────────────────────────────
      setIsLoading(true);
      setError(undefined);

      const ctrl = new AbortController();
      abortRef.current = ctrl;

      const threadIdParam = threadIdRef.current ?? "new";
      const msgs: Message[] = input?.messages ?? [];

      // Add human messages to local state so they render immediately
      const humanMsgs = msgs.filter((m) => m.type === "human");
      if (humanMsgs.length > 0) {
        setMessages((prev) => [...prev, ...humanMsgs]);
      }

      // Helper to extract text from a multimodal content array if it only contains text
      const extractContent = (content: any) => {
        if (typeof content === "string") return content;
        if (Array.isArray(content)) {
          // If it's a multimodal array, check if we only have text blocks
          const hasNonText = content.some((c) => c.type !== "text");
          if (!hasNonText) {
            return content.map((c) => c.text).join("\n");
          }
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

          if (!res.ok) {
            throw new Error(`Stream request failed: ${res.status}`);
          }

          const reader = res.body!.getReader();

          for await (const { event, data } of parseSSE(reader)) {
            if (event === "thread_id") {
              const tid = (data as { thread_id: string }).thread_id;
              threadIdRef.current = tid;
              setThreadId(tid);
              // Refresh thread list
              getThreads().then(setThreads).catch(console.error);
            } else if (event === "token") {
              setMessages((prev) =>
                appendToken(prev, (data as { content: string }).content),
              );
            } else if (event === "message") {
              setMessages((prev) => upsertMessage(prev, data as Message));
            } else if (event === "interrupt") {
              setInterrupt(data as Interrupt<HITLRequest>);
              setIsLoading(false);
            } else if (event === "done") {
              setInterrupt(undefined);
              setIsLoading(false);
            } else if (event === "error") {
              setError(
                new Error((data as { message: string }).message ?? "Unknown error"),
              );
              setIsLoading(false);
            }
          }
          setIsLoading(false);
        } catch (err) {
          if ((err as Error)?.name === "AbortError") {
            // User called stop() — not an error
            return;
          }
          setError(err instanceof Error ? err : new Error(String(err)));
          setIsLoading(false);
        }
      })();
    },
    [apiBase, getThreads, setThreadId, setThreads],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setIsLoading(false);
  }, []);

  const getMessagesMetadata = useCallback(
    (
      _message: Message,
    ): {
      branch: undefined;
      branchOptions: undefined;
      firstSeenState: { parent_checkpoint: undefined };
    } => ({
      branch: undefined,
      branchOptions: undefined,
      firstSeenState: { parent_checkpoint: undefined },
    }),
    [],
  );

  const setBranch = useCallback((_branch: string) => {
    // no-op — branch switching is not supported in the custom SSE implementation
  }, []);

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
  };
}

// ────────────────────────────────────────────────────────────────────────────
// Provider
// ────────────────────────────────────────────────────────────────────────────

export const StreamProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  const apiBase =
    process.env.NEXT_PUBLIC_FASTAPI_URL ?? "/api/fastapi";
  const streamValue = useSSEStream(apiBase);

  return (
    <StreamContext.Provider value={streamValue}>
      {children}
    </StreamContext.Provider>
  );
};

// ────────────────────────────────────────────────────────────────────────────
// Consumer hook
// ────────────────────────────────────────────────────────────────────────────

export const useStreamContext = (): StreamContextValue => {
  const context = useContext(StreamContext);
  if (context === undefined) {
    throw new Error("useStreamContext must be used within a StreamProvider");
  }
  return context;
};

export default StreamContext;
