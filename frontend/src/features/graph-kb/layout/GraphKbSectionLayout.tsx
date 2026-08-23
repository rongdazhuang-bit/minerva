import { Outlet } from 'react-router-dom'

/** Section shell for `/app/graph-kb/:graphId/*` (tabs filled in a later task). */
export function GraphKbSectionLayout() {
  return (
    <div className="minerva-page-fill">
      <Outlet />
    </div>
  )
}
