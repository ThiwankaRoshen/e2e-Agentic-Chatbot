import { useState, useRef, useEffect, ChangeEvent } from "react";
import { toast } from "sonner";
import { ContentBlock } from "@langchain/core/messages";
import { fileToContentBlock } from "@/lib/multimodal-utils";

export const SUPPORTED_FILE_TYPES = [
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
  "application/pdf",
];

interface UseFileUploadOptions {
  initialBlocks?: ContentBlock.Multimodal.Data[];
}

export function useFileUpload({ initialBlocks = [] }: UseFileUploadOptions = {}) {
  const [contentBlocks, setContentBlocks] = useState<ContentBlock.Multimodal.Data[]>(initialBlocks);
  const dropRef = useRef<HTMLDivElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const dragCounter = useRef(0);

  const isDuplicate = (file: File, blocks: ContentBlock.Multimodal.Data[]) => {
    if (file.type === "application/pdf") {
      return blocks.some(
        (b) => b.type === "file" && b.mimeType === "application/pdf" && b.metadata?.filename === file.name,
      );
    }
    return blocks.some(
      (b) => b.type === "image" && b.metadata?.name === file.name && b.mimeType === file.type,
    );
  };

  const handleFileUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    const fileArray = Array.from(files);
    const validFiles = fileArray.filter((f) => SUPPORTED_FILE_TYPES.includes(f.type));
    const invalidFiles = fileArray.filter((f) => !SUPPORTED_FILE_TYPES.includes(f.type));
    const uniqueFiles = validFiles.filter((f) => !isDuplicate(f, contentBlocks));
    const duplicateFiles = validFiles.filter((f) => isDuplicate(f, contentBlocks));

    if (invalidFiles.length > 0) {
      toast.error("Invalid file type. Please upload JPEG, PNG, GIF, WEBP, or PDF.");
    }
    if (duplicateFiles.length > 0) {
      toast.error(`Duplicate file(s): ${duplicateFiles.map((f) => f.name).join(", ")}`);
    }

    if (uniqueFiles.length) {
      const newBlocks = await Promise.all(uniqueFiles.map(fileToContentBlock));
      setContentBlocks((prev) => [...prev, ...newBlocks]);
    }
    e.target.value = "";
  };

  useEffect(() => {
    if (!dropRef.current) return;

    const handleWindowDragEnter = (e: DragEvent) => {
      if (e.dataTransfer?.types?.includes("Files")) {
        dragCounter.current += 1;
        setDragOver(true);
      }
    };
    const handleWindowDragLeave = (e: DragEvent) => {
      if (e.dataTransfer?.types?.includes("Files")) {
        dragCounter.current -= 1;
        if (dragCounter.current <= 0) {
          setDragOver(false);
          dragCounter.current = 0;
        }
      }
    };
    const handleWindowDrop = async (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCounter.current = 0;
      setDragOver(false);
      if (!e.dataTransfer) return;

      const files = Array.from(e.dataTransfer.files);
      const validFiles = files.filter((f) => SUPPORTED_FILE_TYPES.includes(f.type));
      const uniqueFiles = validFiles.filter((f) => !isDuplicate(f, contentBlocks));

      if (uniqueFiles.length) {
        const newBlocks = await Promise.all(uniqueFiles.map(fileToContentBlock));
        setContentBlocks((prev) => [...prev, ...newBlocks]);
      }
    };
    const handleWindowDragOver = (e: DragEvent) => { e.preventDefault(); e.stopPropagation(); };
    const handleWindowDragEnd = () => { dragCounter.current = 0; setDragOver(false); };

    window.addEventListener("dragenter", handleWindowDragEnter);
    window.addEventListener("dragleave", handleWindowDragLeave);
    window.addEventListener("drop", handleWindowDrop);
    window.addEventListener("dragend", handleWindowDragEnd);
    window.addEventListener("dragover", handleWindowDragOver);

    return () => {
      window.removeEventListener("dragenter", handleWindowDragEnter);
      window.removeEventListener("dragleave", handleWindowDragLeave);
      window.removeEventListener("drop", handleWindowDrop);
      window.removeEventListener("dragend", handleWindowDragEnd);
      window.removeEventListener("dragover", handleWindowDragOver);
      dragCounter.current = 0;
    };
  }, [contentBlocks]);

  const removeBlock = (idx: number) => setContentBlocks((prev) => prev.filter((_, i) => i !== idx));
  const resetBlocks = () => setContentBlocks([]);

  const handlePaste = async (e: React.ClipboardEvent<HTMLTextAreaElement | HTMLInputElement>) => {
    const items = e.clipboardData.items;
    if (!items) return;
    const files: File[] = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.kind === "file") {
        const file = item.getAsFile();
        if (file) files.push(file);
      }
    }
    if (!files.length) return;
    e.preventDefault();

    const validFiles = files.filter((f) => SUPPORTED_FILE_TYPES.includes(f.type));
    const uniqueFiles = validFiles.filter((f) => !isDuplicate(f, contentBlocks));

    if (uniqueFiles.length) {
      const newBlocks = await Promise.all(uniqueFiles.map(fileToContentBlock));
      setContentBlocks((prev) => [...prev, ...newBlocks]);
    }
  };

  return { contentBlocks, setContentBlocks, handleFileUpload, dropRef, removeBlock, resetBlocks, dragOver, handlePaste };
}
