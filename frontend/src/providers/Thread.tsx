import {
  createContext,
  useContext,
  ReactNode,
  useCallback,
  useState,
  Dispatch,
  SetStateAction,
} from "react";
import { type ThreadSummary } from "@/lib/types";

interface ThreadContextType {
  getThreads: () => Promise<ThreadSummary[]>;
  threads: ThreadSummary[];
  setThreads: Dispatch<SetStateAction<ThreadSummary[]>>;
  threadsLoading: boolean;
  setThreadsLoading: Dispatch<SetStateAction<boolean>>;
}

const ThreadContext = createContext<ThreadContextType | undefined>(undefined);

export function ThreadProvider({ children }: { children: ReactNode }) {
  const apiBase =
    import.meta.env.VITE_FASTAPI_URL ?? "http://localhost:8000";

  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);

  const getThreads = useCallback(async (): Promise<ThreadSummary[]> => {
    const res = await fetch(`${apiBase}/threads`);
    if (!res.ok) {
      throw new Error(`GET /threads failed: ${res.status}`);
    }
    return res.json() as Promise<ThreadSummary[]>;
  }, [apiBase]);

  return (
    <ThreadContext.Provider
      value={{ getThreads, threads, setThreads, threadsLoading, setThreadsLoading }}
    >
      {children}
    </ThreadContext.Provider>
  );
}

export function useThreads() {
  const context = useContext(ThreadContext);
  if (context === undefined) {
    throw new Error("useThreads must be used within a ThreadProvider");
  }
  return context;
}
