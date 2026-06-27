// assistant Markdown 渲染器。
//
// 痛点③修复要点（spec §4.3）：
//   - user 消息纯文本（不渲染 Markdown，避免用户输入 ** 加粗 等被解释）；
//   - assistant 消息用 react-markdown + remark-gfm（表格/任务列表）+ rehype-raw（允许内联 HTML）
//     + rehype-sanitize（白名单过滤，防 XSS）；
//   - 旧版 html.escape 把 ** 加粗 显示成字面量，新版正确渲染。
import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'

// 放宽 sanitize schema：允许常见结构性标签与 class，禁止 script/style/iframe
const sanitizeSchema = {
  ...defaultSchema,
  tagNames: [
    'a', 'abbr', 'b', 'blockquote', 'br', 'code', 'del', 'em', 'h1', 'h2', 'h3',
    'h4', 'h5', 'h6', 'hr', 'i', 'img', 'ins', 'kbd', 'li', 'mark', 'ol', 'p',
    'pre', 'q', 's', 'small', 'span', 'strong', 'sub', 'sup', 'table', 'tbody',
    'td', 'tfoot', 'th', 'thead', 'tr', 'u', 'ul',
  ],
  attributes: {
    ...defaultSchema.attributes,
    code: ['className'],
    pre: ['className'],
    span: ['className'],
    a: ['href', 'title', 'target', 'rel'],
    img: ['src', 'alt', 'title', 'width', 'height'],
  },
  protocols: {
    ...defaultSchema.protocols,
    href: ['http', 'https', 'mailto'],
    src: ['http', 'https', 'data'],
  },
}

interface MarkdownProps {
  content: string
}

function MarkdownImpl({ content }: MarkdownProps) {
  return (
    <div className="prose-chat">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        // rehype-raw 必须在 rehype-sanitize 之前：先解析内联 HTML，再白名单过滤
        rehypePlugins={[[rehypeRaw, { allowDangerousHtml: true }], [rehypeSanitize, sanitizeSchema]]}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

export const Markdown = memo(MarkdownImpl)
