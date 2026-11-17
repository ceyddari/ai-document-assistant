import { memo } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const CITATION = /(!?)\[Kaynak\s*(\d+)\]/g;
const CITATION_HREF = /^#kaynak-(\d+)$/;

// "[Kaynak 2]" becomes a link the renderer turns into a badge. A preceding "!" is escaped,
// otherwise "harika![Kaynak 2]" would parse as an image.
function toMarkdown(content: string) {
  return content.replace(CITATION, (_, bang: string, number: string) => `${bang ? "\\!" : ""}[${number}](#kaynak-${number})`);
}

type Props = {
  content: string;
  /** Number of sources shown under the answer; badges outside 1..sourceCount are not clickable. */
  sourceCount: number;
  onCite?: (number: number) => void;
};

export const MessageContent = memo(function MessageContent({ content, sourceCount, onCite }: Props) {
  const components: Components = {
    a: ({ href, children }) => {
      const citation = href ? CITATION_HREF.exec(href) : null;
      if (citation) {
        const number = Number(citation[1]);
        return onCite && number >= 1 && number <= sourceCount
          ? <button type="button" className="cite cite-button" title={`Kaynak ${number}`} aria-label={`Kaynak ${number}'i göster`} onClick={() => onCite(number)}>{number}</button>
          : <span className="cite" title={`Kaynak ${number}`}>{number}</span>;
      }
      return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
    },
  };
  // react-markdown escapes raw HTML and drops javascript: URLs by default.
  return <div className="message-content"><Markdown remarkPlugins={[remarkGfm]} components={components}>{toMarkdown(content)}</Markdown></div>;
});
