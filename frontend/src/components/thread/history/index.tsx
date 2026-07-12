import { Button } from "@/components/ui/button";
import { useThreads } from "@/providers/Thread";
import { useStreamContext } from "@/providers/Stream";
import { type ThreadSummary } from "@/lib/types";
import { useEffect } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { PanelRightOpen, PanelRightClose } from "lucide-react";
import { useMediaQuery } from "@/hooks/useMediaQuery";

interface ThreadHistoryProps {
  activeThreadId: string | null;
  chatHistoryOpen: boolean;
  setChatHistoryOpen: (open: boolean) => void;
}

function ThreadList({
  threads,
  activeThreadId,
  onThreadClick,
}: {
  threads: ThreadSummary[];
  activeThreadId: string | null;
  onThreadClick?: (threadId: string) => void;
}) {
  const stream = useStreamContext();

  return (
    <div className="flex h-full w-full flex-col items-start justify-start gap-2 overflow-y-scroll [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-track]:bg-transparent">
      {threads.map((t) => {
        const itemText = t.first_message || t.thread_id;
        return (
          <div key={t.thread_id} className="w-full px-1">
            <Button
              variant="ghost"
              className="w-[280px] items-start justify-start text-left font-normal"
              onClick={(e) => {
                e.preventDefault();
                if (t.thread_id === activeThreadId) return;
                onThreadClick?.(t.thread_id);
                stream.loadThread(t.thread_id);
              }}
            >
              <p className="truncate text-ellipsis">{itemText}</p>
            </Button>
          </div>
        );
      })}
    </div>
  );
}

function ThreadHistoryLoading() {
  return (
    <div className="flex h-full w-full flex-col items-start justify-start gap-2 overflow-y-scroll [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-track]:bg-transparent">
      {Array.from({ length: 30 }).map((_, i) => (
        <Skeleton key={`skeleton-${i}`} className="h-10 w-[280px]" />
      ))}
    </div>
  );
}

export default function ThreadHistory({
  activeThreadId,
  chatHistoryOpen,
  setChatHistoryOpen,
}: ThreadHistoryProps) {
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");
  const { getThreads, threads, setThreads, threadsLoading, setThreadsLoading } = useThreads();

  useEffect(() => {
    setThreadsLoading(true);
    getThreads()
      .then(setThreads)
      .catch(console.error)
      .finally(() => setThreadsLoading(false));
  }, []);

  return (
    <>
      {/* Desktop sidebar */}
      <div className="shadow-inner-right hidden h-screen w-[300px] shrink-0 flex-col items-start justify-start gap-6 border-r-[1px] border-slate-300 lg:flex">
        <div className="flex w-full items-center justify-between px-4 pt-1.5">
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
          <h1 className="text-xl font-semibold tracking-tight">Thread History</h1>
        </div>
        {threadsLoading ? (
          <ThreadHistoryLoading />
        ) : (
          <ThreadList threads={threads} activeThreadId={activeThreadId} />
        )}
      </div>

      {/* Mobile sheet */}
      <div className="lg:hidden">
        <Sheet
          open={chatHistoryOpen && !isLargeScreen}
          onOpenChange={(open) => {
            if (!isLargeScreen) setChatHistoryOpen(open);
          }}
        >
          <SheetContent side="left" className="flex lg:hidden">
            <SheetHeader>
              <SheetTitle>Thread History</SheetTitle>
            </SheetHeader>
            <ThreadList
              threads={threads}
              activeThreadId={activeThreadId}
              onThreadClick={() => setChatHistoryOpen(false)}
            />
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
