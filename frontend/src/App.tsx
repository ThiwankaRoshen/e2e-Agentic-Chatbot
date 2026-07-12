import { useState, useCallback } from "react";
import { Toaster } from "@/components/ui/sonner";
import { ThreadProvider } from "@/providers/Thread";
import { StreamProvider } from "@/providers/Stream";
import { ArtifactProvider } from "@/components/thread/artifact";
import { Thread } from "@/components/thread";

export default function App() {
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [chatHistoryOpen, setChatHistoryOpen] = useState(false);
  const [hideToolCalls, setHideToolCalls] = useState(false);
  // Incrementing this tells StreamProvider to wipe its internal state
  const [resetSignal, setResetSignal] = useState(0);

  const handleNewThread = useCallback(() => {
    setActiveThreadId(null);
    setResetSignal((s) => s + 1);
  }, []);

  return (
    <>
      <Toaster />
      <ThreadProvider>
        <StreamProvider
          activeThreadId={activeThreadId}
          setActiveThreadId={setActiveThreadId}
          resetSignal={resetSignal}
        >
          <ArtifactProvider>
            <Thread
              activeThreadId={activeThreadId}
              setActiveThreadId={setActiveThreadId}
              onNewThread={handleNewThread}
              chatHistoryOpen={chatHistoryOpen}
              setChatHistoryOpen={setChatHistoryOpen}
              hideToolCalls={hideToolCalls}
              setHideToolCalls={setHideToolCalls}
            />
          </ArtifactProvider>
        </StreamProvider>
      </ThreadProvider>
    </>
  );
}
