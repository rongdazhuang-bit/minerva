export const dictQueryKeys = {
  all: (workspaceId: string) => ['dict', workspaceId] as const,
  byCode: (workspaceId: string, dictCode: string, page: number, pageSize: number) =>
    ['dict', workspaceId, 'byCode', dictCode, { page, pageSize }] as const,
}
