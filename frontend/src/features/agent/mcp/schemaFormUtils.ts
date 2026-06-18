/** Helpers to map MCP tool inputSchema (JSON Schema object) to form fields. */

export type SchemaFieldKind =
  | 'string'
  | 'number'
  | 'integer'
  | 'boolean'
  | 'array'
  | 'object'
  | 'unknown'

export type SchemaField = {
  key: string
  kind: SchemaFieldKind
  required: boolean
  description?: string
}

/** Flatten top-level object properties from inputSchema. */
export function listSchemaFields(
  inputSchema: Record<string, unknown> | null | undefined,
): SchemaField[] {
  if (!inputSchema || inputSchema.type !== 'object') return []
  const props = inputSchema.properties
  if (!props || typeof props !== 'object') return []
  const required = new Set(
    Array.isArray(inputSchema.required) ? inputSchema.required.map(String) : [],
  )
  return Object.entries(props as Record<string, Record<string, unknown>>).map(([key, schema]) => ({
    key,
    kind: resolveFieldKind(schema),
    required: required.has(key),
    description: typeof schema.description === 'string' ? schema.description : undefined,
  }))
}

function resolveFieldKind(schema: Record<string, unknown>): SchemaFieldKind {
  const t = schema.type
  if (
    t === 'string' ||
    t === 'number' ||
    t === 'integer' ||
    t === 'boolean' ||
    t === 'array' ||
    t === 'object'
  ) {
    return t
  }
  return 'unknown'
}

/** Build default arguments object from field list. */
export function defaultArgumentsFromFields(fields: SchemaField[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const field of fields) {
    if (field.kind === 'boolean') out[field.key] = false
    else if (field.kind === 'number' || field.kind === 'integer') out[field.key] = undefined
    else if (field.kind === 'array') out[field.key] = []
    else if (field.kind === 'object') out[field.key] = {}
    else out[field.key] = ''
  }
  return out
}

export function argumentsToJsonText(args: Record<string, unknown>): string {
  return JSON.stringify(args, null, 2)
}

export function parseArgumentsJson(text: string): Record<string, unknown> {
  const parsed = JSON.parse(text) as unknown
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('arguments must be a JSON object')
  }
  return parsed as Record<string, unknown>
}
