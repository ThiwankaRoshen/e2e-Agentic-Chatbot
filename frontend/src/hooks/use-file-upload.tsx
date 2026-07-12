import { useState, useRef, useEffect, ChangeEvent } from "react";
import { toast } from "sonner";
import { ContentBlock } from "@langchain/core/messages";
import { fileToContentBlock } from "@/lib/multimodal-utils";
import { useThreads } from "@/providers/Thread";

// Image types stay inline in the message content.
// PDFs are uploaded to the artifact endpoint.
export const INLINE_IMAGE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
];

export const PDF_TYPE = "application/pdf";

export const SUPPORTED_FILE_TYPES = [...INLINE_IMAGE_TYPES, PDF_TYPE];

interface UseFileUploadOptions {
  initialBlocks?: ContentBlock.Multimodal.Data[];
  /** Required for PDF artifact uploads. If null, PDFs are blocked. */
  threadId?: string | null;
}

export function useFileUpload({
  initialBlocks = [],
  threadId,
}: UseFileUploadOptions = {}) {
  // Inline content blocks (images only — rendered inside the message bubble)
  const [contentBlocks, setContentBlocks] = useState<
    ContentBlock.Multimodal.Data[]
  >(initialBlocks);
  const dropRef = useRef<HTMLDivElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const dragCounter = useRef(0);

  const { uploadArtifact } = useThreads();

  const isDuplicateImage = (
    file: File,
    blocks: ContentBlock.Multimodal.Data[],
  ) =>
    blocks.some(
      (b) =>
        b.type === "image" &&
        b.metadata?.name === file.name &&
        b.mimeType === file.type,
    );

  const processPdf = async (file: File) => {
    if (!threadId) {
      toast.error("Send a message first to start a thread, then upload PDFs.");
      return;
    }
    try {
      await uploadArtifact(threadId, file);
      toast.success(`"${file.name}" uploaded — indexing in background.`);
    } catch (err) {
      toast.error(`Failed to upload "${file.name}": ${(err as Error).message}`);
    }
  };

  const processFiles = async (files: File[]) => {
    const valid = files.filter((f) => SUPPORTED_FILE_TYPES.includes(f.type));
    const invalid = files.filter((f) => !SUPPORTED_FILE_TYPES.includes(f.type));

    if (invalid.length > 0) {
      toast.error("Unsupported file type. Accepted: JPEG, PNG, GIF, WEBP, PDF.");
    }

    for (const file of valid) {
      if (file.type === PDF_TYPE) {
        await processPdf(file);
      } else {
        // Inline image — add to contentBlocks if not duplicate
        if (!isDuplicateImage(file, contentBlocks)) {
          const block = await fileToContentBlock(file);
          setContentBlocks((prev) => [...prev, block]);
        } else {
          toast.error(`Duplicate image: ${file.name}`);
        }
      }
    }
  };

  const handleFileUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!files.length) return;
    await processFiles(files);
  };

  useEffect(() => {
    if (!dropRef.current) return;

    const onDragEnter = (e: DragEvent) => {
      if (e.dataTransfer?.types?.includes("Files")) {
        dragCounter.current += 1;
        setDragOver(true);
      }
    };
    const onDragLeave = (e: DragEvent) => {
      if (e.dataTransfer?.types?.includes("Files")) {
        dragCounter.current -= 1;
        if (dragCounter.current <= 0) {
          setDragOver(false);
          dragCounter.current = 0;
        }
      }
    };
    const onDrop = async (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter.current = 0;
      setDragOver(false);
      if (!e.dataTransfer) return;
      await processFiles(Array.from(e.dataTransfer.files));
    };
    const onDragOver = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
    };
    const onDragEnd = () => {
      dragCounter.current = 0;
      setDragOver(false);
    };

    window.addEventListener("dragenter", onDragEnter);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("drop", onDrop);
    window.addEventListener("dragend", onDragEnd);
    window.addEventListener("dragover", onDragOver);

    return () => {
      window.removeEventListener("dragenter", onDragEnter);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("drop", onDrop);
      window.removeEventListener("dragend", onDragEnd);
      window.removeEventListener("dragover", onDragOver);
      dragCounter.current = 0;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contentBlocks, threadId]);

  const removeBlock = (idx: number) =>
    setContentBlocks((prev) => prev.filter((_, i) => i !== idx));
  const resetBlocks = () => setContentBlocks([]);

  const handlePaste = async (
    e: React.ClipboardEvent<HTMLTextAreaElement | HTMLInputElement>,
  ) => {
    const files: File[] = [];
    for (let i = 0; i < e.clipboardData.items.length; i++) {
      const item = e.clipboardData.items[i];
      if (item.kind === "file") {
        const f = item.getAsFile();
        if (f) files.push(f);
      }
    }
    if (!files.length) return;
    e.preventDefault();
    await processFiles(files);
  };

  return {
    contentBlocks,
    setContentBlocks,
    handleFileUpload,
    dropRef,
    removeBlock,
    resetBlocks,
    dragOver,
    handlePaste,
  };
}
