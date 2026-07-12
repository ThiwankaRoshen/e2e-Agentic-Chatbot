import "./markdown-styles.css";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";
import { FC, memo, useState } from "react";
import { CheckIcon, CopyIcon } from "lucide-react";
import { SyntaxHighlighter } from "@/components/thread/syntax-highlighter";
import { TooltipIconButton } from "@/components/thread/tooltip-icon-button";
import { cn } from "@/lib/utils";
import "katex/dist/katex.min.css";

const useCopyToClipboard = ({ copiedDuration = 3000 } = {}) => {
  const [isCopied, setIsCopied] = useState(false);
  const copyToClipboard = (value: string) => {
    if (!value) return;
    navigator.clipboard.writeText(value).then(() => {
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), copiedDuration);
    });
  };
  return { isCopied, copyToClipboard };
};

const CodeHeader: FC<{ language?: string; code: string }> = ({ language, code }) => {
  const { isCopied, copyToClipboard } = useCopyToClipboard();
  return (
    <div className="flex items-center justify-between gap-4 rounded-t-lg bg-zinc-900 px-4 py-2 text-sm font-semibold text-white">
      <span className="lowercase [&>span]:text-xs">{language}</span>
      <TooltipIconButton tooltip="Copy" onClick={() => !isCopied && copyToClipboard(code)}>
        {isCopied ? <CheckIcon /> : <CopyIcon />}
      </TooltipIconButton>
    </div>
  );
};

const defaultComponents: any = {
  h1: ({ className, ...props }: any) => (
    <h1 className={cn("mb-8 scroll-m-20 text-4xl font-extrabold tracking-tight last:mb-0", className)} {...props} />
  ),
  h2: ({ className, ...props }: any) => (
    <h2 className={cn("mt-8 mb-4 scroll-m-20 text-3xl font-semibold tracking-tight first:mt-0 last:mb-0", className)} {...props} />
  ),
  h3: ({ className, ...props }: any) => (
    <h3 className={cn("mt-6 mb-4 scroll-m-20 text-2xl font-semibold tracking-tight first:mt-0 last:mb-0", className)} {...props} />
  ),
  p: ({ className, ...props }: any) => (
    <p className={cn("mt-5 mb-5 leading-7 first:mt-0 last:mb-0", className)} {...props} />
  ),
  a: ({ className, ...props }: any) => (
    <a className={cn("text-primary font-medium underline underline-offset-4", className)} {...props} />
  ),
  ul: ({ className, ...props }: any) => (
    <ul className={cn("my-5 ml-6 list-disc [&>li]:mt-2", className)} {...props} />
  ),
  ol: ({ className, ...props }: any) => (
    <ol className={cn("my-5 ml-6 list-decimal [&>li]:mt-2", className)} {...props} />
  ),
  pre: ({ className, ...props }: any) => (
    <pre className={cn("max-w-4xl overflow-x-auto rounded-lg bg-black text-white", className)} {...props} />
  ),
  code: ({ className, children, ...props }: any) => {
    const match = /language-(\w+)/.exec(className || "");
    if (match) {
      const language = match[1];
      const code = String(children).replace(/\n$/, "");
      return (
        <>
          <CodeHeader language={language} code={code} />
          <SyntaxHighlighter language={language} className={className}>
            {code}
          </SyntaxHighlighter>
        </>
      );
    }
    return (
      <code className={cn("rounded font-semibold", className)} {...props}>
        {children}
      </code>
    );
  },
};

const MarkdownTextImpl: FC<{ children: string }> = ({ children }) => (
  <div className="markdown-content">
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} components={defaultComponents}>
      {children}
    </ReactMarkdown>
  </div>
);

export const MarkdownText = memo(MarkdownTextImpl);
