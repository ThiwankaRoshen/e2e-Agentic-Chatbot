import {
  createContext,
  useContext,
  ReactNode,
  useCallback,
  useState,
  Dispatch,
  SetStateAction,
} from "react";
import { type Artifact, type ThreadSummary } from "@/lib/types";

interface ThreadContextType {
  // Thread list
  getThreads: () => Promise<ThreadSummary[]>;
  threads: ThreadSummary[];
  setThreads: Dispatch<SetStateAction<ThreadSummary[]>>;
  threadsLoading: boolean;
  setThreadsLoading: Dispatch<SetStateAction<boolean>>;

  // Thread deletion
  deleteThread: (threadId: string) => Promise<void>;

  // Per-thread artifacts
  artifacts: Artifact[];
  setArtifacts: Dispatch<SetStateAction<Artifact[]>>;
  fetchArtifacts: (threadId: string) => Promise<void>;
  uploadArtifact: (threadId: string, file: File) => Promise<Artifact>;
  deleteArtifact: (threadId: string, artifactId: string) => Promise<void>;
}

const ThreadContext = createContext<ThreadContextType | undefined>(undefined);

export function ThreadProvider({ children }: { children: ReactNode }) {
  const apiBase = import.meta.env.VITE_FASTAPI_URL ?? "http://localhost:8000";

  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);

  const getThreads = useCallback(async (): Promise<ThreadSummary[]> => {
    const res = await fetch(`${apiBase}/threads`);
    if (!res.ok) throw new Error(`GET /threads failed: ${res.status}`);
    return res.json() as Promise<ThreadSummary[]>;
  }, [apiBase]);

  const deleteThread = useCallback(
    async (threadId: string): Promise<void> => {
      const res = await fetch(`${apiBase}/threads/${threadId}`, {
        method: "DELETE",
      });
      if (!res.ok && res.status !== 404) {
        throw new Error(`DELETE /threads/${threadId} failed: ${res.status}`);
      }
      setThreads((prev) => prev.filter((t) => t.thread_id !== threadId));
    },
    [apiBase],
  );

  const fetchArtifacts = useCallback(
    async (threadId: string): Promise<void> => {
      const res = await fetch(`${apiBase}/threads/${threadId}/artifacts`);
      if (!res.ok) throw new Error(`GET artifacts failed: ${res.status}`);
      const data: Artifact[] = await res.json();
      setArtifacts(data);
    },
    [apiBase],
  );

  const uploadArtifact = useCallback(
    async (threadId: string, file: File): Promise<Artifact> => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${apiBase}/threads/${threadId}/artifacts`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(err || `Upload failed: ${res.status}`);
      }
      const artifact: Artifact = await res.json();
      // Optimistically add to local list
      setArtifacts((prev) => [...prev, artifact]);
      return artifact;
    },
    [apiBase],
  );

  const deleteArtifact = useCallback(
    async (threadId: string, artifactId: string): Promise<void> => {
      const res = await fetch(
        `${apiBase}/threads/${threadId}/artifacts/${artifactId}`,
        { method: "DELETE" },
      );
      if (!res.ok && res.status !== 404) {
        throw new Error(`DELETE artifact failed: ${res.status}`);
      }
      setArtifacts((prev) => prev.filter((a) => a.id !== artifactId));
    },
    [apiBase],
  );

  return (
    <ThreadContext.Provider
      value={{
        getThreads,
        threads,
        setThreads,
        threadsLoading,
        setThreadsLoading,
        deleteThread,
        artifacts,
        setArtifacts,
        fetchArtifacts,
        uploadArtifact,
        deleteArtifact,
      }}
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
