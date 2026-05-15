import { defaultSchema, type Options } from 'rehype-sanitize'

/**
 * 智能体助手回复的 Markdown 净化配置：GFM 表格结构、KaTeX 输出所需 span、受限图片协议。
 */
export const AGENT_CHAT_MARKDOWN_SANITIZE_SCHEMA: Options = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), 'caption', 'col', 'colgroup'],
  ancestors: {
    ...defaultSchema.ancestors,
    caption: ['table'],
    col: ['colgroup', 'table'],
    colgroup: ['table'],
  },
  protocols: {
    ...defaultSchema.protocols,
    /** 允许外链图与内联 ``data:image/...``（模型偶发输出 base64 图）。 */
    src: ['http', 'https', 'data'],
  },
  attributes: {
    ...defaultSchema.attributes,
    /** KaTeX（``output: 'html'``）使用带 className / style 的 span。 */
    span: ['className', 'style', 'ariaHidden', 'title'],
  },
}
