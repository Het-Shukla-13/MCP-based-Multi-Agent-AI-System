import { memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { withToken } from "../lib/api";

/**
 * Renders assistant Markdown.
 * Safety: react-markdown builds React elements and does NOT render raw HTML in the
 * text (a "<script>" in a reply is shown as text). Never add rehype-raw here:
 * the access token in localStorage relies on the page never running injected HTML.
 */

const GENERATED_FILE = /^\/files\/generated\/[0-9a-f-]{36}\/(download|preview|raw)$/i;

/** Our generated-file paths need the API host and the access token; others stay as-is. */
function resolveUrl(url) {
  if (url && GENERATED_FILE.test(url)) return withToken(url);
  return url;
}

function CodeBlock({ className, children }) {
  const [copied, setCopied] = useState(false);
  const language = /language-(\w+)/.exec(className || "")?.[1];
  const code = String(children).replace(/\n$/, "");
  const copy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="md-code">
      <div className="md-code__bar">
        <span>{language || "code"}</span>
        <button onClick={copy} type="button">{copied ? "Copied" : "Copy"}</button>
      </div>
      <pre><code className={className}>{code}</code></pre>
    </div>
  );
}

const components = {
  a: ({ href, children }) => {
    const url = resolveUrl(href);
    const isDownload = /\/download(\?|$)/.test(url || "");
    return (
      <a href={url} rel="noreferrer noopener" target="_blank" {...(isDownload ? { download: "" } : {})}>
        {children}
      </a>
    );
  },
  img: ({ src, alt }) => (
    <a href={resolveUrl(src)} rel="noreferrer noopener" target="_blank">
      <img alt={alt || ""} className="md-image" loading="lazy" src={resolveUrl(src)} />
    </a>
  ),
  // Fenced blocks arrive as <pre><code class="language-x">; inline code has no <pre>.
  pre: ({ children }) => {
    const child = Array.isArray(children) ? children[0] : children;
    return <CodeBlock className={child?.props?.className}>{child?.props?.children}</CodeBlock>;
  },
  table: ({ children }) => (
    <div className="md-table-wrap"><table>{children}</table></div>
  ),
};

function MarkdownMessage({ content }) {
  return (
    <div className="markdown">
      <ReactMarkdown components={components} remarkPlugins={[remarkGfm]}>
        {content || ""}
      </ReactMarkdown>
    </div>
  );
}

// Memoized: while one reply streams, earlier messages don't re-parse their Markdown.
export default memo(MarkdownMessage);
