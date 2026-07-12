import { useEffect } from "react";
import { useThreads } from "@/providers/Thread";
import { type Artifact } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  FileText,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: Artifact["status"] }) {
  const config = {
    uploaded: {
      icon: <Clock className="h-3 w-3" />,
      label: "Queued",
      className: "text-gray-500 bg-gray-100",
    },
    indexing: {
      icon: <Loader2 className="h-3 w-3 animate-spin" />,
      label: "Indexing",
      className: "text-blue-600 bg-blue-50",
    },
    indexed: {
      icon: <CheckCircle2 className="h-3 w-3" />,
      label: "Ready",
      className: "text-emerald-600 bg-emerald-50",
    },
    failed: {
      icon: <XCircle className="h-3 w-3" />,
      label: "Failed",
      className: "text-red-600 bg-red-50",
    },
  } as const;

  const { icon, label, className } = config[status];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        className,
      )}
    >
      {icon}
      {label}
    </span>
  );
}

// ── Single artifact row ───────────────────────────────────────────────────────

function ArtifactRow({
  artifact,
  threadId,
}: {
  artifact: Artifact;
  threadId: string;
}) {
  const { deleteArtifact } = useThreads();

  const handleDelete = async () => {
    try {
      await deleteArtifact(threadId, artifact.id);
      toast.success(`"${artifact.filename}" removed.`);
    } catch {
      toast.error(`Failed to remove "${artifact.filename}".`);
    }
  };

  return (
    <div className="group flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-gray-50">
      <FileText className="h-4 w-4 flex-shrink-0 text-gray-400" />
      <div className="min-w-0 flex-1">
        <p
          className="truncate text-sm text-gray-800"
          title={artifact.filename}
        >
          {artifact.filename}
        </p>
        {artifact.status === "failed" && artifact.error_message && (
          <p className="truncate text-xs text-red-500" title={artifact.error_message}>
            {artifact.error_message}
          </p>
        )}
      </div>
      <StatusBadge status={artifact.status} />
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6 flex-shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
        onClick={handleDelete}
        title="Remove artifact"
      >
        <Trash2 className="h-3.5 w-3.5 text-gray-400 hover:text-red-500" />
      </Button>
    </div>
  );
}

// ── Panel ─────────────────────────────────────────────────────────────────────

interface ArtifactsPanelProps {
  threadId: string | null;
  className?: string;
}

export function ArtifactsPanel({ threadId, className }: ArtifactsPanelProps) {
  const { artifacts, fetchArtifacts } = useThreads();

  // Fetch artifacts when the active thread changes
  useEffect(() => {
    if (!threadId) return;
    fetchArtifacts(threadId).catch(console.error);
  }, [threadId, fetchArtifacts]);

  // Poll indexing artifacts every 3 seconds until all are done
  useEffect(() => {
    if (!threadId) return;
    const hasInProgress = artifacts.some(
      (a) => a.status === "uploaded" || a.status === "indexing",
    );
    if (!hasInProgress) return;

    const timer = setInterval(() => {
      fetchArtifacts(threadId).catch(console.error);
    }, 3000);

    return () => clearInterval(timer);
  }, [threadId, artifacts, fetchArtifacts]);

  if (!threadId) return null;

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <p className="px-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
        Documents
      </p>

      {artifacts.length === 0 ? (
        <p className="px-2 py-1 text-xs text-gray-400">
          No documents yet. Upload a PDF to get started.
        </p>
      ) : (
        <div className="flex flex-col">
          {artifacts.map((artifact) => (
            <ArtifactRow
              key={artifact.id}
              artifact={artifact}
              threadId={threadId}
            />
          ))}
        </div>
      )}
    </div>
  );
}
