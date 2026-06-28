import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeRaw from 'rehype-raw'
import rehypeKatex from 'rehype-katex'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'

const sanitizeSchema = {
  ...defaultSchema,
  tagNames: [
    ...(defaultSchema.tagNames ?? []),
    'math', 'mrow', 'mi', 'mo', 'mn', 'mfrac', 'msup', 'msub', 'msqrt', 'mtext',
    'span', 'div', 'p', 'strong', 'em', 'code', 'pre', 'ul', 'ol', 'li', 'h1',
    'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'img', 'blockquote', 'hr', 'br',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
  ],
  attributes: {
    ...defaultSchema.attributes,
    code: ['className'],
    pre: ['className'],
    span: ['className', 'style', 'aria-hidden'],
    div: ['className'],
    math: ['xmlns', 'display'],
    '*': ['className'],
  },
}

interface MarkdownProps {
  content: string
}

function MarkdownImpl({ content }: MarkdownProps) {
  return (
    <div className="prose-chat">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[
          [rehypeRaw, { allowDangerousHtml: true }],
          rehypeKatex,
          [rehypeSanitize, sanitizeSchema],
        ]}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

export const Markdown = memo(MarkdownImpl)
