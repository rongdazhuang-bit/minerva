/** Supplies graphId to tab pages rendered inside the detail modal. */

import { createContext, useContext, type ReactNode } from 'react'

const GraphKbContext = createContext<string | null>(null)

export type GraphKbProviderProps = {
  graphId: string
  children: ReactNode
}

/** Provides the active graph KB id to nested tab pages. */
export function GraphKbProvider({ graphId, children }: GraphKbProviderProps) {
  return <GraphKbContext.Provider value={graphId}>{children}</GraphKbContext.Provider>
}

/** Returns graphId from modal context; empty string when outside a provider. */
export function useGraphKbId(): string {
  return useContext(GraphKbContext) ?? ''
}
