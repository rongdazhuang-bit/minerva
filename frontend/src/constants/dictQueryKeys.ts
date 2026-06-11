export const dictQueryKeys = {
  all: () => ['dict'] as const,
  byCode: (dictCode: string, page: number, pageSize: number) =>
    ['dict', 'byCode', dictCode, { page, pageSize }] as const,
}
