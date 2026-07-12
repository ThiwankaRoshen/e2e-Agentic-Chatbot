import { useEffect } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useThreads } from "@/providers/Thread";
import { useStreamContext } from "@/providers/Stream";
import { type ThreadSummary } from "@/lib/types";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { PanelRightOpen, PanelRightClose, Trash2 } from "lucide-react";
import { useMediaQuery } from "@/hooks/useMediaQuery";

interface ThreadHistoryProps {
  activeThreadId: string | null;
  setActiveThreadId: (id: string | null) => void;
  onNewThread: () => void;
  chatHistoryOpen: boolean;
  setChatHistoryOpen: (open: boolean) => void;
}

function ThreadList({
  threads,
  activeThreadId,
  onThreadClick,
  onThreadDelete,
}: {
  threads: ThreadSummary[];
  activeThreadId: string | null;
  onThreadClick?: (threadId: string) => void;
  onThreadDelete?: (threadId: string) => void;
}) {
  const stream = useStreamContext();

  if (threads.length === 0) {
    return (
      <p className="px-4 py-2 text-sm text-gray-400">No conversations yet.</p>
    );
  }

  return (
    <div className="flex h-full w-full flex-col items-start justify-start gap-0.5 overflow-y-scroll px-1 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-track]:bg-transparent">
      {threads.map((t) => {
        const label = t.title || t.thread_id.slice(0, 8) + "…";
        const isActive = t.thread_id === activeThreadId;

        return (
          <div
            key={t.thread_id}
            className={`group flex w-full items-center gap-1 rounded-lg pr-1 ${
              isActive ? "bg-gray-100" : "hover:bg-gray-50"
            }`}
          >
            <Button
              variant="ghost"
              className="h-9 min-w-0 flex-1 items-start justify-start text-left font-normal"
              onClick={(e) => {
                e.preventDefault();
                if (isActive) return;
                onThreadClick?.(t.thread_id);
                stream.loadThread(t.thread_id);
              }}
            >
              <p className="w-full truncate text-sm">{label}</p>
            </Button>

            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 flex-shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
              onClick={(e) => {
                e.stopPropagation();
                onThreadDelete?.(t.thread_id);
              }}
              title="Delete thread"
            >
              <Trash2 className="h-3.5 w-3.5 text-gray-400 hover:text-red-500" />
            </Button>
          </div>
        );
      })}
    </div>
  );
}

function ThreadHistoryLoading() {
  return (
    <div className="flex h-full w-full flex-col items-start gap-1 px-2 overflow-y-scroll">
      {Array.from({ length: 20 }).map((_, i) => (
        <Skeleton key={`skeleton-${i}`} className="h-9 w-full rounded-lg" />
      ))}
    </div>
  );
}

export default function ThreadHistory({
  activeThreadId,
  setActiveThreadId,
  onNewThread,
  chatHistoryOpen,
  setChatHistoryOpen,
}: ThreadHistoryProps) {
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");
  const {
    getThreads,
    threads,
    setThreads,
    threadsLoading,
    setThreadsLoading,
    deleteThread,
    setArtifacts,
  } = useThreads();

  useEffect(() => {
    setThreadsLoading(true);
    getThreads()
      .then(setThreads)
      .catch(console.error)
      .finally(() => setThreadsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDelete = async (threadId: string) => {
    try {
      await deleteThread(threadId);
      // If we deleted the active thread, start fresh
      if (threadId === activeThreadId) {
        setArtifacts([]);
        onNewThread();
      }
      toast.success("Thread deleted.");
    } catch {
      toast.error("Failed to delete thread.");
    }
  };

  const handleThreadClick = (threadId: string) => {
    setActiveThreadId(threadId);
    setArtifacts([]); // cleared; fetchArtifacts in ArtifactsPanel will reload
    if (!isLargeScreen) setChatHistoryOpen(false);
  };

  const sidebar = (
    <div className="flex h-full w-full flex-col gap-4 pt-4">
      <div className="flex w-full items-center justify-between px-3">
        <Button
          className="hover:bg-gray-100"
          variant="ghost"
          onClick={() => setChatHistoryOpen(!chatHistoryOpen)}
        >
          {chatHistoryOpen ? (
            <PanelRightOpen className="size-5" />
          ) : (
            <PanelRightClose className="size-5" />
          )}
        </Button>
        <h1 className="text-base font-semibold tracking-tight">Conversations</h1>
      </div>

      {threadsLoading ? (
        <ThreadHistoryLoading />
      ) : (
        <ThreadList
          threads={threads}
          activeThreadId={activeThreadId}
          onThreadClick={handleThreadClick}
          onThreadDelete={handleDelete}
        />
      )}
    </div>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <div className="shadow-inner-right hidden h-screen w-[300px] shrink-0 flex-col items-start border-r border-slate-200 lg:flex">
        {sidebar}
      </div>

      {/* Mobile sheet */}
      <div className="lg:hidden">
        <Sheet
          open={chatHistoryOpen && !isLargeScreen}
          onOpenChange={(open) => {
            if (!isLargeScreen) setChatHistoryOpen(open);
          }}
        >
          <SheetContent side="left" className="flex w-[300px] flex-col lg:hidden">
            <SheetHeader>
              <SheetTitle>Conversations</SheetTitle>
            </SheetHeader>
            {sidebar}
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
